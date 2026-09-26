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

# ARC_R with P3 moved to (4,0): same junction position, tangent (3,0) and
# curvature 2/3 as ARC_L's end, but the turning rate jumps +2/3 -> -2/3.
ARC_R3 = {"points": [[0, 0], [1, 0], [2, 1], [4, 0]]}

# Exact de Casteljau split of one cubic at t = 1/2 (integer control points):
# C^infty at the junction, so position/tangent/curvature/turn-rate are all
# continuous there; segment B carries an interior dκ/ds extremum.
SPLIT_A = {"points": [[0, 0], [4, 0], [8, 2], [10, 5]]}
SPLIT_B = {"points": [[10, 5], [12, 8], [12, 12], [8, 16]]}


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


# ---- unified maximum turning rate dκ/ds (optional) ------------------------


def test_turn_rate_disabled_keeps_legacy_response():
    legacy = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    assert "max_turn_rate" not in legacy
    assert all("max_turn_rate" not in s for s in legacy["segments"])
    # An explicit null is "not filled in": byte-identical response.
    assert audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
                  "max_turn_rate": None}) == legacy


def test_turn_rate_pass_reports_segment_maxima():
    r = audit({"segments": [SPLIT_A, SPLIT_B], "max_curvature": 1.0,
               "max_turn_rate": 0.1})
    assert r["ok"] is True and r["error"] is None
    assert r["max_turn_rate"] == 0.1
    s0, s1 = r["segments"]
    # Segment A peaks at the junction endpoint (t = 1) ...
    assert math.isclose(s0["max_turn_rate"], 0.010114803014211, abs_tol=1e-9)
    assert s0["turn_rate_location"]["t"] == 1.0
    assert s0["turn_rate_location"]["x"] == 10.0
    assert s0["turn_rate_location"]["y"] == 5.0
    # ... segment B at an interior stationary point of dκ/ds.
    assert math.isclose(s1["max_turn_rate"], 0.013289681654063, abs_tol=1e-9)
    loc = s1["turn_rate_location"]
    assert math.isclose(loc["t"], 0.6971813501590987, abs_tol=1e-9)
    assert set(loc) == {"t", "x", "y"}


def test_turn_rate_in_segment_exceeded():
    # Curvature stays within 2.0, but |dκ/ds| peaks ~0.746 inside segment 1.
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
               "max_turn_rate": 0.6})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "TURN_RATE_EXCEEDED"
    assert e["segment"] == 0
    assert math.isclose(e["parameter"], 0.3989525024749128, abs_tol=1e-9)
    assert math.isclose(e["turn_rate"], 0.7459898642202216, abs_tol=1e-9)
    assert e["max_turn_rate"] == 0.6
    assert e["point"] is not None and len(e["point"]) == 2
    assert "control_points" in e
    assert r["max_turn_rate"] == 0.6


def test_turn_rate_exceeded_at_start_endpoint():
    # |dκ/ds| at t=0 of ARC_L is exactly 1/2.
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
               "max_turn_rate": 0.4})
    e = r["error"]
    assert e["code"] == "TURN_RATE_EXCEEDED"
    assert e["segment"] == 0 and e["parameter"] == 0.0
    assert e["turn_rate"] == -0.5


def test_turn_rate_junction_discontinuity():
    # Curvature-continuous splice whose dκ/ds jumps across the junction.
    r = audit({"segments": [ARC_L, ARC_R3], "max_curvature": 2.0,
               "max_turn_rate": 100.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "TURN_RATE_DISCONTINUITY"
    assert e["segment"] == 0 and e["parameter"] == 1.0
    assert math.isclose(e["turn_rate_end"], 2 / 3, abs_tol=1e-12)
    assert math.isclose(e["turn_rate_start"], -2 / 3, abs_tol=1e-12)
    assert e["max_turn_rate"] == 100.0
    assert "control_points" in e and "next_control_points" in e


def test_turn_rate_earliest_problem_wins():
    # Same junction jump as above, but the tighter limit makes the interior
    # of segment 1 (t ~ 0.399) the earliest problem in travel order.
    r = audit({"segments": [ARC_L, ARC_R3], "max_curvature": 2.0,
               "max_turn_rate": 0.6})
    e = r["error"]
    assert e["code"] == "TURN_RATE_EXCEEDED"
    assert e["segment"] == 0
    assert 0.0 < e["parameter"] < 1.0


def test_turn_rate_straight_splice_passes_tiny_limit():
    straight1 = {"points": [[0, 0], [1, 0], [2, 0], [3, 0]]}
    straight2 = {"points": [[3, 0], [4, 0], [5, 0], [6, 0]]}
    r = audit({"segments": [straight1, straight2], "max_curvature": 1.0,
               "max_turn_rate": 1e-9})
    assert r["ok"] is True
    assert all(s["max_turn_rate"] == 0.0 for s in r["segments"])


def test_turn_rate_result_stable():
    payload = {"segments": [SPLIT_A, SPLIT_B], "max_curvature": 1.0,
               "max_turn_rate": 0.1}
    assert audit(payload) == audit(payload)
    payload = {"segments": [ARC_L, ARC_R3], "max_curvature": 2.0,
               "max_turn_rate": 100.0}
    assert audit(payload) == audit(payload)


def test_bad_max_turn_rate():
    for bad in (0, -1.0, "x", True, float("nan"), float("inf")):
        with pytest.raises(AuditInputError):
            audit({"segments": [ARC_L, ARC_R], "max_curvature": 1.0,
                   "max_turn_rate": bad})
