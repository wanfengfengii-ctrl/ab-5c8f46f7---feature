"""Exact real-root isolation on the closed interval [0, 1].

The audit must find *every* stationary point of the squared-curvature
function and *every* zero of the speed polynomial within a segment;
discrete sampling is explicitly forbidden.

Method: Vincent-Descartes over dyadic intervals.  For a dyadic interval
``[A/W, B/W]`` with ``B = A + 1`` and ``W`` a power of two, the Möbius
substitution

    t = (A + B u) / (W (1 + u))

maps the *open* interval onto ``u in (0, +inf)`` and yields the integer
polynomial

    T(u) = sum_k p_k W^(n-k) (A + B u)^k (1 + u)^(n-k).

By Descartes' rule the sign-variation count of ``T`` bounds the number of
real roots of *p* inside that open interval (zero certifies "none"), so no
root can be missed without any sampling.  Endpoint roots appear exactly as:

* ``T(0) = 0``          -> root at A/W, factor u;
* ``deg T < n``         -> root at B/W, factor (1 + u)

(and are divided out exactly so each is reported once).  The two children
of a node are the dyadic intervals ``[2A, 2A+1] / 2W`` and
``[2A+1, 2A+2] / 2W``.  Vincent's theorem makes non-empty nodes converge to
count 1; multiple roots collapse to one report once the enclosing interval
is narrower than ``TOL``.  Root-count decisions use integer arithmetic
only.
"""

from __future__ import annotations

from fractions import Fraction
from typing import List, Sequence

# An enclosing dyadic interval narrower than this (in t) is taken as a
# single location.  1e-12 is far below engineering resolution.
TOL = Fraction(1, 10 ** 12)
MAX_DEPTH = 200


def strip(p: Sequence[int]) -> List[int]:
    """Drop leading zero coefficients (constant term first)."""
    q = [int(c) for c in p]
    while q and q[-1] == 0:
        q.pop()
    return q


def _mul(a: Sequence[int], b: Sequence[int]) -> List[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def _linear_power(n: int, a: int, b: int) -> List[int]:
    """Integer coefficients of (a + b u)^n."""
    choose = 1
    out = [0] * (n + 1)
    for k in range(n + 1):
        out[k] = choose * (a ** (n - k)) * (b ** k)
        choose = choose * (n - k) // (k + 1)
    return out


def variations(coeffs: Sequence[int]) -> int:
    """Sign-variation count, ignoring zero coefficients."""
    s = [1 if c > 0 else -1 for c in coeffs if c != 0]
    return sum(1 for i in range(1, len(s)) if s[i] != s[i - 1])


def moebius(p: Sequence[int], a: int, b: int, w: int) -> List[int]:
    """Polynomial of t = (a + b u)/(w(1 + u)), degree exactly n if p(b/w)!=0."""
    n = len(p) - 1
    result = [0] * (n + 1)
    one_plus = [1, 1]
    for k, c in enumerate(p):
        if c == 0:
            continue
        term = _mul(_linear_power(k, a, b), _linear_power(n - k, 1, 1))
        factor = int(c) * (w ** (n - k))
        for j, x in enumerate(term):
            result[j] += factor * x
    return result  # keep trailing zeros: they encode roots at u = infinity


def divide_by_u_minus_1(q: Sequence[int]) -> List[int]:
    """Synthetic division of *q* by (u - 1); requires q(1) = 0."""
    out = [0] * (len(q) - 1)
    out[-1] = q[-1]
    for i in range(len(q) - 2, 0, -1):
        out[i - 1] = q[i] + out[i]
    return out


def isolate_roots_01(p: Sequence[int]) -> List[Fraction]:
    """Isolate every real root of integer polynomial *p* in [0, 1].

    Returns sorted representative parameters (:class:`Fraction`).  Distinct
    roots more than ``TOL`` apart are reported separately; tighter
    clusters (including multiple roots) are coalesced.
    """
    p = strip(p)
    roots: List[Fraction] = []

    # Extract roots at the global endpoints t = 0 and t = 1 exactly.
    while len(p) > 1 and p[0] == 0:
        roots.append(Fraction(0))
        p = strip(p[1:])
    while len(p) >= 2 and sum(p) == 0:
        roots.append(Fraction(1))
        p = divide_by_u_minus_1(p)
    if not p or len(p) == 1:
        return sorted(set(roots))

    def walk(a: int, b: int, w: int, depth: int) -> None:
        q = strip(moebius(p, a, b, w))

        # Roots at this node's LEFT endpoint t = a/w appear as factor(s) u.
        # Internal split-point roots are reported here by the right child,
        # never twice.  (A root at the right endpoint maps to u = infinity,
        # i.e. a degree drop, which strip() removes without being counted.)
        while len(q) > 1 and q[0] == 0:
            roots.append(Fraction(a, w))
            q = strip(q[1:])

        if not q or len(q) == 1 or variations(q) == 0:
            return  # no root strictly inside (a/w, b/w)

        if depth >= MAX_DEPTH or Fraction(1, w) <= TOL:
            # One certified root, or a multiple-root cluster below TOL.
            roots.append(Fraction(a + b, 2 * w))
            return

        w2 = 2 * w
        walk(2 * a, 2 * a + 1, w2, depth + 1)   # left child
        walk(2 * a + 1, 2 * b, w2, depth + 1)   # right child

    walk(0, 1, 1, 0)
    return sorted(set(roots))


# --------------------------------------------------------------------------
# Exact polynomial algebra over Q (used to distinguish stationary points at
# which the speed is zero from genuine curvature extrema).
# --------------------------------------------------------------------------

def _fractions(p: Sequence) -> List[Fraction]:
    return [Fraction(c) for c in p]


def _strip_fractions(p: Sequence[Fraction]) -> List[Fraction]:
    q = [Fraction(c) for c in p]
    while q and q[-1] == 0:
        q.pop()
    return q or [Fraction(0)]


def _poly_mod(a: List[Fraction], b: List[Fraction]) -> List[Fraction]:
    """Remainder of rational polynomials a mod b (b non-zero)."""
    r = [Fraction(c) for c in a]
    db = len(b) - 1
    while len(r) - 1 >= db and not (len(r) == 1 and r[0] == 0):
        q = r[-1] / b[-1]
        sh = len(r) - 1 - db
        for i in range(len(b)):
            r[sh + i] -= q * b[i]
        r = _strip_fractions(r)
    return r


def _gcd_fractions(a: Sequence, b: Sequence) -> List[Fraction]:
    """Monic GCD of rational/integer polynomials over Q."""
    x = _strip_fractions(_fractions(a))
    y = _strip_fractions(_fractions(b))
    while y != [Fraction(0)]:
        x, y = y, _poly_mod(x, y)
    lc = x[-1]
    return [c / lc for c in x]


def _exact_divide(a: Sequence[Fraction], b: Sequence[Fraction]) -> List[Fraction]:
    """Exact polynomial division a / b over Q."""
    a = _strip_fractions(a)
    b = _strip_fractions(b)
    out = [Fraction(0)] * (len(a) - len(b) + 1)
    rem = [Fraction(c) for c in a]
    for i in range(len(out) - 1, -1, -1):
        q = rem[i + len(b) - 1] / b[-1]
        out[i] = q
        for j in range(len(b)):
            rem[i + j] -= q * b[j]
    return _strip_fractions(out)


def _to_integer_poly(p: Sequence[Fraction]) -> List[int]:
    """Scale a rational polynomial up to primitive integer coefficients."""
    from math import gcd
    q = _strip_fractions(p)
    den_lcm = 1
    for c in q:
        den_lcm = den_lcm * c.denominator // gcd(den_lcm, c.denominator)
    ints = [int(c * den_lcm) for c in q]
    g = 0
    for v in ints:
        g = gcd(g, abs(v))
    if g:
        ints = [v // g for v in ints]
    if ints and ints[-1] < 0:
        ints = [-v for v in ints]
    return ints


def squarefree_part(p: Sequence[int]) -> List[int]:
    """Primitive integer polynomial carrying each distinct root of p once."""
    a = _strip_fractions(_fractions(strip(p)))
    if len(a) <= 1:
        return _to_integer_poly(a)
    dp = [Fraction(i) * a[i] for i in range(1, len(a))]
    g = _gcd_fractions(a, dp)
    return _to_integer_poly(_exact_divide(a, g))


def gcd_integer_poly(a: Sequence[int], b: Sequence[int]) -> List[int]:
    """Primitive integer GCD of two integer polynomials (1 if coprime)."""
    return _to_integer_poly(_gcd_fractions(strip(a), strip(b)))


def roots_not_shared(p: Sequence[int], q: Sequence[int]) -> List[int]:
    """Integer polynomial carrying the simple roots of *p* not shared by *q*.

    Both inputs are reduced to square-free parts first, so no shared root
    survives through multiplicity.  Used to remove zero-speed parameters
    from the set of curvature-stationary parameters exactly.
    """
    sf_p = squarefree_part(p)
    sf_q = squarefree_part(q)
    shared = gcd_integer_poly(sf_p, sf_q)
    if len(shared) == 1 and abs(shared[0]) == 1:
        return sf_p  # no shared root
    return _to_integer_poly(
        _exact_divide(_fractions(sf_p), _fractions(shared))
    )
