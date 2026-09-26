"""HTTP-level tests using FastAPI's in-process test client."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ARC_L = {"points": [[-3, 0], [-2, 1], [-1, 0], [0, 0]]}
ARC_R = {"points": [[0, 0], [1, 0], [2, 1], [3, 0]]}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_audit_pass_payload():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["segments"]) == 2
    assert body["segments"][0]["max_curvature"] > 0


def test_audit_fail_payload():
    pin_l = {"points": [[0, 0], [10, 0], [0, 1], [10, 1]]}
    pin_r = {"points": [[10, 1], [20, 1], [10, 2], [20, 2]]}
    r = client.post("/api/audit", json={
        "segments": [pin_l, pin_r], "max_curvature": 1.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CURVATURE_EXCEEDED"
    assert body["error"]["segment"] == 0
    assert "curvature" in body["error"] and "point" in body["error"]


def test_audit_invalid_payload():
    r = client.post("/api/audit", json={"segments": [ARC_L],
                                        "max_curvature": 1.0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


# Two halves of one cubic subdivided at t = 0.5 (C-infinity junction).
SEG_A = {"points": [[0, 0], [4, 0], [8, 2], [12, 4]]}
SEG_B = {"points": [[12, 4], [16, 6], [20, 8], [24, 8]]}


def test_audit_with_rate_limit_passes():
    r = client.post("/api/audit", json={
        "segments": [SEG_A, SEG_B], "max_curvature": 0.5,
        "max_curvature_rate": 0.05})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["max_curvature_rate"] == 0.05
    assert "max_curvature_rate" in body["segments"][0]
    assert "rate_location" in body["segments"][0]


def test_audit_rate_discontinuity_payload():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 2.0,
        "max_curvature_rate": 1.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    err = body["error"]
    assert err["code"] == "CURVATURE_RATE_DISCONTINUITY"
    assert err["curvature_rate_end"] == -err["curvature_rate_start"]
    assert err["max_curvature_rate"] == 1.0


def test_audit_invalid_rate_limit():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 1.0,
        "max_curvature_rate": -1})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_legacy_response_has_no_rate_keys():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "max_curvature_rate" not in body
    assert all("max_curvature_rate" not in s for s in body["segments"])
