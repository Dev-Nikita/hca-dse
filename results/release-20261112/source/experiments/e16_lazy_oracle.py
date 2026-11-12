"""Exact lazy-oracle SMT baseline without a precomputed objective table.

Z3 represents only the finite decision domains and structural constraints.  It
proposes one complete architecture at a time; the external Python evaluator
returns feasibility and objectives, after which a no-good clause blocks that
architecture.  Once the structural formula is UNSAT, every structurally valid
architecture has been evaluated and the retained archive is the exact oracle
Pareto front.

For a genuinely black-box oracle, blocking a larger unseen region would be
unsound without additional model-specific information.  This baseline thus
tests what lazy external-oracle SMT provides on its own, and separates solver
enumeration from the admissible partial-design bounds used by HCA-DSE.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import z3

from hcadse import feedback
from hcadse.evaluate import evaluate as analytic_evaluate
from hcadse.metrics import objset
from hcadse.model import VAR_ORDER, WORKLOADS, make_space
from hcadse.search import pareto_front, structurally_valid


def build_structural_solver(space):
    domains = {name: list(space.domain(name)) for name in VAR_ORDER}
    index = {name: z3.Int(name) for name in VAR_ORDER}
    solver = z3.Solver()
    for name, var in index.items():
        solver.add(var >= 0, var < len(domains[name]))

    # The three structural rules in hcadse.search.structurally_valid.
    ne, ng, rep, policy = (index[k] for k in ("n_e", "n_g", "rep", "policy"))
    ne_vals, ng_vals, rep_vals = (domains[k] for k in ("n_e", "n_g", "rep"))
    for i, a in enumerate(ng_vals):
        for j, b in enumerate(ne_vals):
            if a > b:
                solver.add(z3.Not(z3.And(ng == i, ne == j)))
    for i, a in enumerate(rep_vals):
        for j, b in enumerate(ne_vals):
            if a > b:
                solver.add(z3.Not(z3.And(rep == i, ne == j)))
    for i, a in enumerate(rep_vals):
        for j, p in enumerate(domains["policy"]):
            if p == "cloud-first" and a > 1:
                solver.add(z3.Not(z3.And(rep == i, policy == j)))
    return solver, index, domains


def solve(space, wl, evaluator, timeout_s):
    solver, variables, domains = build_structural_solver(space)
    solver.set(timeout=max(1, int(min(timeout_s, 10.0) * 1000)))
    points = []
    calls = checks = 0
    solver_seconds = evaluator_seconds = 0.0
    deadline = time.perf_counter() + timeout_s
    status_name = "exact"
    while True:
        if time.perf_counter() >= deadline:
            status_name = "timeout"
            break
        t0 = time.perf_counter()
        status = solver.check()
        solver_seconds += time.perf_counter() - t0
        checks += 1
        if status == z3.unsat:
            break
        if status != z3.sat:
            status_name = "timeout" if solver.reason_unknown() == "timeout" else "unknown"
            break
        model = solver.model()
        chosen = {name: model.eval(var).as_long() for name, var in variables.items()}
        design = {name: domains[name][chosen[name]] for name in VAR_ORDER}

        t0 = time.perf_counter()
        result = evaluator(design, wl)
        evaluator_seconds += time.perf_counter() - t0
        calls += 1
        if result.feasible:
            points.append((design, result.objectives))
        solver.add(z3.Or([var != chosen[name] for name, var in variables.items()]))
    return (pareto_front(points), calls, checks, solver_seconds, evaluator_seconds,
            status_name)


def exhaustive_oracle(space, wl, evaluator):
    points = []
    for design in space.enumerate():
        if not structurally_valid(design):
            continue
        result = evaluator(design, wl)
        if result.feasible:
            points.append((design, result.objectives))
    return pareto_front(points)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2,S3")
    ap.add_argument("--models", default="analytic,retry")
    ap.add_argument("--out", default="results/e16_lazy_oracle.csv")
    ap.add_argument("--timeout-s", type=float, default=60.0,
                    help="per scale/workload/model wall-time limit")
    a = ap.parse_args()
    evaluators = {"analytic": analytic_evaluate, "retry": feedback.evaluate}
    rows = []
    for model_name in a.models.split(","):
        evaluator = evaluators[model_name]
        for scale in a.scales.split(","):
            space = make_space(scale)
            for workload, wl in WORKLOADS.items():
                tracemalloc.start()
                t0 = time.perf_counter()
                front, calls, checks, solver_s, evaluator_s, status = solve(
                    space, wl, evaluator, a.timeout_s)
                total_s = time.perf_counter() - t0
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                exact = False
                if status == "exact":
                    reference = exhaustive_oracle(space, wl, evaluator)
                    exact = objset(front) == objset(reference)
                row = {"model": model_name, "scale": scale, "workload": workload,
                       "raw_space": space.size, "evaluator_calls": calls,
                       "solver_checks": checks, "pareto": len(objset(front)),
                       "solver_seconds": round(solver_s, 6),
                       "evaluator_seconds": round(evaluator_s, 6),
                       "total_seconds": round(total_s, 6),
                       "peak_traced_mib": round(peak / 2**20, 3),
                       "status": status, "exact": exact}
                rows.append(row)
                print(row, flush=True)
                assert status != "exact" or exact
                path = Path(a.out)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("w", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)


if __name__ == "__main__":
    main()
