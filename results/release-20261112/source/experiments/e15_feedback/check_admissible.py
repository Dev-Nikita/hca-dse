"""Exhaustive machine check of Proposition 4 on S1 (and a prefix sample on S2).

For every prefix of the decision order and every completion of that prefix, the
term-wise bound of hcadse.feedback.lower_bounds must not exceed the objective
vector the retry evaluator returns for the completion.  Infeasible completions
are included: a bound must underestimate every completion, feasible or not,
because pruning happens before feasibility is known.
"""
import argparse, itertools, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hcadse import feedback
from hcadse.model import VAR_ORDER, WORKLOADS, make_space
from hcadse.search import structurally_valid

INF = float("inf")
KEYS = ("L", "E", "C", "D")
IDX = {"L": 0, "E": 1, "C": 2, "D": 3}


def completions(space, partial, rest):
    doms = [space.domain(v) for v in rest]
    for combo in itertools.product(*doms):
        x = dict(partial)
        x.update(dict(zip(rest, combo)))
        yield x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="S1")
    ap.add_argument("--depth-max", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    rows = []
    for wname, wl in WORKLOADS.items():
        space = make_space(a.scale)
        t0 = time.perf_counter()
        prefixes = checks = 0
        worst = {k: INF for k in KEYS}      # smallest slack f_i - LB_i
        for depth in range(0, min(a.depth_max, len(VAR_ORDER)) + 1):
            head, rest = VAR_ORDER[:depth], list(VAR_ORDER[depth:])
            for combo in itertools.product(*[space.domain(v) for v in head]):
                partial = dict(zip(head, combo))
                if not structurally_valid(partial):
                    continue
                prefixes += 1
                lb = feedback.lower_bounds(partial, space, wl)
                if not (lb["L"] < INF):
                    # an infeasible bound prunes the whole subtree: every
                    # completion must indeed be infeasible
                    for x in completions(space, partial, rest):
                        if not structurally_valid(x):
                            continue
                        checks += 1
                        r = feedback.evaluate(x, wl)
                        assert not r.feasible, ("inf bound over a feasible completion",
                                                wname, partial, x)
                    continue
                for x in completions(space, partial, rest):
                    if not structurally_valid(x):
                        continue
                    checks += 1
                    f = feedback.evaluate(x, wl).objectives
                    for k in KEYS:
                        v = f[IDX[k]]
                        if v == INF:
                            continue
                        slack = v - lb[k]
                        assert slack >= -1e-9, ("bound violated", k, wname, partial, x,
                                                lb[k], v)
                        worst[k] = min(worst[k], slack)
        row = dict(scale=a.scale, workload=wname, prefixes=prefixes, checks=checks,
                   seconds=round(time.perf_counter() - t0, 2),
                   min_slack={k: (None if worst[k] == INF else worst[k]) for k in KEYS})
        rows.append(row)
        print(json.dumps(row), flush=True)
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=2)
    print("Proposition 4 holds on every prefix/completion pair checked.")


if __name__ == "__main__":
    main()
