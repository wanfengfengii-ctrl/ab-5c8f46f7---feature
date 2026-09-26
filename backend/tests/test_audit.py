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


# ---------------------------------------------------------------------------
# Optional unified steering-rate limit (dκ/ds of the signed curvature).
# ---------------------------------------------------------------------------

# Two halves of one cubic subdivided at t = 0.5: C-infinity junction, so
# both curvature and steering rate are continuous across the splice.
SEG_A = {"points": [[0, 0], [4, 0], [8, 2], [12, 4]]}
SEG_B = {"points": [[12, 4], [16, 6], [20, 8], [24, 8]]}

# Segment whose steering rate at t = 0 is exactly -8/9.
BEND = {"points": [[0, 0], [0, 1], [1, 1], [1, 2]]}


def test_rate_limit_omitted_keeps_legacy_response():
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0})
    assert r["ok"] is True
    assert "max_curvature_rate" not in r
    assert all("max_curvature_rate" not in s for s in r["segments"])
    assert all("rate_location" not in s for s in r["segments"])


def test_rate_limit_null_disables_check():
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
               "max_curvature_rate": None})
    assert r["ok"] is True and "max_curvature_rate" not in r


def test_rate_pass_reports_per_segment_maxima():
    r = audit({"segments": [SEG_A, SEG_B], "max_curvature": 0.5,
               "max_curvature_rate": 0.05})
    assert r["ok"] is True and r["error"] is None
    assert r["max_curvature_rate"] == 0.05
    s0, s1 = r["segments"]
    # Exact maxima (root isolation): |dκ/ds| peaks inside both halves.
    assert math.isclose(s0["max_curvature_rate"], 0.008706309572,
                        abs_tol=1e-9)
    assert math.isclose(s0["rate_location"]["t"], 0.1840901210,
                        abs_tol=1e-7)
    assert math.isclose(s1["max_curvature_rate"], 0.008706309572,
                        abs_tol=1e-9)
    assert math.isclose(s1["rate_location"]["t"], 0.8159098790,
                        abs_tol=1e-7)
    assert set(s0["rate_location"]) == {"t", "x", "y"}
    # Curvature summaries are still reported next to the rate values.
    assert math.isclose(s0["max_curvature"], 1 / 12, abs_tol=1e-12)


def test_interior_rate_exceeded_with_curvature_in_limit():
    r = audit({"segments": [PIN_L, PIN_R], "max_curvature": 100.0,
               "max_curvature_rate": 50.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "CURVATURE_RATE_EXCEEDED"
    assert e["segment"] == 0
    assert math.isclose(e["parameter"], 0.4802526352, abs_tol=1e-7)
    assert math.isclose(e["curvature_rate"], -71.66787439, abs_tol=1e-6)
    assert e["max_curvature_rate"] == 50.0
    assert e["point"] is not None and len(e["point"]) == 2
    assert r["max_curvature_rate"] == 50.0


def test_junction_rate_discontinuity():
    # ARC_L/ARC_R join with G2 continuity (kappa^2 equal) but the signed
    # steering rate jumps from +2/3 to -2/3.
    r = audit({"segments": [ARC_L, ARC_R], "max_curvature": 2.0,
               "max_curvature_rate": 1.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "CURVATURE_RATE_DISCONTINUITY"
    assert e["segment"] == 0 and e["parameter"] == 1.0
    assert e["point"] == [0.0, 0.0]
    assert math.isclose(e["curvature_rate_end"], 2 / 3, abs_tol=1e-12)
    assert math.isclose(e["curvature_rate_start"], -2 / 3, abs_tol=1e-12)
    assert e["max_curvature_rate"] == 1.0
    assert "control_points" in e and "next_control_points" in e


def test_rate_exceeded_at_segment_start():
    r = audit({"segments": [BEND, ARC_R], "max_curvature": 10.0,
               "max_curvature_rate": 0.8})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "CURVATURE_RATE_EXCEEDED"
    assert e["segment"] == 0 and e["parameter"] == 0.0
    assert math.isclose(e["curvature_rate"], -8 / 9, abs_tol=1e-12)


def test_rate_limit_above_extremum_passes():
    r = audit({"segments": [PIN_L, PIN_R], "max_curvature": 100.0,
               "max_curvature_rate": 100.0})
    assert r["ok"] is True


def test_rate_earliest_problem_wins():
    # Junction 0 has a steering-rate jump; later segments would break
    # position continuity -- the junction problem is earlier in travel
    # order and must be reported.
    r = audit({"segments": [ARC_L, ARC_R, SEG_A, SEG_B],
               "max_curvature": 2.0, "max_curvature_rate": 1.0})
    assert r["ok"] is False
    e = r["error"]
    assert e["code"] == "CURVATURE_RATE_DISCONTINUITY"
    assert e["segment"] == 0


def test_rate_result_is_stable():
    payload = {"segments": [PIN_L, PIN_R], "max_curvature": 100.0,
               "max_curvature_rate": 50.0}
    assert audit(payload) == audit(payload)


def test_bad_max_curvature_rate():
    for bad in (0, -2.5, "fast", True, float("nan"), float("inf")):
        with pytest.raises(AuditInputError):
            audit({"segments": [ARC_L, ARC_R], "max_curvature": 1.0,
                   "max_curvature_rate": bad})
