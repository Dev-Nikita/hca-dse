"""Quality metrics: Pareto recall/precision, hypervolume, IGD+."""
from __future__ import annotations
from typing import List, Tuple
import numpy as np


def objset(front) -> set:
    return {tuple(round(v, 9) for v in f) for _, f in front}


def recall(front, ref) -> float:
    R, P = objset(ref), objset(front)
    return len(R & P) / len(R) if R else float("nan")


def precision(front, ref) -> float:
    R, P = objset(ref), objset(front)
    return len(R & P) / len(P) if P else float("nan")


def _norm(F: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    span = np.where(hi - lo == 0, 1.0, hi - lo)
    return (F - lo) / span


def hypervolume(front, lo, hi, ref_point=1.1) -> float:
    from pymoo.indicators.hv import HV
    if not front:
        return 0.0
    F = _norm(np.array([f for _, f in front], float), lo, hi)
    F = F[np.all(np.isfinite(F), axis=1)]
    if len(F) == 0:
        return 0.0
    return float(HV(ref_point=np.full(F.shape[1], ref_point))(F))


def igd_plus(front, ref, lo, hi) -> float:
    from pymoo.indicators.igd_plus import IGDPlus
    if not front:
        return float("inf")
    A = _norm(np.array([f for _, f in front], float), lo, hi)
    R = _norm(np.array([f for _, f in ref], float), lo, hi)
    return float(IGDPlus(R)(A))


def bounds_from(*fronts):
    F = np.array([f for fr in fronts for _, f in fr], float)
    F = F[np.all(np.isfinite(F), axis=1)]
    return F.min(axis=0), F.max(axis=0)
