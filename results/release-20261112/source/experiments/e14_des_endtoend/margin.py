"""Prospective screening decisions, scored post hoc against exhaustive DES.

The dump must contain every structurally valid design, including infeasible
ones.  Selection uses only analytical feasibility and analytical objectives:
the analytical Pareto front is fixed first, then the epsilon rule selects
candidates without consulting DES values.  DES feasibility/objectives are read
only after selection to score recall against independent exhaustive-DES ground
truth.  The exhaustive dump is therefore an evaluation oracle for the
experiment, not an input to the screening policy.
"""
import argparse, json, sys
import numpy as np


def nondominated_mask(F):
    """Boolean mask of the non-dominated rows of F (minimisation)."""
    n = len(F)
    keep = np.ones(n, bool)
    order = np.argsort(F[:, 0], kind="stable")
    for i in order:
        if not keep[i]:
            continue
        le = np.all(F <= F[i], axis=1)
        lt = np.any(F < F[i], axis=1)
        dom = le & lt
        if dom.any():
            keep[i] = False
    return keep


def dominated_by_front(F, front_F, eps):
    """Rows of F that some inflated front point dominates."""
    out = np.zeros(len(F), bool)
    for b in front_F * (1.0 + eps):
        out |= np.all(b <= F, axis=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dumps", nargs="+")
    ap.add_argument("--out", default="out/margin.json")
    a = ap.parse_args()
    rows = []
    for path in a.dumps:
        d = json.load(open(path))
        dump = d.get("_dump")
        if not dump:
            print("no dump in " + path, file=sys.stderr)
            continue
        required = {"analytic_feasible", "des_feasible"}
        if any(not required.issubset(r) for r in dump):
            raise ValueError(path + " is a legacy feasibility-filtered dump; rerun des_driver.py")
        an = np.array([r["analytic"] for r in dump], float)
        de = np.array([r["des"] for r in dump], float)
        an_ok = np.array([r["analytic_feasible"] for r in dump], bool) & np.all(np.isfinite(an), axis=1)
        de_ok = np.array([r["des_feasible"] for r in dump], bool) & np.all(np.isfinite(de), axis=1)

        # Ground truth uses DES only and includes designs the analytical
        # feasibility test rejects.  Those become genuine screening misses.
        des_front = np.zeros(len(dump), bool)
        des_idx = np.where(de_ok)[0]
        des_front[des_idx] = nondominated_mask(de[des_idx])

        base = np.zeros(len(dump), bool)
        an_idx = np.where(an_ok)[0]
        base[an_idx] = nondominated_mask(an[an_idx])
        base_F = an[base]
        for eps in (0.0, 0.01, 0.05, 0.10, 0.20, 0.30):
            sel = np.zeros(len(dump), bool)
            if eps == 0:
                sel = base.copy()
            else:
                sel[an_idx] = ~dominated_by_front(an[an_idx], base_F, eps)
            picked = np.zeros(len(dump), bool)
            idx = np.where(sel & de_ok)[0]
            if len(idx):
                picked[idx] = nondominated_mask(de[idx])
            hit = int((picked & des_front).sum())
            rows.append(dict(scale=d["scale"], workload=d["workload"], eps=eps,
                             sims=int(sel.sum()), recall=hit / max(int(des_front.sum()), 1),
                             des_front=int(des_front.sum()),
                             analytic_feasible=int(an_ok.sum()),
                             des_feasible=int(de_ok.sum()),
                             selected_des_feasible=int((sel & de_ok).sum()),
                             analytic_feasibility_misses=int((~an_ok & des_front).sum()),
                             exhaustive_sims=int(d["exh_sim_runs"])))
    print("%-4s %-10s %6s %7s %8s %10s %10s" %
          ("sc", "workload", "eps", "sims", "recall", "DES front", "exh sims"))
    for r in rows:
        print("%-4s %-10s %6.2f %7d %8.3f %10d %10d" %
              (r["scale"], r["workload"], r["eps"], r["sims"], r["recall"],
               r["des_front"], r["exhaustive_sims"]))
    json.dump(rows, open(a.out, "w"), indent=2)


if __name__ == "__main__":
    main()
