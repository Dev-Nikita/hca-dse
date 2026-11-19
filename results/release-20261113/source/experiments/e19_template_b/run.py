"""E19: the bound construction on a second, structurally different template.

For each scale and workload of template B: exhaustive enumeration (the oracle),
the generic partial-cost branch-and-bound (G1), the bound of Section 4 with the
waiting term relaxed to zero (G2m) and the bound of Section 4 (G2), all with the
same traversal order, the same pruning rules and the same archive.  Wall-clock
is the median of three runs; the overhead is wall-clock minus the time spent in
the evaluator.  Every configuration must return the exhaustive front.
"""
from __future__ import annotations

import argparse, csv, json, statistics, sys, time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hcadse import template_b as tb

CONFIGS = (("G1", dict(relax=False)), ("G2m", dict(queue=False)), ("G2", dict()))


def timed(fn, repeats):
    walls, evals_t, out = [], [], None
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        walls.append(time.perf_counter() - t0)
        evals_t.append(out.t_eval)
    return out, statistics.median(walls), statistics.median(evals_t)


def reference(out, scale, wname):
    """The exact exhaustive front, stored as numerator/denominator strings so that
    it is computed once and can be checked independently."""
    f = out / "reference" / ("%s_%s.json" % (scale, wname))
    if f.exists():
        return tuple(tuple(Fraction(v) for v in row) for row in json.loads(f.read_text()))
    front = tb.exhaustive(scale, tb.WORKLOADS[wname], exact=True).front
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps([[str(v) for v in row] for row in front]) + "\n")
    return front


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="B1,B2,B3")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workloads", default=",".join(tb.WORKLOADS))
    ap.add_argument("--part", default=None,
                    help="write matrix_<part>.csv; `--merge` joins the parts")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--reference-only", action="store_true",
                    help="only compute and store the exact exhaustive fronts")
    ap.add_argument("--out", default="results/e19_template_b")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.merge:
        rank = {s: i for i, s in enumerate(tb.SCALES)}
        wrank = {w: i for i, w in enumerate(tb.WORKLOADS)}
        crank = {"G0": 0, "G1": 1, "G2m": 2, "G2": 3}
        rows = [r for f in sorted(out.glob("matrix_*.csv")) for r in csv.DictReader(f.open())]
        rows.sort(key=lambda r: (rank[r["scale"]], wrank[r["workload"]], crank[r["config"]]))
        with (out / "matrix.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("merged", len(rows), "rows into", out / "matrix.csv")
        return
    if a.reference_only:
        for scale in a.scales.split(","):
            for wname in a.workloads.split(","):
                t0 = time.perf_counter()
                reference(out, scale, wname)
                print(scale, wname, "exact front in %.1f s" % (time.perf_counter() - t0), flush=True)
        return
    rows = []
    for scale in a.scales.split(","):
        for wname in a.workloads.split(","):
            wl = tb.WORKLOADS[wname]
            oracle, wall, et = timed(lambda: tb.exhaustive(scale, wl), a.repeats)
            reference_front = reference(out, scale, wname)
            rows.append(dict(scale=scale, workload=wname, config="G0", raw=tb.raw_size(scale),
                             evals=oracle.evals, nodes=oracle.nodes, bound_calls=0,
                             certifications=0,
                             seconds=round(wall, 4), eval_seconds=round(et, 4),
                             overhead_seconds=round(wall - et, 4),
                             front=len(reference_front), exact=True,
                             float_front_equal=(len(oracle.front) == len(reference_front)
                                                and all(abs(float(a_[i]) - b_[i]) <= 1e-9 * max(1.0, abs(b_[i]))
                                                        for a_, b_ in zip(reference_front, oracle.front)
                                                        for i in range(4)))))
            print(json.dumps(rows[-1]), flush=True)
            for name, kw in CONFIGS:
                s, wall, et = timed(lambda: tb.search(scale, wl, **kw), a.repeats)
                same = s.front == reference_front
                rows.append(dict(scale=scale, workload=wname, config=name,
                                 raw=tb.raw_size(scale), evals=s.evals, nodes=s.nodes,
                                 bound_calls=s.bound_calls,
                                 certifications=s.certifications, seconds=round(wall, 4),
                                 eval_seconds=round(et, 4),
                                 overhead_seconds=round(wall - et, 4),
                                 front=len(s.front), exact=same))
                print(json.dumps(rows[-1]), flush=True)
                assert same, ("front differs from the oracle", scale, wname, name)
    name = "matrix.csv" if a.part is None else "matrix_%s.csv" % a.part
    with (out / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", out / name)


if __name__ == "__main__":
    main()
