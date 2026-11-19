"""Direct empirical verification of Propositions 1-3 on the implementation.

For every prefix the algorithm prunes, enumerate ALL of its completions and check
that the reason claimed by the proposition actually holds:
  structural   -> no completion is well-formed                    (Prop. 3)
  feasibility  -> no completion is feasible                       (Prop. 1)
  dominance    -> no completion lies on the true Pareto front     (Prop. 2)
                  of the exhaustive run over the well-formed space
"""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS, VAR_ORDER
from hcadse.evaluate import evaluate
from hcadse.search import exhaustive, hca_dse, structurally_valid
from hcadse.metrics import objset


def completions(space, partial):
    free = [v for v in VAR_ORDER if v not in partial]
    for combo in itertools.product(*[space.domain(v) for v in free]):
        x = dict(partial); x.update(dict(zip(free, combo)))
        yield x


def test_pruning_safety(scale="S1"):
    space = make_space(scale)
    for name, wl in WORKLOADS.items():
        ref_front = objset(exhaustive(space, wl).front)
        pruned = []
        hca_dse(space, wl, record_pruned=pruned)
        checked = {"structural": 0, "feasibility": 0, "dominance": 0}
        for reason, p in pruned:
            for x in completions(space, p):
                r = evaluate(x, wl)
                if reason == "structural":
                    assert not structurally_valid(x), (
                        f"structural pruning removed a WELL-FORMED design: {p} -> {x}")
                elif reason == "feasibility":
                    assert not (structurally_valid(x) and r.feasible), (
                        f"feasibility pruning removed a FEASIBLE design: {p} -> {x}")
                else:
                    key = tuple(round(v, 9) for v in r.objectives)
                    assert not (structurally_valid(x) and r.feasible and key in ref_front), (
                        f"dominance pruning removed a PARETO-OPTIMAL design: {p} -> {x}")
                checked[reason] += 1
        print(f"{scale}/{name}: pruned prefixes={len(pruned)}, completions verified="
              f"{sum(checked.values())} "
              f"(structural {checked['structural']}, feasibility {checked['feasibility']}, "
              f"dominance {checked['dominance']}) — all safe")


if __name__ == "__main__":
    test_pruning_safety("S1")
    test_pruning_safety("S2")
