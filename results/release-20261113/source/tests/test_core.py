"""Gate 2 + Gate 5 verification."""
import itertools, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS, VAR_ORDER
from hcadse.evaluate import evaluate
from hcadse.bounds import lower_bounds
from hcadse.search import exhaustive, hca_dse
from hcadse.metrics import objset

KEYS = ["L", "E", "C", "D"]


def test_bound_admissibility():
    """LB_i(partial) <= f_i(x) for every completion x, exhaustively on S1."""
    space = make_space("S1")
    worst = 0.0
    for wl in WORKLOADS.values():
        full = list(space.enumerate())
        for depth in range(0, len(VAR_ORDER)):
            seen = {}
            for x in full:
                key = tuple(x[v] for v in VAR_ORDER[:depth])
                seen.setdefault(key, []).append(x)
            for key, comps in seen.items():
                partial = dict(zip(VAR_ORDER[:depth], key))
                lb = lower_bounds(partial, space, wl)
                for x in comps:
                    f = evaluate(x, wl).objectives
                    for i, k in enumerate(KEYS):
                        assert lb[k] <= f[i] + 1e-9, (wl.name, depth, k, lb[k], f[i])
                        if f[i] > 0:
                            worst = max(worst, lb[k] / f[i]) if lb[k] <= f[i] else worst
    print("bound admissibility: OK")


def test_hca_equals_exhaustive():
    for scale in ("S1", "S2"):
        space = make_space(scale)
        for wl in WORKLOADS.values():
            ref = exhaustive(space, wl)
            got = hca_dse(space, wl)
            assert objset(got.front) == objset(ref.front), (scale, wl.name)
            print(f"{scale}/{wl.name}: |P|={len(objset(ref.front))} "
                  f"evals {got.n_evaluated}/{ref.n_evaluated} "
                  f"({100*(1-got.n_evaluated/max(ref.n_evaluated,1)):.1f}% saved)")


if __name__ == "__main__":
    test_bound_admissibility()
    test_hca_equals_exhaustive()
