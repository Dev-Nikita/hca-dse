"""Select representative architectures for the physical testbed (Gate 10).

Chosen so that the comparison is not flattered: Pareto-optimal designs, clearly
dominated designs, and designs near the deadline/utilisation boundary. Only
configurations that fit on one machine are kept (<= 4 edge + 2 gateway + 1 cloud
containers); this restriction is a stated limitation of the empirical study.
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS, POLICIES, WAN_B, WAN_PROP
from hcadse.evaluate import evaluate
from hcadse.search import hca_dse, structurally_valid

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--max-edge", type=int, default=4)
_ap.add_argument("--max-gw", type=int, default=2)
_ap.add_argument("--out", default="testbed/specs/designs.json")
_A = _ap.parse_args()
MAX_E, MAX_G = _A.max_edge, _A.max_gw
N_PARETO, N_OTHER, N_BOUNDARY = 6, 4, 2


def fits(x):
    return x["n_e"] <= MAX_E and x["n_g"] <= MAX_G


def spec_for(x, wl, n_req, warmup):
    """Container topology + request plan implied by design x."""
    t1, t3 = POLICIES[x["policy"]]
    edges = [f"edge{i+1}:8080" for i in range(x["n_e"])]
    gws = [f"gw{i+1}:8080" for i in range(x["n_g"])]
    cloud = "cloud1:8080"
    host = {"edge": edges, "gw": gws, "cloud": [cloud]}
    entry = host[t1]
    steps = [dict(hosts=entry, work_mi=wl.stages[0].w, pay_mb=wl.stages[0].s_in),
             dict(hosts=gws, work_mi=wl.stages[1].w, pay_mb=wl.stages[1].s_in),
             dict(hosts=host[t3], work_mi=wl.stages[2].w, pay_mb=wl.stages[2].s_in)]
    return dict(tiers=[t1, "gw", t3],
                stages=[dict(w=st.w, pay=st.s_in) for st in wl.stages],
                design=dict(x, edge_cls=x["edge_cls"].name, gw_cls=x["gw_cls"].name,
                            cloud_cls=x["cloud_cls"].name, link_cls=x["link_cls"].name),
                entry=entry, rep=x["rep"], steps=steps, lambda_=wl.Lambda,
                n_req=n_req, warmup=warmup, first_pay_mb=wl.stages[0].s_in,
                sync_mb=wl.s_sync)


def main():
    sp = make_space("S2")
    out = []
    for name, wl in WORKLOADS.items():
        rng = random.Random(11)
        front = [x for x, _ in hca_dse(sp, wl).front if fits(x)]
        allx = [x for x in sp.enumerate() if structurally_valid(x) and fits(x)]
        feas = [(x, evaluate(x, wl)) for x in allx]
        ok = [(x, r) for x, r in feas if r.feasible]
        dominated = [x for x, r in ok if x not in front]
        boundary = sorted([(x, r) for x, r in ok],
                          key=lambda z: -max(z[1].rho.values()))[:20]
        rng.shuffle(dominated); rng.shuffle(boundary)
        sel = ([(x, "pareto") for x in front[:N_PARETO]] +
               [(x, "dominated") for x in dominated[:N_OTHER]] +
               [(x, "boundary") for x, _ in boundary[:N_BOUNDARY]])
        for x, kind in sel:
            r = evaluate(x, wl)
            d = spec_for(x, wl, n_req=900, warmup=150)
            d.update(workload=name, kind=kind,
                     L_analytical=r.objectives[0], rho=r.rho,
                     mips=dict(edge=x["edge_cls"].C, gw=x["gw_cls"].C,
                               cloud=x["cloud_cls"].C),
                     link=dict(delay_ms=x["link_cls"].prop * 1000, rate_mbit=x["link_cls"].B),
                     wan=dict(delay_ms=WAN_PROP * 1000, rate_mbit=WAN_B),
                     n_e=x["n_e"], n_g=x["n_g"])
            out.append(d)
    os.makedirs("testbed/specs", exist_ok=True)
    with open(_A.out, "w") as f:
        json.dump(out, f, indent=1)
    print(f"selected {len(out)} designs -> {_A.out}")
    for w in WORKLOADS:
        k = [d["kind"] for d in out if d["workload"] == w]
        print(f"  {w}: {len(k)} ({k.count('pareto')} pareto, {k.count('dominated')} dominated, "
              f"{k.count('boundary')} boundary)")


if __name__ == "__main__":
    main()
