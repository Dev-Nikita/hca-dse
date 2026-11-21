"""E20: the bound against the generic partial cost under tighter and looser
constraints (protocol: PROTOCOL.md, fixed before the runs).

The deadline, cost budget and energy budget of every workload are scaled jointly
by m in {0.8, 1.0, 1.25}.  G0 exhaustive, G1c generic partial cost, G2 the bound
of Section 4, all with the same order, pruning rules and certified archive.
"""
from __future__ import annotations

import argparse, csv, dataclasses, json, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "e17_generic_bb"))

from bounders import CachedPartialCostBounder  # noqa: E402
from hcadse import search as search_mod  # noqa: E402
from hcadse.bounder import Bounder  # noqa: E402
from hcadse.metrics import objset  # noqa: E402
from hcadse.model import WORKLOADS, make_space  # noqa: E402
from hcadse.search import exhaustive, hca_dse  # noqa: E402

REGIMES = (("tight", 0.8), ("baseline", 1.0), ("loose", 1.25))
CONFIGS = (("G1c", CachedPartialCostBounder), ("G2", Bounder))


def regime(wl, m):
    return dataclasses.replace(wl, deadline=wl.deadline * m, C_max=wl.C_max * m,
                               E_max=wl.E_max * m)


def timed(fn, repeats):
    walls, evals = [], []
    out = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        walls.append(time.perf_counter() - t0)
        evals.append(out.t_eval)
    return out, statistics.median(walls), statistics.median(evals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="S1,S2,S3")
    ap.add_argument("--workloads", default=",".join(WORKLOADS))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--part", default=None)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--out", default="results/e20_regimes")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.merge:
        rs = {s: i for i, s in enumerate(("S1", "S2", "S3"))}
        ws = {w: i for i, w in enumerate(WORKLOADS)}
        gs = {g: i for i, (g, _) in enumerate(REGIMES)}
        cs = {"G0": 0, "G1c": 1, "G2": 2}
        rows = [r for f in sorted(out.glob("regimes_*.csv")) for r in csv.DictReader(f.open())]
        rows.sort(key=lambda r: (rs[r["scale"]], ws[r["workload"]], gs[r["regime"]], cs[r["config"]]))
        with (out / "regimes.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("merged", len(rows), "rows")
        return
    rows = []
    for scale in a.scales.split(","):
        space = make_space(scale)
        for wname in a.workloads.split(","):
            for gname, m in REGIMES:
                wl = regime(WORKLOADS[wname], m)
                ex, wall, et = timed(lambda: exhaustive(space, wl), a.repeats)
                ref = objset(ex.front)
                base = dict(scale=scale, workload=wname, regime=gname, m=m)
                rows.append(dict(base, config="G0", evals=ex.n_evaluated, nodes=ex.n_evaluated,
                                 bound_calls=0, seconds=round(wall, 4),
                                 overhead_seconds=round(wall - et, 4), front=len(ref),
                                 feasible=ex.n_feasible, exact=True))
                print(json.dumps(rows[-1]), flush=True)
                for cname, bounder in CONFIGS:
                    original = search_mod.Bounder
                    search_mod.Bounder = bounder
                    try:
                        st, wall, et = timed(lambda: hca_dse(space, wl), a.repeats)
                    finally:
                        search_mod.Bounder = original
                    same = objset(st.front) == ref
                    rows.append(dict(base, config=cname, evals=st.n_evaluated, nodes=st.n_nodes,
                                     bound_calls=st.n_bound_calls, seconds=round(wall, 4),
                                     overhead_seconds=round(wall - et, 4),
                                     front=len(objset(st.front)), feasible=st.n_feasible,
                                     exact=bool(same)))
                    print(json.dumps(rows[-1]), flush=True)
                    assert same, ("front differs", scale, wname, gname, cname)
    name = "regimes.csv" if a.part is None else "regimes_%s.csv" % a.part
    with (out / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", out / name)


if __name__ == "__main__":
    main()
