"""E15: exploration under a load term that no compact solver encoding represents.

Three methods on the retry model of hcadse/feedback.py:

  EXH       exhaustive enumeration with the retry evaluator.  Ground truth.
  HCA-DSE   the same search as Section 4, with the retry bounds of Proposition 4.
  TABLE     the finite-table Z3 baseline of experiments/e11_solver.py: evaluate
            every structurally valid design, then solve exactly over the table.

The factorised encoding of experiments/e12_symbolic.py is not among them, and
this script reports why in numbers: the retry term is a single term whose
support is the whole decision vector, so its table has one entry per design of
the space and each entry is one evaluator call.  The compact encoding therefore
degenerates into TABLE.
"""
import argparse, csv, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hcadse import feedback
from hcadse import search as search_mod
from hcadse.metrics import objset
from hcadse.model import VAR_ORDER, WORKLOADS, make_space
from hcadse.search import exhaustive, hca_dse, structurally_valid


class FbBounder:
    """Bounder interface over hcadse.feedback.lower_bounds."""

    def __init__(self, space, wl, use_queue_bound=True):
        self.space, self.wl, self.calls = space, wl, 0
        self.use_queue_bound = use_queue_bound

    def bounds(self, partial):
        self.calls += 1
        return feedback.lower_bounds(partial, self.space, self.wl)

    def fast_bounds(self, partial):
        self.calls += 1
        return feedback.legacy_lower_bounds(partial, self.space, self.wl)

    def certify(self, partial):
        self.calls += 1
        return feedback.lower_bounds(partial, self.space, self.wl)

    @staticmethod
    def certified_objectives(design, workload):
        return feedback.certified_objectives(design, workload)


def table_baseline(space, wl, timeout_ms=120000):
    """e11_solver on the retry model: the cost of the table is the method's cost."""
    import z3
    t0 = time.perf_counter()
    points, ne = [], 0
    for x in space.enumerate():
        if not structurally_valid(x):
            continue
        r = feedback.evaluate(x, wl)
        ne += 1
        if r.feasible:
            points.append((x, r.objectives))
    table_time = time.perf_counter() - t0
    unique = sorted({f for _, f in points})
    values = [sorted({f[i] for f in unique}) for i in range(4)]
    ranks = [{v: j for j, v in enumerate(vs)} for vs in values]
    rankvec = [tuple(ranks[i][f[i]] for i in range(4)) for f in unique]
    obj = z3.Ints("L E C D")
    solver = z3.Solver()
    solver.set(timeout=timeout_ms, random_seed=0)
    solver.add(z3.Or([z3.And([obj[i] == f[i] for i in range(4)]) for f in rankvec]))
    front, checks = [], 0

    def check():
        nonlocal checks
        checks += 1
        r = solver.check()
        if r == z3.unknown:
            raise RuntimeError(solver.reason_unknown())
        return r

    while check() == z3.sat:
        p = tuple(solver.model()[v].as_long() for v in obj)
        solver.push()
        while True:
            solver.add(z3.And([obj[i] <= p[i] for i in range(4)]),
                       z3.Or([obj[i] < p[i] for i in range(4)]))
            if check() == z3.unsat:
                break
            p = tuple(solver.model()[v].as_long() for v in obj)
        solver.pop()
        front.append(tuple(values[i][p[i]] for i in range(4)))
        solver.add(z3.Or([obj[i] < p[i] for i in range(4)]))
    total = time.perf_counter() - t0
    return dict(evaluator_calls=ne, table_seconds=table_time, total_seconds=total,
                solver_seconds=total - table_time, solver_checks=checks,
                front=set(front))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2,S3")
    ap.add_argument("--table-scales", default="S1,S2")
    ap.add_argument("--out", default="results/e15_feedback")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    original_eval, original_bounder = search_mod.evaluate, search_mod.Bounder
    rows = []
    try:
        search_mod.evaluate = feedback.evaluate
        search_mod.Bounder = FbBounder
        for scale in a.scales.split(","):
            for wname, wl in WORKLOADS.items():
                space = make_space(scale)
                iters = []
                base_fp = feedback.fixed_point

                def counted(L_of_lam, lam0, tau, _fp=base_fp, _it=iters):
                    r = _fp(L_of_lam, lam0, tau)
                    _it.append(r[2])
                    return r

                feedback.fixed_point = counted
                try:
                    e = exhaustive(space, wl)
                finally:
                    feedback.fixed_point = base_fp
                h = hca_dse(space, wl)
                same = objset(h.front) == objset(e.front)
                row = dict(scale=scale, workload=wname, space=space.size,
                           exh_evals=e.n_evaluated, exh_seconds=round(e.runtime, 3),
                           hca_evals=h.n_evaluated, hca_seconds=round(h.runtime, 3),
                           hca_bound_calls=h.n_bound_calls, hca_nodes=h.n_nodes,
                           front=len(objset(e.front)), exact=bool(same),
                           eval_reduction=round(e.n_evaluated / max(h.n_evaluated, 1), 1),
                           speedup=round(e.runtime / max(h.runtime, 1e-9), 2),
                           fp_iters_max=max(iters), fp_iters_mean=round(
                               sum(iters) / max(len(iters), 1), 1))
                assert same, ("the retry front is not reproduced", scale, wname)
                # screening with the retry term ignored: the front of the
                # closed-form model, re-evaluated under retries
                from hcadse.evaluate import evaluate as analytic_evaluate
                ignored = search_mod.evaluate
                try:
                    search_mod.evaluate = analytic_evaluate
                    search_mod.Bounder = original_bounder
                    plain = hca_dse(space, wl)
                finally:
                    search_mod.evaluate = ignored
                    search_mod.Bounder = FbBounder
                resc = [(x, feedback.evaluate(x, wl)) for x, _ in plain.front]
                resc = search_mod.pareto_front([(x, r.objectives) for x, r in resc
                                                if r.feasible])
                ref = {f for _, f in e.front}
                hit = len({f for _, f in resc} & ref)
                row.update(ignore_screen_designs=len(plain.front),
                           ignore_screen_recall=round(hit / max(len(ref), 1), 3))
                if scale in a.table_scales.split(","):
                    t = table_baseline(space, wl)
                    assert t["front"] == {f for _, f in e.front}, "table front differs"
                    row.update(table_evaluator_calls=t["evaluator_calls"],
                               table_seconds=round(t["total_seconds"], 3),
                               table_build_seconds=round(t["table_seconds"], 3),
                               table_solver_seconds=round(t["solver_seconds"], 3),
                               table_solver_checks=t["solver_checks"])
                # the factorised encoding's table for the retry term
                row.update(factorised_support=len(VAR_ORDER),
                           factorised_entries=space.size)
                rows.append(row)
                print(json.dumps(row), flush=True)
    finally:
        search_mod.evaluate, search_mod.Bounder = original_eval, original_bounder

    keys = sorted({k for r in rows for k in r})
    with (out / "feedback.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out / "feedback.csv")


if __name__ == "__main__":
    main()
