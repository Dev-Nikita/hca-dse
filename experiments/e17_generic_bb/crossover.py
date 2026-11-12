"""Where the generic bound overtakes ours as the evaluator gets expensive.

The controlled comparison leaves the published bound with less search overhead
and, on six of the nine combinations, one to five more full evaluations than the
generic bound.  Which of the two is cheaper therefore depends on what one full
evaluation costs.  With the linear cost model of Section 4.7,

    T(C_E) = overhead + N C_E,

where `overhead` is the measured wall-clock minus the measured time inside the
evaluator and N is the number of full evaluations, the two cross at

    C_E* = (overhead_ours - overhead_generic) / (N_generic - N_ours).

Below C_E* the published bound is cheaper, above it the generic bound is. When
the two spend the same number of evaluations there is no crossover: the lower
overhead wins at every evaluator cost. The same computation against exhaustive
enumeration is reported for reference.
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

INF = float("inf")


def crossover(a, b):
    """Cost at which configuration b overtakes a (a has lower overhead)."""
    dn = int(b["evals"]) - int(a["evals"])
    do = float(a["overhead_seconds"]) - float(b["overhead_seconds"])
    if dn == 0:
        return None          # no crossover; the lower overhead always wins
    return do / -dn if dn < 0 else None if do <= 0 else do / dn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="results/e17_generic_bb/bb_matrix.csv")
    ap.add_argument("--out", default="results/e17_generic_bb/crossover.csv")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.matrix)))
    by = {}
    for r in rows:
        by.setdefault((r["scale"], r["workload"]), {})[r["config"]] = r

    out = []
    for (scale, workload), cell in sorted(by.items()):
        ours, generic, oracle = cell["G2"], cell["G1c"], cell["G0"]
        # ours vs the generic bound
        extra = int(ours["evals"]) - int(generic["evals"])
        margin = float(generic["overhead_seconds"]) - float(ours["overhead_seconds"])
        # ours is cheaper while margin > extra * C_E
        c_generic = (margin / extra) if extra > 0 and margin > 0 else None
        # ours vs exhaustive enumeration
        dn_x = int(oracle["evals"]) - int(ours["evals"])
        do_x = float(ours["overhead_seconds"]) - float(oracle["overhead_seconds"])
        c_exh = (do_x / dn_x) if dn_x > 0 and do_x > 0 else None
        out.append(dict(
            scale=scale, workload=workload,
            ours_evals=ours["evals"], generic_evals=generic["evals"],
            ours_overhead=ours["overhead_seconds"],
            generic_overhead=generic["overhead_seconds"],
            exhaustive_overhead=oracle["overhead_seconds"],
            extra_evals=extra,
            crossover_vs_generic_s=("" if c_generic is None else round(c_generic, 4)),
            crossover_vs_exhaustive_us=("" if c_exh is None else round(c_exh * 1e6, 2)),
        ))
        print(json.dumps(out[-1]), flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
