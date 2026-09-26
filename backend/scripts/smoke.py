#!/usr/bin/env python3
"""Business smoke test for the audit API.

Runs inside the one-shot ``verify`` compose service.  Exercises the audit
endpoint with representative business payloads (pass, curvature exceeded,
zero tangent, junction break, invalid input, steering-rate pass, interior
rate excess, junction rate jump, legacy response shape) and exits non-zero
on the first unexpected result.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API_URL = os.environ.get("API_URL", "http://api:8000").rstrip("/")
WEB_URL = os.environ.get("WEB_URL", "http://web:80").rstrip("/")

ARC_L = {"points": [[-3, 0], [-2, 1], [-1, 0], [0, 0]]}
ARC_R = {"points": [[0, 0], [1, 0], [2, 1], [3, 0]]}
PIN_L = {"points": [[0, 0], [10, 0], [0, 1], [10, 1]]}
PIN_R = {"points": [[10, 1], [20, 1], [10, 2], [20, 2]]}
CUSP = {"points": [[0, 0], [1, 0], [-1, 0], [0, 0]]}
# Two halves of one cubic subdivided at t = 0.5: C-infinity junction, so
# the steering rate dκ/ds is continuous across the splice as well.
SEG_A = {"points": [[0, 0], [4, 0], [8, 2], [12, 4]]}
SEG_B = {"points": [[12, 4], [16, 6], [20, 8], [24, 8]]}


def call(path: str, payload=None):
    url = f"{API_URL}{path}"
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def get(url: str) -> int:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status


def expect(cond: bool, label: str, detail="") -> None:
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        raise SystemExit(1)


def main() -> None:
    print(f"target API: {API_URL}")
    print(f"target WEB: {WEB_URL}")

    status, body = call("/health")
    expect(status == 200 and body.get("status") == "ok",
          "API health endpoint", str(body))

    expect(get(f"{WEB_URL}/index.html") == 200,
          "WEB serves the audit page (via web container)")

    # 1. valid G2 spline passes and reports per-segment maxima
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    expect(status == 200, "pass-case HTTP 200", str(status))
    expect(body.get("ok") is True, "pass-case ok=true", str(body)[:300])
    segs = body.get("segments", [])
    expect(len(segs) == 2 and all(s["max_curvature"] > 0 for s in segs),
           "pass-case reports 2 segment maxima with locations", str(segs))

    # 2. interior extremum that endpoint checks alone would miss
    status, body = call("/api/audit",
                        {"segments": [PIN_L, PIN_R], "max_curvature": 1.0})
    err = body.get("error") or {}
    expect(body.get("ok") is False, "hairpin ok=false")
    expect(err.get("code") == "CURVATURE_EXCEEDED",
           "hairpin code=CURVATURE_EXCEEDED", str(err))
    expect(err.get("segment") == 0, "hairpin earliest segment=0", str(err))
    expect(0 < err.get("parameter", -1) < 1,
           "hairpin parameter inside segment", str(err))
    expect(isinstance(err.get("point"), list) and len(err["point"]) == 2,
           "hairpin reports coordinates", str(err))
    expect(err.get("curvature", 0) > 1.0,
           "hairpin reports over-limit curvature", str(err))

    # stability: same draft twice -> identical answer
    _, body2 = call("/api/audit",
                    {"segments": [PIN_L, PIN_R], "max_curvature": 1.0})
    expect(body == body2, "audit result is stable for repeated drafts")

    # 3. zero tangent vector -> non-runnable
    status, body = call("/api/audit",
                        {"segments": [CUSP, ARC_R], "max_curvature": 100.0})
    err = (body.get("error") or {})
    expect(err.get("code") == "ZERO_TANGENT",
           "zero-tangent code=ZERO_TANGENT", str(err))

    # 4. junction break
    broken = {"points": [[1, 0], [2, 0], [3, 0], [4, 0]]}
    status, body = call("/api/audit",
                        {"segments": [ARC_L, broken], "max_curvature": 100.0})
    expect((body.get("error") or {}).get("code") == "POSITION_DISCONTINUITY",
           "position discontinuity detected", str(body.get("error")))

    # 5. structural validation
    status, body = call("/api/audit",
                        {"segments": [ARC_L], "max_curvature": 1.0})
    expect(status == 422 and
           body.get("error", {}).get("code") == "INVALID_INPUT",
           "single segment rejected with 422", str(body))

    # 6. legacy drafts (no rate limit) keep the legacy response shape
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    expect(body.get("ok") is True and "max_curvature_rate" not in body
           and all("max_curvature_rate" not in s
                   for s in body.get("segments", [])),
           "legacy draft response unchanged", str(body)[:300])

    # 7. steering-rate audit: C-infinity draft passes and reports maxima
    status, body = call("/api/audit",
                        {"segments": [SEG_A, SEG_B], "max_curvature": 0.5,
                         "max_curvature_rate": 0.05})
    expect(status == 200 and body.get("ok") is True,
           "rate pass-case ok=true", str(body)[:300])
    expect(body.get("max_curvature_rate") == 0.05,
           "rate pass-case echoes the limit", str(body)[:300])
    segs = body.get("segments", [])
    expect(len(segs) == 2 and all(s.get("max_curvature_rate", 0) > 0
                                  for s in segs),
           "rate pass-case reports per-segment max rates", str(segs))
    expect(all(set(s.get("rate_location", {})) == {"t", "x", "y"}
               for s in segs),
           "rate pass-case reports rate parameters and coordinates",
           str(segs))

    # 8. interior steering-rate excess (curvature itself within limit)
    status, body = call("/api/audit",
                        {"segments": [PIN_L, PIN_R], "max_curvature": 100.0,
                         "max_curvature_rate": 50.0})
    err = body.get("error") or {}
    expect(body.get("ok") is False and
           err.get("code") == "CURVATURE_RATE_EXCEEDED",
           "interior rate excess code=CURVATURE_RATE_EXCEEDED", str(err))
    expect(err.get("segment") == 0 and 0 < err.get("parameter", -1) < 1,
           "interior rate excess located inside segment 0", str(err))
    expect(abs(err.get("curvature_rate", 0)) > 50.0 and
           err.get("max_curvature_rate") == 50.0,
           "interior rate excess reports actual value and limit", str(err))
    expect(isinstance(err.get("point"), list) and len(err["point"]) == 2,
           "interior rate excess reports coordinates", str(err))

    # stability: same rate-limited draft twice -> identical answer
    _, body2 = call("/api/audit",
                    {"segments": [PIN_L, PIN_R], "max_curvature": 100.0,
                     "max_curvature_rate": 50.0})
    expect(body == body2, "rate audit result is stable for repeated drafts")

    # 9. junction steering-rate jump (curvature continuous, rate jumps)
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
                         "max_curvature_rate": 1.0})
    err = body.get("error") or {}
    expect(body.get("ok") is False and
           err.get("code") == "CURVATURE_RATE_DISCONTINUITY",
           "junction rate jump code=CURVATURE_RATE_DISCONTINUITY", str(err))
    expect(err.get("segment") == 0 and err.get("parameter") == 1.0,
           "junction rate jump located at first splice", str(err))
    expect(abs(err.get("curvature_rate_end", 0) - 2 / 3) < 1e-9 and
           abs(err.get("curvature_rate_start", 0) + 2 / 3) < 1e-9 and
           err.get("max_curvature_rate") == 1.0,
           "junction rate jump reports left/right values and limit",
           str(err))

    # 10. invalid steering-rate limit rejected
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
                         "max_curvature_rate": 0})
    expect(status == 422 and
           body.get("error", {}).get("code") == "INVALID_INPUT",
           "non-positive rate limit rejected with 422", str(body))

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
    sys.exit(0)
