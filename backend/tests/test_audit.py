"""End-to-end splice audit tests."""

import math

import pytest

from app.audit import AuditInputError, audit

# Symmetric S-shaped arc whose two mirrored halves join with G2 continuity
# at (0,0): tangents (3,0) both sides, curvature 0 at the junction.
ARC_L = {"points": [[-3, 0], [-2, 1], [-1, 0], [0, 0]]}
ARC_R = {"points": [[0, 0], [1, 0], [2, 1], [3, 0]]}

# Hairpin with large interior curvature (~6.42) but tiny endpoint values.
PIN_L = {"points": [[0, 0], [10, 0], [0, 1], [10, 1]]}
PIN_R = {"points": [[10, 1], [20, 1], [10, 2], [20, 2]]}

# Segment whose tangent vanishes at two interior parameters.
LOOP = {"points": [[1, 0], [2, 0], [0, 0], [1, 0]]}
# Straight segment ending at (1,0) with tangent (3,0), junction-compatible.
TAIL = {"points": [[-2, 0], [-1, 0], [0, 0], [1, 0]]}


def test_passing_spline_reports_segment_maxima():
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    assert r["ok"] is True and r["error"] is None
    assert len(r["segments"]) == 2
    assert math.isclose(r["segments"][0]["max_curvature"],
                        r["segments"][1]["max_curvature"], abs_tol=1e-12)
    loc = r["segments"][0]["location"]
    assert 0.0 <= loc["t"] <= 1.0
    assert set(loc) == {"t", "x", "y"}


def test_interior_curvature_extremum_is_caught():
    r = audit({"segments": [PIN_L, PIN_R], "max_curvature": 1.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "CURVATURE_EXCEEDED"
    assert e["segment"] == 0
    assert math.isclose(e["parameter"], 0.4235922886, abs_tol=1e-7)
    assert math.isclose(e["curvature"], 6.423730581, abs_tol=1e-6)
    assert e["point"] is not None and len(e["point"]) == 2


def test_limit_above_extremum_passes():
    r = audit({"segments": [PIN_L, PIN_R], "max_curvature": 100.0})
    assert r["ok"] is True


def test_endpoint_curvature_limit_checked():
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 0.1})
    assert r["ok"] is False
    assert r["error"]["code"] == "CURVATURE_EXCEEDED"
    assert r["error"]["segment"] == 0
    assert r["error"]["parameter"] == 0.0


def test_position_discontinuity():
    bad_r = {"points": [[1, 0], [2, 0], [3, 0], [4, 0]]}
    r = audit({"segments": [ARC_L, bad_r], "max_curvature": 10.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "POSITION_DISCONTINUITY"
    assert e["segment"] == 0
    assert e["point_end"] == [0, 0]
    assert e["point_next"] == [1, 0]


def test_tangent_discontinuity():
    # Same endpoint, different departure vector.
    bad_r = {"points": [[0, 0], [0, 1], [1, 1], [2, 1]]}
    r = audit({"segments": [ARC_L, bad_r], "max_curvature": 10.0})
    assert r["ok"] is False
    assert r["error"]["code"] == "TANGENT_DISCONTINUITY"
    assert r["error"]["tangent_end"] == [3, 0]
    assert r["error"]["tangent_start"] == [0, 3]


def test_curvature_discontinuity():
    straight = {"points": [[-3, 0], [-2, 0], [-1, 0], [0, 0]]}
    r = audit({"segments": [straight, ARC_R], "max_curvature": 100.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "CURVATURE_DISCONTINUITY"
    assert e["curvature_end"] == 0.0
    assert math.isclose(e["curvature_start"], 2 / 3, abs_tol=1e-9)


def test_zero_tangent_inside_first_segment():
    z = {"points": [[0, 0], [1, 0], [-1, 0], [0, 0]]}
    r = audit({"segments": [z, ARC_R], "max_curvature": 100.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "ZERO_TANGENT"
    assert e["segment"] == 0
    assert math.isclose(e["parameter"], (3 - math.sqrt(3)) / 6, abs_tol=1e-9)


def test_zero_tangent_at_start():
    flat = {"points": [[0, 0], [0, 0], [1, 0], [2, 0]]}
    r = audit({"segments": [flat, ARC_R], "max_curvature": 100.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "ZERO_TANGENT" and e["segment"] == 0
    assert e["parameter"] == 0.0


def test_earliest_problem_wins():
    # Segment 0 is fine; junction 0 is G2-continuous; segment 1 has an
    # interior zero tangent; segment 2 would break curvature continuity.
    arc2 = {"points": [[1, 0], [2, 0], [2, 1], [3, 1]]}
    r = audit({"segments": [TAIL, LOOP, arc2], "max_curvature": 100.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["segment"] == 1
    assert e["code"] == "ZERO_TANGENT"


def test_result_is_stable():
    payload = {"segments": [PIN_L, PIN_R], "max_curvature": 1.0}
    a = audit(payload)
    b = audit(payload)
    assert a == b


@pytest.mark.parametrize("n", [1, 6])
def test_segment_count_bounds(n):
    segs = [ARC_L] * n
    with pytest.raises(AuditInputError):
        audit({"segments": segs, "max_curvature": 1.0})


def test_integer_points_required():
    bad = {"points": [[0, 0], [0.5, 0], [1, 0], [2, 0]]}
    with pytest.raises(AuditInputError):
        audit({"segments": [bad, ARC_R], "max_curvature": 1.0})


def test_bad_max_curvature():
    with pytest.raises(AuditInputError):
        audit({"segments": [ARC_L, ARC_R], "max_curvature": 0})
    with pytest.raises(AuditInputError):
        audit({"segments": [ARC_L, ARC_R], "max_curvature": -1.0})
