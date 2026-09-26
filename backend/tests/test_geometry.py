"""Tests for cubic-Bezier segment geometry and exact curvature."""

from fractions import Fraction
from math import isclose, sqrt

from app.geometry import Segment

HAIRPIN = ((0, 0), (10, 0), (0, 1), (10, 1))
ZERO_LOOP = ((0, 0), (1, 0), (-1, 0), (0, 0))


def test_tangent_endpoints():
    seg = Segment(HAIRPIN)
    # P'(0) = 3(P1-P0) = (30, 0);  P'(1) = 3(P3-P2) = (30, 0)
    assert seg.tangent(Fraction(0)) == (30, 0)
    assert seg.tangent(Fraction(1)) == (30, 0)


def test_zero_speed_detected_in_interior():
    seg = Segment(ZERO_LOOP)
    roots = sorted(float(t) for t in seg.zero_speed_params() if 0 < float(t) < 1)
    # v(t) = 3(1 - 6t + 6t^2, 0), roots (3 +/- sqrt(3))/6
    assert len(roots) == 2
    assert isclose(roots[0], (3 - sqrt(3)) / 6, abs_tol=1e-9)
    assert isclose(roots[1], (3 + sqrt(3)) / 6, abs_tol=1e-9)


def test_curvature_stationary_excludes_zero_speed():
    # The loop has interior cusp(s); no stationary parameter may coincide
    # with a zero-speed root (exact GCD removal).
    seg = Segment(ZERO_LOOP)
    zero = set(seg.zero_speed_params())
    stat = set(seg.curvature_stationary_params())
    assert zero & stat == set()


def test_hairpin_extremum_matches_dense_reference():
    # Independently computed by dense float scan: 6.423731 near 0.423592.
    seg = Segment(HAIRPIN)
    best = 0.0
    best_t = None
    for t in [Fraction(0), Fraction(1)] + seg.curvature_stationary_params():
        if seg.speed_squared(t) <= 0:
            continue
        k = sqrt(float(seg.curvature_squared(t)))
        if k > best:
            best, best_t = k, float(t)
    assert isclose(best, 6.423730581017, abs_tol=1e-7)
    assert isclose(best_t, 0.4235922886, abs_tol=1e-8)


def test_endpoint_curvature_straight_segment_is_zero():
    seg = Segment(((0, 0), (1, 0), (2, 0), (3, 0)))
    assert seg.curvature_squared(Fraction(0)) == 0
    assert seg.curvature_squared(Fraction(1)) == 0
    assert seg.curvature_stationary_params() == []


def test_position_exact():
    seg = Segment(((0, 0), (0, 0), (1, 1), (1, 1)))
    x, y = seg.position(Fraction(1, 2))
    # midpoint = (1/8 P1 + 3/8 P2 ...) standard: (0.5, 0.5)
    assert isclose(float(x), 0.5) and isclose(float(y), 0.5)
