"""Polynomial helpers and exact cubic-Bezier segment geometry.

Everything is derived from *integer* control points, so every polynomial
coefficient below (velocity, speed-squared, cross product, squared
curvature numerator/denominator and the stationary-point polynomial) is an
exact integer.  Curvature comparisons can therefore be made with exact
rational arithmetic instead of sampled floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import List, Sequence, Tuple

from .polyroot import isolate_roots_01, roots_not_shared, squarefree_part

Point = Tuple[int, int]
Vec2 = Tuple[int, int]


def poly_mul(a: Sequence[int], b: Sequence[int]) -> List[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def poly_der(p: Sequence[int]) -> List[int]:
    return [i * p[i] for i in range(1, len(p))]


def poly_strip(p: Sequence[int]) -> List[int]:
    q = list(p)
    while q and q[-1] == 0:
        q.pop()
    return q


def poly_eval(p: Sequence[int], t: Fraction) -> Fraction:
    r = Fraction(0)
    for c in reversed(p):
        r = r * t + c
    return r


@dataclass(frozen=True)
class Segment:
    """One cubic Bezier segment with integer control points P0..P3."""

    points: Tuple[Point, Point, Point, Point]

    def _coeffs(self, axis: int) -> List[int]:
        p = [pt[axis] for pt in self.points]
        # Cubic power basis  c0 + c1 t + c2 t^2 + c3 t^3
        return [
            p[0],
            3 * (p[1] - p[0]),
            3 * (p[0] - 2 * p[1] + p[2]),
            -p[0] + 3 * p[1] - 3 * p[2] + p[3],
        ]

    def __post_init__(self) -> None:
        cx = self._coeffs(0)
        cy = self._coeffs(1)
        # Velocity (degree 2) and acceleration (degree 1).
        vx = poly_der(cx)
        vy = poly_der(cy)
        ax = poly_der(vx)
        ay = poly_der(vy)

        s2 = poly_strip([a + b for a, b in
                         zip(poly_mul(vx, vx), poly_mul(vy, vy))])
        cross = poly_strip([
            a - b for a, b in zip(poly_mul(vx, ay), poly_mul(vy, ax))
        ])
        num = poly_mul(cross, cross)          # |v x a|^2, degree 6
        den = poly_mul(poly_mul(s2, s2), s2)  # |v|^6,        degree 12
        if num and den:
            stationary = poly_strip([
                a - b for a, b in zip(
                    poly_mul(poly_der(num), den),
                    poly_mul(num, poly_der(den)),
                )
            ])
        else:
            stationary = []

        object.__setattr__(self, "cx", cx)
        object.__setattr__(self, "cy", cy)
        object.__setattr__(self, "vx", vx)
        object.__setattr__(self, "vy", vy)
        object.__setattr__(self, "speed2", s2)
        object.__setattr__(self, "k_num", num)
        object.__setattr__(self, "k_den", den)
        object.__setattr__(self, "stationary", stationary)

    # -- exact evaluations -------------------------------------------------

    def position(self, t: Fraction) -> Tuple[Fraction, Fraction]:
        u = 1 - t
        basis = (u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3)
        px = sum(b * Fraction(p[0]) for b, p in zip(basis, self.points))
        py = sum(b * Fraction(p[1]) for b, p in zip(basis, self.points))
        return px, py

    def tangent(self, t: Fraction) -> Tuple[Fraction, Fraction]:
        return poly_eval(self.vx, t), poly_eval(self.vy, t)

    def speed_squared(self, t: Fraction) -> Fraction:
        return poly_eval(self.speed2, t) if self.speed2 else Fraction(0)

    def curvature_squared(self, t: Fraction) -> Fraction:
        """Exact kappa^2 = |v x a|^2 / |v|^6; undefined at zero velocity."""
        return poly_eval(self.k_num, t) / poly_eval(self.k_den, t)

    # -- root isolation -----------------------------------------------------

    def zero_speed_params(self) -> List[Fraction]:
        """Distinct parameters in [0, 1] where the tangent vector vanishes."""
        if not self.speed2:
            return []
        return isolate_roots_01(squarefree_part(self.speed2))

    def curvature_stationary_params(self) -> List[Fraction]:
        """Parameters in [0, 1] with d(kappa^2)/dt = 0 and non-zero speed.

        Stationary parameters that coincide exactly with a zero-speed root
        (where curvature is undefined, not extremal) are removed by exact
        square-free GCD rather than a numeric proximity test.
        """
        if not self.stationary or not self.speed2:
            return []
        return isolate_roots_01(
            roots_not_shared(self.stationary, self.speed2)
        )
