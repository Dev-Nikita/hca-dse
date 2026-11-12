"""Exhaustive check that the positive waiting bound never exceeds a completion.

For every prefix of the decision order and every completion of that prefix, the
bound of hcadse.partialqueue plus the published bound must stay at or below the
objective vector the evaluator returns.  Infeasible completions are included,
because pruning happens before feasibility is known.
"""
import argparse, itertools, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bounders import PositiveQueueBounder

from hcadse.evaluate import evaluate
from hcadse.model import VAR_ORDER, WORKLOADS, make_space
from hcadse.search import structurally_valid

INF = float("inf")
KEYS = {"L": 0, "E": 1, "C": 2, "D": 3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="S1")
    ap.add_argument("--depth-max", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    for wname, wl in WORKLOADS.items():
        space = make_space(a.scale)
        bounder = PositiveQueueBounder(space, wl)
        prefixes = checks = 0
        worst = {k: INF for k in KEYS}
        for depth in range(0, min(a.depth_max, len(VAR_ORDER)) + 1):
            head, rest = VAR_ORDER[:depth], list(VAR_ORDER[depth:])
            for combo in itertools.product(*[space.domain(v) for v in head]):
                partial = dict(zip(head, combo))
                if not structurally_valid(partial):
                    continue
                prefixes += 1
                lb = bounder.bounds(partial)
                completions = itertools.product(*[space.domain(v) for v in rest])
                for tail in completions:
                    x = dict(partial)
                    x.update(dict(zip(rest, tail)))
                    if not structurally_valid(x):
                        continue
                    checks += 1
                    f = evaluate(x, wl).objectives
                    for k, i in KEYS.items():
                        if f[i] == INF or lb[k] == INF:
                            continue
                        slack = f[i] - lb[k]
                        assert slack >= -1e-9, ("bound violated", k, wname, partial, x,
                                                lb[k], f[i])
                        worst[k] = min(worst[k], slack)
        row = dict(scale=a.scale, workload=wname, prefixes=prefixes, checks=checks,
                   min_slack={k: (None if worst[k] == INF else worst[k]) for k in KEYS})
        rows.append(row)
        print(json.dumps(row), flush=True)
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=2)
    print("the positive waiting bound is admissible on every pair checked.")


if __name__ == "__main__":
    main()
