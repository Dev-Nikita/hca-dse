"""Independent reference implementation of template B.

Written from the specification in the supplementary material, not from
hcadse.template_b: only the parameter tables (node and link classes, workloads,
scale domains) are taken from that module, and every computation --- enumeration,
well-formedness, utilisation, stage time, transfer, fork-join latency, energy,
cost, volume, feasibility and the Pareto filter --- is reimplemented here in
rational arithmetic.  The production code is then compared against it.
"""
from __future__ import annotations

import argparse, itertools, json, random, sys
from fractions import Fraction as Q
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hcadse import template_b as tb  # parameters and the code under test only

STAGE_NAMES = ["I", "F", "A", "N", "R"]
ALLOWED = {"I": ("edge", "fog"), "F": ("edge", "fog"), "A": ("fog", "cloud"),
           "N": ("fog", "cloud"), "R": ("fog", "cloud")}
LEVEL = {"edge": 0, "fog": 1, "cloud": 2}
# graph edges with payload index: src->I, I->F, F->A, A->N, F->R
GRAPH = [("src", "I", 0), ("I", "F", 1), ("F", "A", 2), ("A", "N", 3), ("F", "R", 4)]


def designs(scale):
    d = tb.SCALES[scale]
    for n_e, k_e, n_f, k_f, link, k_c in itertools.product(
            d["n_e"], d["k_e"], d["n_f"], d["k_f"], d["link"], d["k_c"]):
        for tiers in itertools.product(*[ALLOWED[s] for s in STAGE_NAMES]):
            place = dict(zip(STAGE_NAMES, tiers))
            yield dict(n_e=n_e, k_e=k_e, n_f=n_f, k_f=k_f, link=link, k_c=k_c, place=place)


def valid(d):
    tier = lambda s: "edge" if s == "src" else d["place"][s]
    return all(LEVEL[tier(b)] >= LEVEL[tier(a)] for a, b, _ in GRAPH)


def objectives(d, wl):
    lam = Q(wl.Lambda)
    nodes = {"edge": (d["n_e"], d["k_e"]), "fog": (d["n_f"], d["k_f"]), "cloud": (1, d["k_c"])}
    w = dict(zip(STAGE_NAMES, [Q(v) for v in wl.w]))
    rho = {}
    for t, (n, c) in nodes.items():
        rho[t] = lam * sum((w[s] for s in STAGE_NAMES if d["place"][s] == t), Q(0)) / (Q(n) * Q(c.C))
    used = set(d["place"].values())
    if any(rho[t] >= 1 for t in used):
        return None
    tau = {}
    for s in STAGE_NAMES:
        t = d["place"][s]
        base = w[s] / Q(nodes[t][1].C)
        tau[s] = base + base * rho[t] / (2 * (1 - rho[t]))
    tier = lambda s: "edge" if s == "src" else d["place"][s]

    def crossed(a, b):
        lo, hi = LEVEL[tier(a)], LEVEL[tier(b)]
        links = []
        if lo == 0 and hi >= 1:
            links.append("acc")
        if lo <= 1 and hi == 2:
            links.append("wan")
        return links

    def chi(a, b, k):
        s_e = Q(wl.s_in[k])
        out = Q(0)
        for l in crossed(a, b):
            if l == "acc":
                out += 8 * s_e / Q(d["link"].B) + Q(d["link"].prop)
            else:
                out += 8 * s_e / Q(tb.WAN_B) + Q(tb.WAN_PROP)
        return out

    x = {(a, b): chi(a, b, k) for a, b, k in GRAPH}
    L = (x[("src", "I")] + tau["I"] + x[("I", "F")] + tau["F"]
         + max(x[("F", "A")] + tau["A"] + x[("A", "N")] + tau["N"], x[("F", "R")] + tau["R"]))
    T = Q(wl.horizon)
    E = Q(0)
    for t in ("edge", "fog"):
        n, c = nodes[t]
        E += Q(n) * (Q(c.P_idle) + rho[t] * (Q(c.P_peak) - Q(c.P_idle))) * T
    E += rho["cloud"] * Q(d["k_c"].P_peak) * T
    D = Q(0)
    for a, b, k in GRAPH:
        for l in crossed(a, b):
            E += Q(wl.s_in[k]) * lam * Q(d["link"].e if l == "acc" else tb.WAN_E) * T
            D += Q(wl.s_in[k]) * lam
    C = (Q(d["n_e"]) * (Q(d["k_e"].cost) + Q(d["link"].cost))
         + Q(d["n_f"]) * (Q(d["k_f"].cost) + Q(d["link"].cost)) + Q(d["k_c"].cost))
    feasible = (all(rho[t] <= Q(wl.rho_max) for t in used) and L <= Q(wl.deadline)
                and C <= Q(wl.C_max) and E <= Q(wl.E_max))
    return (L, E, C, D), feasible, max(rho[t] for t in used)


def pareto(vectors):
    vs = set(vectors)
    return sorted(v for v in vs
                  if not any(u != v and all(u[i] <= v[i] for i in range(4)) for u in vs))


def to_prod(d):
    x = dict(n_e=d["n_e"], k_e=d["k_e"], n_f=d["n_f"], k_f=d["k_f"], link=d["link"], k_c=d["k_c"])
    for s, var in zip(STAGE_NAMES, tb.PLACE):
        x[var] = d["place"][s]
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", default="B1,B2", help="scales compared design by design")
    ap.add_argument("--sample", default="B3", help="scales compared on a sample")
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--out", default="results/e19_template_b/oracle.json")
    ap.add_argument("--front-only", default=None,
                    help="scale:workload; compare only the fronts (reference implementation, "
                         "stored exhaustive front, search)")
    a = ap.parse_args()
    if a.front_only:
        scale, wname = a.front_only.split(":")
        wl = tb.WORKLOADS[wname]
        vecs = []
        for d in designs(scale):
            if valid(d):
                r = objectives(d, wl)
                if r is not None and r[1]:
                    vecs.append(tuple(r[0]))
        ref_front = pareto(vecs)
        stored = Path(a.out).parent / "reference" / ("%s_%s.json" % (scale, wname))
        stored = sorted(tuple(Q(v) for v in r) for r in json.loads(stored.read_text()))
        row = dict(scale=scale, workload=wname, feasible=len(vecs), front=len(ref_front),
                   stored_front_equal=stored == ref_front,
                   search_front_equal=sorted(tb.search(scale, wl).front) == ref_front)
        print(json.dumps(row))
        Path(a.out).write_text(json.dumps([row], indent=1) + "\n")
        assert row["stored_front_equal"] and row["search_front_equal"], row
        return
    # the search is also run with two other variable orders on the fully compared scales
    rows = []
    for scale in [s for s in a.full.split(",") if s] + [s for s in a.sample.split(",") if s]:
        full = scale in a.full.split(",")
        for wname, wl in tb.WORKLOADS.items():
            all_d = [d for d in designs(scale) if valid(d)]
            prod_valid = len(all_d)
            if full:
                picked = all_d
            else:
                rng = random.Random(20261119)
                picked = rng.sample(all_d, min(a.n, len(all_d)))
            mism_feas = mism_obj = near = 0
            feas_vectors = []
            for d in picked:
                ref = objectives(d, wl)
                f, ok = tb.evaluate(to_prod(d), wl, exact=True)
                if ref is None:
                    mism_feas += ok
                    mism_obj += f[0] != tb.INF
                    continue
                vec, feasible, rho_max = ref
                mism_feas += feasible != ok
                mism_obj += tuple(vec) != tuple(f)
                if (abs(vec[0] - Q(wl.deadline)) <= Q(wl.deadline) / 50
                        or abs(rho_max - Q(wl.rho_max)) <= Q(1, 50)):
                    near += 1
                if feasible:
                    feas_vectors.append(tuple(vec))
            row = dict(scale=scale, workload=wname, compared=len(picked),
                       structurally_valid=prod_valid, near_boundary=near,
                       feasibility_mismatches=mism_feas, objective_mismatches=mism_obj)
            if full:
                ref_front = pareto(feas_vectors)
                got = sorted(tb.search(scale, wl).front)
                gen = sorted(tb.search(scale, wl, relax=False).front)
                orders = [tuple(reversed(tb.ORDER)),
                          tb.PLACE + ("link", "k_c", "k_f", "n_f", "k_e", "n_e")]
                alt = [sorted(tb.search(scale, wl, order=o).front) == ref_front for o in orders]
                row.update(front=len(ref_front), search_front_equal=got == ref_front,
                           generic_front_equal=gen == ref_front,
                           other_orders=len(orders), other_orders_equal=all(alt),
                           production_valid=tb.exhaustive(scale, wl).evals)
                assert row["production_valid"] == prod_valid
            rows.append(row)
            print(json.dumps(row), flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rows, indent=1) + "\n")
    bad = [r for r in rows if r["feasibility_mismatches"] or r["objective_mismatches"]
           or r.get("search_front_equal") is False or r.get("generic_front_equal") is False
           or r.get("other_orders_equal") is False]
    assert not bad, bad


if __name__ == "__main__":
    main()
