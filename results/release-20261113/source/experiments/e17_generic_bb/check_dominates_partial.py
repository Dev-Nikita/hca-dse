"""Check, for every structurally valid prefix, that the bound of Section 4 is at
least the assignment-monotone partial cost in every objective (both the
certified intervals and the fast proposals), up to a relative rounding tolerance
of 1e-12; the largest relative excess is recorded.  Prefixes whose determined tier is
unstable are skipped: both bounds then prune by feasibility.
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bounders import CachedPartialCostBounder
from hcadse.bounder import Bounder
from hcadse.model import WORKLOADS, make_space
from hcadse.search import VAR_ORDER, structurally_valid

INF = float("inf")
TOL = 1e-12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2")
    ap.add_argument("--out", default="results/e17_generic_bb/dominates_partial.json")
    a = ap.parse_args()
    report = []
    for scale in a.scales.split(","):
        for wname, wl in WORKLOADS.items():
            space = make_space(scale)
            ours, generic = Bounder(space, wl), CachedPartialCostBounder(space, wl)
            checked = skipped = violations = 0
            worst = 0.0

            def rec(depth, partial):
                nonlocal checked, skipped, violations, worst
                if depth == len(VAR_ORDER):
                    return
                var = VAR_ORDER[depth]
                for val in space.domain(var):
                    q = dict(partial); q[var] = val
                    if not structurally_valid(q):
                        continue
                    pairs = ((ours.certify(q), generic.certify(q)),
                             (ours.fast_bounds(q), generic.fast_bounds(q)))
                    if any(x["L"] == INF or y["L"] == INF for x, y in pairs):
                        skipped += 1
                    else:
                        checked += 1
                        for x, y in pairs:
                            for k in "LECD":
                                excess = (y[k] - x[k]) / max(abs(x[k]), 1e-300)
                                worst = max(worst, excess)
                                violations += excess > TOL
                    rec(depth + 1, q)

            rec(0, {})
            report.append(dict(scale=scale, workload=wname, prefixes=checked,
                               unstable_skipped=skipped, violations=violations,
                               max_relative_excess=worst))
            print(json.dumps(report[-1]), flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=1) + "\n")
    assert all(r["violations"] == 0 for r in report), "partial cost exceeds the bound"


if __name__ == "__main__":
    main()
