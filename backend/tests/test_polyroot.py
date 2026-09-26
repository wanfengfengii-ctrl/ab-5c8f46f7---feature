"""Tests for exact root isolation and rational polynomial algebra."""

from fractions import Fraction

from app.polyroot import (
    gcd_integer_poly,
    isolate_roots_01,
    roots_not_shared,
    squarefree_part,
)


def approx_set(roots, expected):
    roots = sorted(float(r) for r in roots)
    assert len(roots) == len(expected)
    for got, want in zip(roots, sorted(expected)):
        assert abs(got - want) < 1e-9


def test_endpoint_roots():
    assert isolate_roots_01([0, 0, 1]) == [Fraction(0)]          # t^2
    assert isolate_roots_01([-1, 2, -1]) == [Fraction(1)]        # -(t-1)^2
    approx_set(isolate_roots_01([0, -1, 1]), [0.0, 1.0])         # t(t-1)


def test_interior_roots():
    approx_set(isolate_roots_01([2, -9, 9]), [1 / 3, 2 / 3])
    # (t - 1/5)(t - 1/2)^2
    approx_set(isolate_roots_01([-1, 9, -24, 20]), [0.2, 0.5])


def test_no_roots():
    assert isolate_roots_01([1, 0, 1]) == []
    assert isolate_roots_01([5]) == []


def test_constructed_polynomials():
    """Every constructed root in (0,1) must be isolated exactly once."""
    import random
    from fractions import Fraction as Fr

    def from_roots(roots):
        p = [1]
        for r in roots:
            a, b = r.numerator, r.denominator
            q = [0] * (len(p) + 1)
            for i, c in enumerate(p):
                q[i] += -a * c
                q[i + 1] += b * c
            p = q
        return p

    rng = random.Random(1234)
    for _ in range(300):
        k = rng.randint(1, 7)
        roots = set()
        while len(roots) < k:
            a = rng.randint(1, 9)
            d = rng.randint(a + 1, 20)
            roots.add(Fr(a, d))
        roots = list(roots)
        got = isolate_roots_01(from_roots(roots))
        assert len(got) == len(roots)
        for g in got:
            assert min(abs(g - r) for r in roots) < 1e-9


def test_gcd():
    # (t-1)(t-2) and (t-1)(t-3)
    assert gcd_integer_poly([2, -3, 1], [3, -4, 1]) == [-1, 1]
    assert gcd_integer_poly([1, 0, 1], [1, 0, 0, 1]) == [1] or \
        gcd_integer_poly([1, 0, 1], [1, 0, 0, 1]) == [-1]


def test_squarefree():
    # (t-1)^2(t-2) -> (t-1)(t-2)
    assert squarefree_part([-2, 5, -4, 1]) == [2, -3, 1]


def test_roots_not_shared_with_multiplicity():
    from fractions import Fraction as Fr

    def from_roots(roots):
        p = [1]
        for r in roots:
            a, b = r.numerator, r.denominator
            q = [0] * (len(p) + 1)
            for i, c in enumerate(p):
                q[i] += -a * c
                q[i + 1] += b * c
            p = q
        from app.polyroot import _to_integer_poly
        return _to_integer_poly(p)

    p = from_roots([Fr(1, 2), Fr(1, 2), Fr(1, 2), Fr(1, 5)])
    q = from_roots([Fr(1, 2)])
    # The triple root 1/2 is shared (and must be removed despite different
    # multiplicities); only 1/5 remains.
    assert roots_not_shared(p, q) == [-1, 5] or \
        roots_not_shared(p, q) == [1, -5]
