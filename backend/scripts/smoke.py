#!/usr/bin/env python3
"""Business smoke test for the audit API.

Runs inside the one-shot ``verify`` compose service.  Exercises the audit
endpoint with representative business payloads (pass, curvature exceeded,
zero tangent, junction break, invalid input, in-segment turning-rate
exceeded, junction turning-rate jump, turning-rate-enabled pass and
backward compatibility for drafts without the optional limit) and exits
non-zero on the first unexpected result.
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
# Curvature-continuous with ARC_L at the junction, but dκ/ds jumps +2/3 -> -2/3.
ARC_R3 = {"points": [[0, 0], [1, 0], [2, 1], [4, 0]]}
# Exact de Casteljau split of one cubic: fully continuous incl. dκ/ds.
SPLIT_A = {"points": [[0, 0], [4, 0], [8, 2], [10, 5]]}
SPLIT_B = {"points": [[10, 5], [12, 8], [12, 12], [8, 16]]}


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

    # 6. turning rate: in-segment |dκ/ds| over the limit (curvature is fine)
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
                         "max_turn_rate": 0.6})
    err = body.get("error") or {}
    expect(status == 200 and body.get("ok") is False,
           "turn-rate in-segment HTTP 200 + ok=false", str(body)[:300])
    expect(err.get("code") == "TURN_RATE_EXCEEDED",
           "turn-rate in-segment code=TURN_RATE_EXCEEDED", str(err))
    expect(err.get("segment") == 0 and 0 < err.get("parameter", -1) < 1,
           "turn-rate in-segment earliest location in segment 1", str(err))
    expect(abs(err.get("turn_rate", 0)) > 0.6 and
           err.get("max_turn_rate") == 0.6,
           "turn-rate in-segment reports actual value and limit", str(err))
    expect(isinstance(err.get("point"), list) and len(err["point"]) == 2,
           "turn-rate in-segment reports coordinates", str(err))

    # 7. turning rate: jump at a curvature-continuous junction
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R3], "max_curvature": 2.0,
                         "max_turn_rate": 100.0})
    err = body.get("error") or {}
    expect(err.get("code") == "TURN_RATE_DISCONTINUITY",
           "turn-rate junction code=TURN_RATE_DISCONTINUITY", str(err))
    expect(err.get("segment") == 0 and err.get("parameter") == 1.0,
           "turn-rate junction located at first splice", str(err))
    expect(abs(err.get("turn_rate_end", 0) - 2 / 3) < 1e-9 and
           abs(err.get("turn_rate_start", 0) + 2 / 3) < 1e-9,
           "turn-rate junction reports left/right actual values", str(err))

    # 8. turning rate enabled and satisfied: per-segment maxima reported
    status, body = call("/api/audit",
                        {"segments": [SPLIT_A, SPLIT_B], "max_curvature": 1.0,
                         "max_turn_rate": 0.1})
    expect(body.get("ok") is True and body.get("max_turn_rate") == 0.1,
           "turn-rate pass-case ok=true with echoed limit", str(body)[:300])
    segs = body.get("segments", [])
    expect(len(segs) == 2 and all(s.get("max_turn_rate", 0) > 0 and
                                  "turn_rate_location" in s for s in segs),
           "turn-rate pass-case reports per-segment maxima with locations",
           str(segs))

    # 9. backward compatibility: drafts without the limit are unchanged
    status, body = call("/api/audit",
                        {"segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    expect("max_turn_rate" not in body and
           all("max_turn_rate" not in s for s in body.get("segments", [])),
           "no turn-rate fields when the limit is not filled in", str(body))

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
    sys.exit(0)
