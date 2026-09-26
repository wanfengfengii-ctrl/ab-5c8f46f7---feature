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


SPLIT_A = {"points": [[0, 0], [4, 0], [8, 2], [10, 5]]}
SPLIT_B = {"points": [[10, 5], [12, 8], [12, 12], [8, 16]]}


def test_audit_turn_rate_enabled_pass():
    r = client.post("/api/audit", json={
        "segments": [SPLIT_A, SPLIT_B], "max_curvature": 1.0,
        "max_turn_rate": 0.1})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["max_turn_rate"] == 0.1
    assert all("max_turn_rate" in s and "turn_rate_location" in s
               for s in body["segments"])


def test_audit_turn_rate_fail_payload():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 2.0,
        "max_turn_rate": 0.6})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    err = body["error"]
    assert err["code"] == "TURN_RATE_EXCEEDED"
    assert err["segment"] == 0
    assert "turn_rate" in err and "max_turn_rate" in err and "point" in err


def test_audit_turn_rate_disabled_response_unchanged():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    body = r.json()
    assert "max_turn_rate" not in body
    assert all("max_turn_rate" not in s for s in body["segments"])


def test_audit_bad_turn_rate_422():
    r = client.post("/api/audit", json={
        "segments": [ARC_L, ARC_R], "max_curvature": 1.0,
        "max_turn_rate": -2})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_INPUT"
