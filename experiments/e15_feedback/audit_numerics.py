"""Independent numerical-sensitivity audit for the E15 retry fixed point.

Recompute every structurally valid design with tighter and looser stopping
tolerances, then compare feasibility, Pareto membership and objective values.
This is an empirical floating-point sensitivity check, not a formal roundoff
proof.  It deliberately bypasses HCA-DSE so pruning cannot hide a difference.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hcadse import feedback
from hcadse.model import WORKLOADS, make_space
from hcadse.search import pareto_front, structurally_valid


def design_key(x):
    return tuple((k, getattr(v, "name", v)) for k, v in sorted(x.items()))


def sweep(scale, wl, tol):
    original = feedback.fixed_point

    def fixed(L_of_lam, lam0, tau):
        return original(L_of_lam, lam0, tau, rtol=tol, atol=tol)

    feedback.fixed_point = fixed
    try:
        rows = []
        for x in make_space(scale).enumerate():
            if structurally_valid(x):
                r = feedback.evaluate(x, wl)
                rows.append((design_key(x), r))
    finally:
        feedback.fixed_point = original
    front = pareto_front([(k, r.objectives) for k, r in rows if r.feasible])
    return {k: r for k, r in rows}, {k for k, _ in front}, {k: f for k, f in front}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2,S3")
    ap.add_argument("--tolerances", default="1e-10,1e-12,1e-14")
    ap.add_argument("--out", default="results/e15_feedback/numerical_audit.json")
    a = ap.parse_args()
    tolerances = [float(v) for v in a.tolerances.split(",")]
    reference_tol = min(tolerances)
    report = []
    for scale in a.scales.split(","):
        for name, wl in WORKLOADS.items():
            runs = {tol: sweep(scale, wl, tol) for tol in tolerances}
            ref_rows, ref_front, ref_obj = runs[reference_tol]
            for tol in tolerances:
                rows, front, obj = runs[tol]
                max_rel = 0.0
                for key in ref_rows:
                    left, right = rows[key], ref_rows[key]
                    if left.feasible != right.feasible:
                        continue
                    for u, v in zip(left.objectives, right.objectives):
                        if math.isfinite(u) and math.isfinite(v):
                            max_rel = max(max_rel, abs(u - v) / max(abs(v), 1.0))
                item = {"scale": scale, "workload": name, "tolerance": tol,
                        "reference_tolerance": reference_tol,
                        "feasibility_changes": sum(rows[k].feasible != ref_rows[k].feasible
                                                   for k in ref_rows),
                        "front_membership_changes": len(front ^ ref_front),
                        "front_size": len(front), "max_relative_objective_change": max_rel}
                report.append(item)
                print(json.dumps(item, sort_keys=True), flush=True)
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    assert all(r["feasibility_changes"] == 0 and r["front_membership_changes"] == 0
               for r in report), "Pareto or feasibility result changed with tolerance"


if __name__ == "__main__":
    main()
