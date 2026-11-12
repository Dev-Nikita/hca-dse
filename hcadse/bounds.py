"""Admissible objective lower bounds for partial designs (Propositions 1-2)."""
from __future__ import annotations
from typing import Dict, List, Optional
from .model import DesignSpace, VAR_ORDER, POLICIES, WAN_B, WAN_PROP, WAN_E
from .evaluate import MB_TO_MB
from .numeric import decimal_value, deployment_cost_decimal
from .intervals import certified_lower_bounds, lower_float

INF = float("inf")


def _dom(space: DesignSpace, partial: dict, var: str) -> List:
    """Values still reachable for `var` (a singleton if already assigned)."""
    return [partial[var]] if var in partial else space.domain(var)


def _policies(space, partial):
    return _dom(space, partial, "policy")


def lower_bounds(partial: dict, space: DesignSpace, wl) -> Dict[str, float]:
    """Objective-wise optimistic bounds: LB_i(partial) <= f_i(x) for every
    completion x of `partial`. Every term is replaced by its minimum over the
    still-reachable domains, independently per term (a valid relaxation)."""
    st = wl.stages
    lam = wl.Lambda
    edge_d = _dom(space, partial, "edge_cls")
    gw_d = _dom(space, partial, "gw_cls")
    cl_d = _dom(space, partial, "cloud_cls")
    lk_d = _dom(space, partial, "link_cls")
    ne_d = _dom(space, partial, "n_e")
    ng_d = _dom(space, partial, "n_g")
    rep_d = _dom(space, partial, "rep")
    pol_d = _policies(space, partial)

    Ce_max = max(c.C for c in edge_d); Cg_max = max(c.C for c in gw_d)
    Cc_max = max(c.C for c in cl_d)
    B_max = max(l.B for l in lk_d); prop_min = min(l.prop for l in lk_d)
    e_min = min(l.e for l in lk_d)

    # ---- latency -----------------------------------------------------------
    # processing: each stage on the fastest tier it can still be placed on
    tier_C = {"edge": Ce_max, "gw": Cg_max, "cloud": Cc_max}
    L = 0.0
    for i, s in enumerate(st):
        opts = set()
        for p in pol_d:
            t1, t3 = POLICIES[p]
            opts.add(t1 if i == 0 else ("gw" if i == 1 else t3))
        L += min(s.w / tier_C[t] for t in opts)
    # queueing: exact only when all determinants of a tier are fixed, else 0
    L += _queue_bound(partial, space, wl)
    # communication: cheapest reachable hop set
    L += min(_comm_latency_lb(p, rep_d, wl, B_max, prop_min) for p in pol_d)

    # ---- energy ------------------------------------------------------------
    T = wl.horizon
    E = min(ne_d) * min(c.P_idle for c in edge_d) * T
    E += min(ng_d) * min(c.P_idle for c in gw_d) * T
    # dynamic energy is independent of node count: lam*w*(P_peak-P_idle)/C
    dyn = {"edge": min((c.P_peak - c.P_idle) / c.C for c in edge_d),
           "gw": min((c.P_peak - c.P_idle) / c.C for c in gw_d),
           "cloud": min(c.P_peak / c.C for c in cl_d)}
    for i, s in enumerate(st):
        opts = set()
        for p in pol_d:
            t1, t3 = POLICIES[p]
            opts.add(t1 if i == 0 else ("gw" if i == 1 else t3))
        mult = min(rep_d) if i == 0 else 1
        E += lam * s.w * mult * min(dyn[t] for t in opts) * T
    E += min(_net_MB_lb(p, rep_d, wl) for p in pol_d) * lam * min(e_min, WAN_E) * T

    # ---- cost --------------------------------------------------------------
    C_exact = deployment_cost_decimal(
        min(ne_d), min(c.cost for c in edge_d), min(ng_d),
        min(c.cost for c in gw_d), min(l.cost for l in lk_d),
        min(c.cost for c in cl_d))
    C = float(C_exact)

    # ---- network volume ----------------------------------------------------
    D = min(_net_MB_lb(p, rep_d, wl) for p in pol_d) * lam

    certified = certified_lower_bounds(partial, space, wl)
    return {"L": lower_float(certified["L"].lo),
            "E": lower_float(certified["E"].lo),
            "C": lower_float(certified["C"].lo),
            "C_exact": certified["C"].lo,
            "D": lower_float(certified["D"].lo),
            "_intervals": certified,
            "_legacy": {"L": L, "E": E, "C": C, "D": D}}


def _net_MB_lb(policy: str, rep_d, wl) -> float:
    t1, t3 = POLICIES[policy]
    s = [x.s_in for x in wl.stages]
    v = s[0] + s[2]
    if t1 == "edge":
        v += s[1] + (min(rep_d) - 1) * wl.s_sync
    return v


def _comm_latency_lb(policy, rep_d, wl, B_max, prop_min) -> float:
    t1, t3 = POLICIES[policy]
    s = [x.s_in for x in wl.stages]
    L = s[0] * MB_TO_MB / B_max + prop_min
    if t1 == "edge":
        L += s[1] * MB_TO_MB / B_max + prop_min
        if min(rep_d) > 1:
            L += (min(rep_d) - 1) * wl.s_sync * MB_TO_MB / B_max + prop_min
    if t3 == "cloud":
        L += s[2] * MB_TO_MB / WAN_B + WAN_PROP
    else:
        L += s[2] * MB_TO_MB / B_max + prop_min
    return L


def _queue_bound(partial: dict, space: DesignSpace, wl) -> float:
    """Exact queueing delay of a tier whose load and capacity are already
    determined by the assigned variables; 0 (optimistic) otherwise."""
    if "policy" not in partial or "rep" not in partial:
        return 0.0
    t1, t3 = POLICIES[partial["policy"]]
    tiers = (t1, "gw", t3)
    lam, rep = wl.Lambda, partial["rep"]
    total = 0.0
    for tier, need in (("edge", ("n_e", "edge_cls")), ("gw", ("n_g", "gw_cls")),
                       ("cloud", ("cloud_cls",))):
        if any(k not in partial for k in need):
            continue
        idx = [i for i, t in enumerate(tiers) if t == tier]
        if not idx:
            continue
        cls = partial[need[-1]]
        n = partial[need[0]] if len(need) == 2 else 1
        load = sum(lam * wl.stages[i].w * (rep if i == 0 else 1) for i in idx)
        rho = load / (n * cls.C)
        if rho >= 1.0:
            return INF
        for i in idx:
            total += (wl.stages[i].w / cls.C) * rho / (2.0 * (1.0 - rho))
    return total


def infeasible_by_bounds(lb: Dict[str, float], wl) -> bool:
    """Proposition 1: no completion can satisfy the hard constraints."""
    cost = lb.get("C_exact", decimal_value(lb["C"]))
    return lb["L"] > wl.deadline or cost > decimal_value(wl.C_max) or lb["E"] > wl.E_max


def dominated_by_bounds(lb: Dict[str, float], archive) -> bool:
    """Proposition 2: an evaluated feasible design dominates the optimistic
    vector of the partial design, so no completion can be Pareto-optimal."""
    if "_intervals" in lb and archive and isinstance(archive[0], dict):
        lower = tuple(lb["_intervals"][name].lo for name in ("L", "E", "C", "D"))
        for point in archive:
            upper = point["upper"]
            if all(upper[i] <= lower[i] for i in range(4)) and \
                    any(upper[i] < lower[i] for i in range(4)):
                return True
        return False
    v = (lb["L"], lb["E"], lb["C"], lb["D"])
    for f in archive:
        if all(f[i] <= v[i] for i in range(4)) and any(f[i] < v[i] for i in range(4)):
            return True
    return False
