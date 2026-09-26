"""Splice audit for 2..5 cubic-Bezier segments.

Checks, in strict travel order so that the *earliest* problem is reported:

1. junction position continuity  P3_i == P0_{i+1};
2. junction first-derivative (tangent vector) continuity;
3. zero tangent vectors are non-runnable (at every endpoint and at every
   exact interior root of the speed-squared polynomial);
4. curvature continuity across junctions (exact rational comparison);
5. curvature against the unified maximum at every segment endpoint and at
   every stationary point of d(kappa^2)/dt -- all of them, never a discrete
   sample.

All geometry comes from integer control points, and every comparison is
made on exact rational values; only the final report values are converted
to floats for JSON.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

from .geometry import Segment


class AuditInputError(ValueError):
    """Raised when the request body is structurally invalid."""


def _point(p: Any) -> Tuple[int, int]:
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise AuditInputError("每个控制点必须是 [x, y]")
    x, y = p
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) \
            or not isinstance(y, int):
        raise AuditInputError("控制点坐标必须为整数")
    return int(x), int(y)


def build_segments(payload: Dict[str, Any]) -> Tuple[List[Segment], float]:
    raw = payload.get("segments")
    if not isinstance(raw, list) or not (2 <= len(raw) <= 5):
        raise AuditInputError("曲线段数必须为 2 至 5 段")
    segments: List[Segment] = []
    for i, seg in enumerate(raw):
        if not isinstance(seg, dict):
            raise AuditInputError(f"第 {i + 1} 段格式无效")
        pts = seg.get("points")
        if not isinstance(pts, list) or len(pts) != 4:
            raise AuditInputError(f"第 {i + 1} 段必须含 4 个控制点")
        points = tuple(_point(p) for p in pts)
        segments.append(Segment(points))  # type: ignore[arg-type]

    kmax = payload.get("max_curvature")
    if isinstance(kmax, bool) or not isinstance(kmax, (int, float)):
        raise AuditInputError("最大曲率必须为正数")
    kmax = float(kmax)
    if not (kmax > 0.0) or kmax != kmax or kmax == float("inf"):
        raise AuditInputError("最大曲率必须为有限正数")
    return segments, kmax


def _f(value: Fraction) -> float:
    return float(value)


def _error(code: str, message: str, segment: int, t: Any,
           point: Any, **details: Any) -> Dict[str, Any]:
    err: Dict[str, Any] = {
        "code": code,
        "message": message,
        "segment": segment,
        "parameter": None if t is None else (float(t) if not isinstance(t, float) else t),
        "point": point,
    }
    err.update(details)
    return err


def audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    segments, kmax = build_segments(payload)
    n = len(segments)
    # Fraction(str(float)) captures the exact decimal the engineer typed,
    # so the curvature comparison is exact rational arithmetic.
    limit2 = Fraction(str(kmax)) ** 2

    def curvature_violation(seg_idx: int, t: Fraction,
                            seg: Segment) -> Optional[Dict[str, Any]]:
        k2 = seg.curvature_squared(t)
        if k2 > limit2:
            x, y = seg.position(t)
            return _error(
                "CURVATURE_EXCEEDED",
                f"第 {seg_idx + 1} 段 t={float(t):.6f} 处曲率 "
                f"{_f(k2) ** 0.5:.6g} 超过最大曲率 {kmax:.6g}",
                seg_idx, t, [_f(x), _f(y)],
                curvature=_f(k2) ** 0.5,
                max_curvature=kmax,
            )
        return None

    # ---- travel-order scan -------------------------------------------------
    for i, seg in enumerate(segments):
        # Start endpoint t = 0 (only an independent physical point for seg 0;
        # for other segments it is the junction handled at the previous end).
        if i == 0:
            vx, vy = seg.tangent(Fraction(0))
            if vx == 0 and vy == 0:
                x, y = seg.position(Fraction(0))
                return _fail(_error(
                    "ZERO_TANGENT",
                    f"第 1 段起点 t=0 处切向量为零，曲线不可运行",
                    0, 0.0, [_f(x), _f(y)],
                    tangent=[0, 0],
                ), segments, kmax)
            problem = curvature_violation(0, Fraction(0), seg)
            if problem:
                return _fail(problem, segments, kmax)

        # Interior candidate locations in travel order: stationary points
        # of kappa^2 (at non-zero speed, proven by square-free GCD) and the
        # exact roots of the speed-squared polynomial.  All are found by
        # exact root isolation, never sampling.
        stationary = {t for t in seg.curvature_stationary_params()
                      if 0 < t < 1}
        zero_roots = {t for t in seg.zero_speed_params() if 0 < t < 1}
        candidates = sorted(stationary | zero_roots)

        for t in candidates:
            x, y = seg.position(t)
            if t in zero_roots:
                return _fail(_error(
                    "ZERO_TANGENT",
                    f"第 {i + 1} 段 t={float(t):.6f} 处切向量为零，"
                    f"曲线不可运行",
                    i, t, [_f(x), _f(y)], tangent=[0, 0],
                ), segments, kmax)
            problem = curvature_violation(i, t, seg)
            if problem:
                return _fail(problem, segments, kmax)

        # End endpoint t = 1.
        vx_end, vy_end = seg.tangent(Fraction(1))
        if vx_end == 0 and vy_end == 0:
            x, y = seg.position(Fraction(1))
            return _fail(_error(
                "ZERO_TANGENT",
                f"第 {i + 1} 段终点 t=1 处切向量为零，曲线不可运行",
                i, 1.0, [_f(x), _f(y)], tangent=[0, 0],
            ), segments, kmax)

        if i < n - 1:
            nxt = segments[i + 1]
            end = seg.points[3]
            start = nxt.points[0]

            # 1. position continuity
            if end != start:
                return _fail(_error(
                    "POSITION_DISCONTINUITY",
                    f"第 {i + 1} 段终点 {list(end)} 与第 {i + 2} 段起点 "
                    f"{list(start)} 不重合",
                    i, 1.0, list(end),
                    point_end=list(end), point_next=list(start),
                ), segments, kmax)

            # 2. first-derivative (tangent vector) continuity
            t_end = seg.tangent(Fraction(1))
            t_start = nxt.tangent(Fraction(0))
            if (t_start[0] == 0 and t_start[1] == 0) or \
               (t_end[0] == 0 and t_end[1] == 0):
                # covered by the zero-tangent checks above/below; defensive
                x, y = seg.position(Fraction(1))
                return _fail(_error(
                    "ZERO_TANGENT",
                    f"第 {i + 1}/{i + 2} 段拼接点切向量为零，曲线不可运行",
                    i, 1.0, [_f(x), _f(y)], tangent=[0, 0],
                ), segments, kmax)
            if t_end != t_start:
                x, y = seg.position(Fraction(1))
                return _fail(_error(
                    "TANGENT_DISCONTINUITY",
                    f"第 {i + 1} 段末端切向量 ({t_end[0]}, {t_end[1]}) 与第 "
                    f"{i + 2} 段首端切向量 ({t_start[0]}, {t_start[1]}) "
                    f"不一致",
                    i, 1.0, [_f(x), _f(y)],
                    tangent_end=[t_end[0], t_end[1]],
                    tangent_start=[t_start[0], t_start[1]],
                ), segments, kmax)

            # 3. curvature continuity at the shared endpoint
            k_end = seg.curvature_squared(Fraction(1))
            k_start = nxt.curvature_squared(Fraction(0))
            if k_end != k_start:
                x, y = seg.position(Fraction(1))
                return _fail(_error(
                    "CURVATURE_DISCONTINUITY",
                    f"拼接点处曲率不连续：第 {i + 1} 段末端 "
                    f"{_f(k_end) ** 0.5:.6g}，第 {i + 2} 段首端 "
                    f"{_f(k_start) ** 0.5:.6g}",
                    i, 1.0, [_f(x), _f(y)],
                    curvature_end=_f(k_end) ** 0.5,
                    curvature_start=_f(k_start) ** 0.5,
                ), segments, kmax)

        # Curvature limit at this physical endpoint (same value as the next
        # segment's start once continuity has passed).
        problem = curvature_violation(i, Fraction(1), seg)
        if problem:
            return _fail(problem, segments, kmax)

    return {
        "ok": True,
        "max_curvature": kmax,
        "error": None,
        "segments": [segment_summary(i, seg) for i, seg in enumerate(segments)],
    }


def _fail(error: Dict[str, Any], segments: List[Segment],
          kmax: float) -> Dict[str, Any]:
    idx = error.get("segment")
    if isinstance(idx, int) and 0 <= idx < len(segments):
        error["control_points"] = [list(p) for p in segments[idx].points]
        if error.get("code") in {
            "POSITION_DISCONTINUITY", "TANGENT_DISCONTINUITY",
            "CURVATURE_DISCONTINUITY",
        } and idx + 1 < len(segments):
            error["next_control_points"] = [
                list(p) for p in segments[idx + 1].points]
    return {"ok": False, "max_curvature": kmax, "error": error,
            "segments": []}


def segment_summary(index: int, seg: Segment) -> Dict[str, Any]:
    """Maximum curvature of one segment over endpoints + stationary points."""
    candidates = {Fraction(0), Fraction(1)}
    for t in seg.curvature_stationary_params():
        if 0 <= t <= 1 and seg.speed_squared(t) > 0:
            candidates.add(t)
    best_t = Fraction(0)
    best_k2 = seg.curvature_squared(Fraction(0))
    for t in candidates:
        if seg.speed_squared(t) <= 0:
            continue
        k2 = seg.curvature_squared(t)
        if k2 > best_k2:
            best_k2, best_t = k2, t
    x, y = seg.position(best_t)
    return {
        "index": index,
        "max_curvature": _f(best_k2) ** 0.5,
        "location": {"t": _f(best_t), "x": _f(x), "y": _f(y)},
    }
