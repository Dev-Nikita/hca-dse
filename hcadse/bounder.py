"""Cached implementation of the admissible bounds (Gate 6).

Mathematically identical to `bounds.lower_bounds`, but every term that depends
only on the *classes* still reachable (and not on the node counts) is memoised,
so the per-node bound cost C_P drops well below the full evaluation cost C_E.
"""
from __future__ import annotations
from typing import Dict, List
from .model import DesignSpace, POLICIES, WAN_B, WAN_PROP, WAN_E
from .evaluate import MB_TO_MB
from .bounds import _comm_latency_lb, _net_MB_lb, _queue_bound, INF
from .numeric import deployment_cost_decimal
from .intervals import certified_lower_bounds, lower_float


class Bounder:
    def __init__(self, space: DesignSpace, wl, use_queue_bound=True):
        self.use_queue_bound = use_queue_bound
        self.space, self.wl = space, wl
        self._proc: Dict = {}
        self._comm: Dict = {}
        self._net: Dict = {}
        self._dyn: Dict = {}
        # domain aggregates for the free (unassigned) case
        self.d = {}
        for v in ("edge_cls", "gw_cls", "cloud_cls"):
            dom = space.domain(v)
            self.d[v] = dict(C_max=max(c.C for c in dom),
                             cost_min=min(c.cost for c in dom),
                             P_idle_min=min(c.P_idle for c in dom))
        lk = space.domain("link_cls")
        self.d["link_cls"] = dict(B_max=max(l.B for l in lk),
                                  prop_min=min(l.prop for l in lk),
                                  e_min=min(l.e for l in lk),
                                  cost_min=min(l.cost for l in lk))
        self.d["n_e"] = min(space.domain("n_e"))
        self.d["n_g"] = min(space.domain("n_g"))
        self.d["rep"] = min(space.domain("rep"))
        self.calls = 0

    @staticmethod
    def certified_objectives(design, workload):
        from .intervals import certified_objectives
        return certified_objectives(design, workload)

    # ---- per-variable reachable aggregates (O(1)) --------------------------
    def _cls(self, partial, var, field):
        v = partial.get(var)
        if v is None:
            return self.d[var][field]
        if field == "C_max":
            return v.C
        if field == "cost_min":
            return v.cost
        if field == "P_idle_min":
            return v.P_idle
        if field == "B_max":
            return v.B
        if field == "prop_min":
            return v.prop
        if field == "e_min":
            return v.e
        raise KeyError(field)

    def _tier_opts(self, pol_key):
        pols = list(POLICIES) if pol_key is None else [pol_key]
        opts = []
        for i in range(3):
            o = set()
            for p in pols:
                t1, t3 = POLICIES[p]
                o.add(t1 if i == 0 else ("gw" if i == 1 else t3))
            opts.append(o)
        return opts

    def _compute_bounds(self, partial: dict, certify: bool) -> Dict[str, float]:
        self.calls += 1
        wl, lam, st = self.wl, self.wl.Lambda, self.wl.stages
        pol_key = partial.get("policy")
        ek, gk, ck = partial.get("edge_cls"), partial.get("gw_cls"), partial.get("cloud_cls")
        lkk = partial.get("link_cls")
        rep_min = partial["rep"] if "rep" in partial else self.d["rep"]
        ne_min = partial["n_e"] if "n_e" in partial else self.d["n_e"]
        ng_min = partial["n_g"] if "n_g" in partial else self.d["n_g"]

        # --- processing latency (cached) ---
        key = (ek, gk, ck, pol_key)
        L = self._proc.get(key)
        if L is None:
            tier_C = {"edge": self._cls(partial, "edge_cls", "C_max"),
                      "gw": self._cls(partial, "gw_cls", "C_max"),
                      "cloud": self._cls(partial, "cloud_cls", "C_max")}
            L = sum(min(st[i].w / tier_C[t] for t in o)
                    for i, o in enumerate(self._tier_opts(pol_key)))
            self._proc[key] = L

        # --- communication latency (cached) ---
        key = (lkk, pol_key, rep_min)
        c = self._comm.get(key)
        if c is None:
            B_max = self._cls(partial, "link_cls", "B_max")
            prop_min = self._cls(partial, "link_cls", "prop_min")
            pols = list(POLICIES) if pol_key is None else [pol_key]
            c = min(_comm_latency_lb(p, [rep_min], wl, B_max, prop_min) for p in pols)
            self._comm[key] = c
        L += c
        if self.use_queue_bound:
            L += _queue_bound(partial, self.space, wl)

        # --- network volume (cached) ---
        key = (pol_key, rep_min)
        n = self._net.get(key)
        if n is None:
            pols = list(POLICIES) if pol_key is None else [pol_key]
            n = min(_net_MB_lb(p, [rep_min], wl) for p in pols)
            self._net[key] = n
        D = n * lam

        # --- energy ---
        T = wl.horizon
        E = ne_min * self._cls(partial, "edge_cls", "P_idle_min") * T
        E += ng_min * self._cls(partial, "gw_cls", "P_idle_min") * T
        key = (ek, gk, ck, pol_key, rep_min)
        dyn = self._dyn.get(key)
        if dyn is None:
            def dmin(var, cloud=False):
                v = partial.get(var)
                dom = [v] if v is not None else self.space.domain(var)
                return min((c.P_peak / c.C) if cloud else ((c.P_peak - c.P_idle) / c.C)
                           for c in dom)
            per = {"edge": dmin("edge_cls"), "gw": dmin("gw_cls"),
                   "cloud": dmin("cloud_cls", True)}
            dyn = sum(lam * st[i].w * (rep_min if i == 0 else 1) *
                      min(per[t] for t in o) * T
                      for i, o in enumerate(self._tier_opts(pol_key)))
            self._dyn[key] = dyn
        E += dyn + n * lam * min(self._cls(partial, "link_cls", "e_min"), WAN_E) * T

        # --- cost ---
        lcost = min(l.cost for l in ([lkk] if lkk else self.space.domain("link_cls")))
        C_exact = deployment_cost_decimal(
            ne_min, self._cls(partial, "edge_cls", "cost_min"),
            ng_min, self._cls(partial, "gw_cls", "cost_min"), lcost,
            self._cls(partial, "cloud_cls", "cost_min"))
        C = float(C_exact)

        if not certify:
            return {"L": L, "E": E, "C": C, "C_exact": C_exact, "D": D,
                    "_legacy": {"L": L, "E": E, "C": C, "D": D}}
        certified = certified_lower_bounds(partial, self.space, wl)
        return {"L": lower_float(certified["L"].lo),
                "E": lower_float(certified["E"].lo),
                "C": lower_float(certified["C"].lo),
                "C_exact": certified["C"].lo,
                "D": lower_float(certified["D"].lo),
                "_intervals": certified,
                "_legacy": {"L": L, "E": E, "C": C, "D": D}}

    def fast_bounds(self, partial: dict) -> Dict[str, float]:
        """Unsound proposal only; search must certify before pruning."""
        return self._compute_bounds(partial, certify=False)

    def bounds(self, partial: dict) -> Dict[str, float]:
        return self._compute_bounds(partial, certify=True)

    def certify(self, partial: dict) -> Dict[str, float]:
        return self._compute_bounds(partial, certify=True)
