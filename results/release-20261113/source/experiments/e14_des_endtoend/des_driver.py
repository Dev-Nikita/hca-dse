"""Search with the discrete-event simulator as the leaf evaluator.

Three protocols are measured against the same ground truth:

  EXH-DES   exhaustive enumeration, every structurally valid design simulated.
            The reference Pareto front at the simulator's level of detail.

  INLINE    HCA-DSE with the simulator in the inner loop.  The admissible
            bounds are derived for the analytical model, so with a simulated
            leaf the pruning carries no guarantee; the point is to measure what
            it costs and what it loses.

  TWO-LEVEL the workflow the manuscript actually recommends: search on the
            analytical model, then re-evaluate only the surviving front with
            the simulator.  Cheap, and the honest candidate for practice.

Energy, cost and network volume stay analytical: the simulator reports latency
only.  Feasibility uses the simulated latency for the deadline and the
analytical model for every other constraint.  Each design is simulated with a
fixed seed set, so a design has the same value in every protocol.
"""
from __future__ import annotations

import argparse, json, os, statistics, sys, time
from dataclasses import dataclass
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.setrecursionlimit(10000)

from hcadse import search as search_mod
from hcadse.evaluate import Result, evaluate as analytic_evaluate
from hcadse.model import WORKLOADS, make_space
from hcadse.search import pareto_front
from hcadse.simulate import simulate

INF = float("inf")
N_REQ = 3000          # the configuration the reported simulator timing used
WARMUP = 400


@dataclass
class Counter:
    sim_runs: int = 0
    sim_seconds: float = 0.0

    def reset(self):
        self.sim_runs = 0
        self.sim_seconds = 0.0


COUNT = Counter()


_ALL = []


def des_evaluate(x: dict, wl, seeds: Tuple[int, ...], record=False) -> Result:
    base = analytic_evaluate(x, wl)
    t0 = time.perf_counter()
    means = [simulate(x, wl, n_req=N_REQ, warmup=WARMUP, seed=sd)["mean"] for sd in seeds]
    COUNT.sim_runs += len(seeds)
    COUNT.sim_seconds += time.perf_counter() - t0
    L = statistics.median(means)
    viol = tuple(v for v in base.violations if v != "deadline")
    if not (L < INF) or L > wl.deadline:
        viol = viol + ("deadline",)
    r = Result((L,) + base.objectives[1:], not viol, base.rho, viol)
    if record:
        # Record the complete structurally valid universe, including designs
        # rejected by either evaluator.  The screening decision must be made
        # from analytical values alone; DES feasibility is used only later to
        # score the already fixed selection against exhaustive DES ground truth.
        _ALL.append((dict(x), r))
    return r


def key(x):
    return tuple(sorted((k, getattr(v, "name", v)) for k, v in x.items()))


def keyset(front):
    return {key(x) for x, _ in front}


def gap_to(front_objs, f):
    """Smallest max-relative difference from f to any point of the front."""
    best = INF
    for g in front_objs:
        d = max(abs(a - b) / max(abs(b), 1e-12) for a, b in zip(f, g))
        best = min(best, d)
    return best


def run(scale: str, workload: str, seeds: Tuple[int, ...]):
    wl = WORKLOADS[workload]
    sp = make_space(scale)
    out = {"scale": scale, "workload": workload, "seeds": list(seeds),
           "n_req": N_REQ, "warmup": WARMUP, "space": sp.size}
    original = search_mod.evaluate

    # ---- TWO-LEVEL: analytical search, then simulate the survivors ---------
    t0 = time.perf_counter()
    a = search_mod.hca_dse(sp, wl)
    out["analytic_wall"] = time.perf_counter() - t0
    out["analytic_evals"] = a.n_evaluated
    COUNT.reset()
    t0 = time.perf_counter()
    two = [(x, des_evaluate(x, wl, seeds).objectives) for x, _ in a.front]
    two = pareto_front([(x, f) for x, f in two if all(v < INF for v in f)])
    out["twolevel_wall"] = out["analytic_wall"] + (time.perf_counter() - t0)
    out["twolevel_sim_runs"] = COUNT.sim_runs
    out["twolevel_front_size"] = len(two)

    # ---- INLINE: the simulator inside the search ---------------------------
    search_mod.evaluate = lambda x, w: des_evaluate(x, w, seeds)
    try:
        COUNT.reset()
        t0 = time.perf_counter()
        h = search_mod.hca_dse(sp, wl)
        out["inline_wall"] = time.perf_counter() - t0
        out["inline_evals"] = h.n_evaluated
        out["inline_sim_runs"] = COUNT.sim_runs
        out["inline_front_size"] = len(h.front)

        # ---- EXH-DES: the reference -------------------------------------
        COUNT.reset()
        _ALL.clear()
        search_mod.evaluate = lambda x, w: des_evaluate(x, w, seeds, record=True)
        t0 = time.perf_counter()
        e = search_mod.exhaustive(sp, wl)
        out["exh_wall"] = time.perf_counter() - t0
        out["exh_evals"] = e.n_evaluated
        out["exh_sim_runs"] = COUNT.sim_runs
        out["exh_front_size"] = len(e.front)
        out["_dump"] = []
        for x, des_r in _ALL:
            an_r = analytic_evaluate(x, wl)
            out["_dump"].append({"design": dict(key(x)),
                                 "des": [float(v) for v in des_r.objectives],
                                 "des_feasible": bool(des_r.feasible),
                                 "des_violations": list(des_r.violations),
                                 "analytic": [float(v) for v in an_r.objectives],
                                 "analytic_feasible": bool(an_r.feasible),
                                 "analytic_violations": list(an_r.violations)})
    finally:
        search_mod.evaluate = original

    ref, refk = e.front, keyset(e.front)
    ref_objs = [f for _, f in ref]
    for tag, front, wall in (("inline", h.front, out["inline_wall"]),
                             ("twolevel", two, out["twolevel_wall"])):
        fk = keyset(front)
        hit = fk & refk
        out[tag + "_recall"] = len(hit) / max(len(refk), 1)
        out[tag + "_front_equal"] = fk == refk
        out[tag + "_speedup_wall"] = out["exh_wall"] / wall
        missed = [f for x, f in ref if key(x) not in fk]
        gaps = [gap_to([f for _, f in front], f) for f in missed] if front else []
        out[tag + "_missed"] = len(missed)
        out[tag + "_missed_gap_max"] = max(gaps) if gaps else 0.0
        out[tag + "_missed_gap_median"] = statistics.median(gaps) if gaps else 0.0
        out[tag + "_missed_within_1pct"] = sum(1 for g in gaps if g <= 0.01)
        out[tag + "_missed_within_5pct"] = sum(1 for g in gaps if g <= 0.05)
        out[tag + "_missed_detail"] = [
            {"design": dict(key(x)), "objectives": [round(v, 6) for v in f],
             "gap": round(g, 4)}
            for (x, f), g in zip([(x, f) for x, f in ref if key(x) not in fk], gaps)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", required=True)
    ap.add_argument("--workload", required=True)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = run(a.scale, a.workload, tuple(int(s) for s in a.seeds.split(",")))
    with open(a.out, "w") as f:
        json.dump(r, f, indent=2, default=str)
    brief = {k: v for k, v in r.items() if not k.endswith("_detail") and k != "_dump"}
    print(json.dumps(brief, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
