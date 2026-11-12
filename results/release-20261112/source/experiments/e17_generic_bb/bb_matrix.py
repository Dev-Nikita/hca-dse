"""E17: is the result explained by a generic branch-and-bound?

Six configurations, identical in every respect except the bounds they use and,
for G4, the traversal order.  Feasibility pruning, dominance pruning, the
certified archive, the evaluator and the variable order are shared, so a
difference between two rows is a difference between two bounds.

  G0  exhaustive enumeration (the oracle)
  G1  generic branch-and-bound: the assignment-monotone partial-cost bound
  G2m HCA-DSE with the contention term bounded by zero everywhere
  G2  HCA-DSE as published
  G3  HCA-DSE plus the positive waiting bound for undetermined tiers
  G4  G3 under the determinants-early order O2

Reported per configuration: evaluator calls, expanded prefix states, bound
calls, wall-clock, peak memory, and whether the returned front equals the
exhaustive front.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import statistics
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bounders import (CachedPartialCostBounder, PartialCostBounder,
                      PositiveQueueBounder)

from hcadse import search as search_mod
from hcadse.bounder import Bounder
from hcadse.metrics import objset
from hcadse.model import WORKLOADS, make_space
from hcadse.search import exhaustive, hca_dse

# the paper's O1: determinants of contention assigned late
O1 = ["n_e", "edge_cls", "n_g", "gw_cls", "link_cls", "cloud_cls", "rep", "policy"]

CONFIGS = (
    ("G1", PartialCostBounder, dict(), "generic B&B, partial-cost bound"),
    ("G1c", CachedPartialCostBounder, dict(),
     "generic B&B, same two-stage protocol and caching"),
    ("G2m", Bounder, dict(use_queue_bound=False), "HCA-DSE, contention term zeroed"),
    ("G2", Bounder, dict(), "HCA-DSE as published"),
    ("G3", PositiveQueueBounder, dict(), "HCA-DSE + positive waiting bound"),
    ("G4", PositiveQueueBounder, dict(variable_order=O1), "G3 under the determinants-late order"),
)


def run_one(bounder, space, wl, kwargs, repeats=3):
    """Timed runs carry no instrumentation; memory is measured in its own run.

    Measuring wall-clock under tracemalloc inflates every configuration several
    times over and is not comparable with the benchmark tables of Section 6, so
    the two measurements are taken separately and reported separately.
    """
    original = search_mod.Bounder
    search_mod.Bounder = bounder
    try:
        walls, evals_t = [], []
        stats = None
        for _ in range(repeats):
            t0 = time.perf_counter()
            stats = hca_dse(space, wl, **kwargs)
            walls.append(time.perf_counter() - t0)
            evals_t.append(stats.t_eval)
        tracemalloc.start()
        try:
            hca_dse(space, wl, **kwargs)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
    finally:
        search_mod.Bounder = original
    return stats, statistics.median(walls), min(walls), peak, statistics.median(evals_t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2,S3")
    ap.add_argument("--out", default="results/e17_generic_bb")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for scale in a.scales.split(","):
        for wname, wl in WORKLOADS.items():
            space = make_space(scale)
            walls, exh_evals_t = [], []
            for _ in range(3):
                t0 = time.perf_counter()
                oracle = exhaustive(space, wl)
                walls.append(time.perf_counter() - t0)
                exh_evals_t.append(oracle.t_eval)
            exh_wall = statistics.median(walls)
            exh_eval_t = statistics.median(exh_evals_t)
            exh_best = min(walls)
            tracemalloc.start()
            exhaustive(space, wl)
            exh_peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            reference = objset(oracle.front)
            rows.append(dict(scale=scale, workload=wname, config="G0",
                             label="exhaustive oracle", evals=oracle.n_evaluated,
                             nodes=oracle.n_evaluated, bound_calls=0,
                             seconds=round(exh_wall, 4), best_seconds=round(exh_best, 4),
                             eval_seconds=round(exh_eval_t, 5),
                             overhead_seconds=round(exh_wall - exh_eval_t, 5),
                             peak_kib=round(exh_peak / 1024),
                             front=len(reference), exact=True))
            print(json.dumps(rows[-1]), flush=True)
            for name, bounder, kwargs, label in CONFIGS:
                stats, wall, best, peak, eval_t = run_one(bounder, space, wl, kwargs)
                same = objset(stats.front) == reference
                rows.append(dict(scale=scale, workload=wname, config=name, label=label,
                                 evals=stats.n_evaluated, nodes=stats.n_nodes,
                                 bound_calls=stats.n_bound_calls,
                                 seconds=round(wall, 4), best_seconds=round(best, 4),
                                 eval_seconds=round(eval_t, 5),
                                 overhead_seconds=round(wall - eval_t, 5),
                                 peak_kib=round(peak / 1024),
                                 front=len(objset(stats.front)), exact=bool(same)))
                print(json.dumps(rows[-1]), flush=True)
                assert same, ("front differs from the oracle", scale, wname, name)

    keys = list(rows[0])
    with (out / "bb_matrix.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print("wrote", out / "bb_matrix.csv")


if __name__ == "__main__":
    main()
