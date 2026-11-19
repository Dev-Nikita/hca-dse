"""Bounders for the controlled comparison of Section 6: same traversal order,
same feasibility and dominance rules, different bounds only.

G1  partial-cost bound (the assignment-monotone construction): a term enters the
    bound only once the assigned variables determine it; everything else is zero.
    This is the generic branch-and-bound bound, independent of this model.
G2  the published HCA-DSE bound, with the contention term bounded by zero until
    its determinants are fixed (hcadse.bounder.Bounder with use_queue_bound).
G3  G2 plus the positive waiting bound of hcadse.partialqueue.
"""
from __future__ import annotations

from typing import Dict

from hcadse.bounder import Bounder
from hcadse.intervals import DINF, Interval, certified_objectives, lower_float
from hcadse.model import POLICIES, WAN_B, WAN_E, WAN_PROP
from hcadse.numeric import decimal_value
from hcadse.partialqueue import positive_queue_lower


class PositiveQueueBounder(Bounder):
    """G3: the published bound plus a positive bound on the undetermined tiers."""

    def _compute_bounds(self, partial: dict, certify: bool) -> Dict[str, float]:
        out = super()._compute_bounds(partial, certify)
        extra = positive_queue_lower(partial, self.space, self.wl)
        if extra.lo <= 0:
            return out
        out = dict(out)
        if "_intervals" in out:
            intervals = dict(out["_intervals"])
            if extra.lo >= DINF:
                intervals["L"] = Interval(DINF, DINF)
            else:
                intervals["L"] = intervals["L"] + Interval(extra.lo, extra.lo)
            out["_intervals"] = intervals
            out["L"] = lower_float(intervals["L"].lo)
        else:
            # the uncertified proposal path: a float proposal, certified later
            out["L"] = (float("inf") if extra.lo >= DINF
                        else out["L"] + lower_float(extra.lo))
        return out


class PartialCostBounder:
    """G1: the assignment-monotone partial cost, computed in the same interval
    type as the published bound.

    A contribution enters only when the assigned variables determine it: a
    stage's processing and waiting time once its tier, that tier's class, its
    node count, the replication factor and the policy are all assigned; a hop's
    transfer time once the policy, the replication factor and the link class are
    assigned; node cost and idle energy once the count and the class are
    assigned.  Nothing else contributes.  This is admissible because every
    omitted term is non-negative, and it is the bound a generic multi-objective
    branch-and-bound has without the relaxations of Section 4.2.
    """

    certified_objectives = staticmethod(certified_objectives)

    def __init__(self, space, wl, use_queue_bound=True):
        self.space, self.wl, self.calls = space, wl, 0
        self.use_queue_bound = use_queue_bound

    # -- the four objectives -------------------------------------------------
    def _bounds(self, p: dict) -> Dict[str, Interval]:
        wl = self.wl
        zero = Interval.point(0)
        latency = zero
        energy = zero
        cost = zero
        volume = zero
        arrival = Interval.point(wl.n_dev) * wl.rate
        horizon = Interval.point(wl.horizon)

        tiers = None
        if "policy" in p:
            t1, t3 = POLICIES[p["policy"]]
            tiers = (t1, "gw", t3)

        # node cost and idle energy: determined by count and class
        for count_key, class_key in (("n_e", "edge_cls"), ("n_g", "gw_cls")):
            if count_key in p and class_key in p:
                cls = p[class_key]
                cost += Interval.point(p[count_key]) * cls.cost
                energy += Interval.point(p[count_key]) * cls.P_idle * horizon
                if "link_cls" in p:
                    cost += Interval.point(p[count_key]) * p["link_cls"].cost
        if "cloud_cls" in p:
            cost += Interval.point(p["cloud_cls"].cost)

        # processing, waiting and dynamic energy: determined per tier
        if tiers is not None and "rep" in p:
            for tier, requirements in (("edge", ("n_e", "edge_cls")),
                                       ("gw", ("n_g", "gw_cls")),
                                       ("cloud", ("cloud_cls",))):
                if any(name not in p for name in requirements):
                    continue
                indices = [i for i, t in enumerate(tiers) if t == tier]
                if not indices:
                    continue
                cls = p[requirements[-1]]
                count = p[requirements[0]] if len(requirements) == 2 else 1
                load = zero
                for index in indices:
                    multiplier = p["rep"] if index == 0 else 1
                    load += arrival * wl.stages[index].w * multiplier
                rho = load / (Interval.point(count) * cls.C)
                if rho.hi >= 1:
                    return {"L": Interval(DINF, DINF), "E": Interval(DINF, DINF),
                            "C": Interval(DINF, DINF), "D": Interval(DINF, DINF)}
                for index in indices:
                    service = Interval.point(wl.stages[index].w) / cls.C
                    latency += service
                    if self.use_queue_bound:
                        latency += (service * rho
                                    / (Interval.point(2) * (Interval.point(1) - rho)))
                dynamic = Interval.point(cls.P_peak - cls.P_idle) if tier != "cloud" \
                    else Interval.point(cls.P_peak)
                energy += rho * dynamic * horizon * Interval.point(count)

        # communication: determined by policy, replication and link class
        if tiers is not None and "rep" in p and "link_cls" in p:
            link = p["link_cls"]
            stages = [s.s_in for s in wl.stages]
            hops = [(stages[0], "access")]
            if tiers[0] == "edge":
                hops.append((stages[1], "access"))
                if p["rep"] > 1:
                    hops.append(((p["rep"] - 1) * wl.s_sync, "access"))
            hops.append((stages[2], "wan" if tiers[2] == "cloud" else "access"))
            for payload, kind in hops:
                payload_i = Interval.point(payload)
                if kind == "access":
                    latency += payload_i * 8 / Interval.point(link.B) \
                        + Interval.point(link.prop)
                    energy += payload_i * arrival * link.e * horizon
                else:
                    latency += payload_i * 8 / Interval.point(WAN_B) \
                        + Interval.point(WAN_PROP)
                    energy += payload_i * arrival * WAN_E * horizon
                volume += payload_i * arrival
        return {"L": latency, "E": energy, "C": cost, "D": volume}

    def _wrap(self, p):
        self.calls += 1
        intervals = self._bounds(p)
        return {"L": lower_float(intervals["L"].lo),
                "E": lower_float(intervals["E"].lo),
                "C": lower_float(intervals["C"].lo),
                "C_exact": intervals["C"].lo,
                "D": lower_float(intervals["D"].lo),
                "_intervals": intervals}

    def fast_bounds(self, p):
        return self._wrap(p)

    def bounds(self, p):
        return self._wrap(p)

    def certify(self, p):
        return self._wrap(p)


class CachedPartialCostBounder(PartialCostBounder):
    """G1c: the generic bound with the two-stage protocol and the component
    caching that the published bound enjoys.

    The published implementation proposes a cheap floating-point bound at every
    node and pays for the certified interval arithmetic only when that proposal
    suggests pruning (`hcadse.bounder.Bounder.fast_bounds` / `certify`), and it
    memoises the parts of the bound that depend only on the assigned classes.
    Granting the generic bound the same two devices removes the implementation
    difference from the wall-clock comparison: what remains is the bound.
    """

    def __init__(self, space, wl, use_queue_bound=True):
        super().__init__(space, wl, use_queue_bound=use_queue_bound)
        self._cache = {}

    # -- the cheap proposal: the same terms in binary64 ----------------------
    def _float_bounds(self, p: dict):
        wl = self.wl
        latency = energy = cost = volume = 0.0
        arrival = wl.n_dev * wl.rate
        horizon = wl.horizon
        tiers = None
        if "policy" in p:
            t1, t3 = POLICIES[p["policy"]]
            tiers = (t1, "gw", t3)
        for count_key, class_key in (("n_e", "edge_cls"), ("n_g", "gw_cls")):
            if count_key in p and class_key in p:
                cls = p[class_key]
                cost += p[count_key] * cls.cost
                energy += p[count_key] * cls.P_idle * horizon
                if "link_cls" in p:
                    cost += p[count_key] * p["link_cls"].cost
        if "cloud_cls" in p:
            cost += p["cloud_cls"].cost
        if tiers is not None and "rep" in p:
            for tier, requirements in (("edge", ("n_e", "edge_cls")),
                                       ("gw", ("n_g", "gw_cls")),
                                       ("cloud", ("cloud_cls",))):
                if any(name not in p for name in requirements):
                    continue
                indices = [i for i, t in enumerate(tiers) if t == tier]
                if not indices:
                    continue
                cls = p[requirements[-1]]
                count = p[requirements[0]] if len(requirements) == 2 else 1
                load = sum(arrival * wl.stages[i].w * (p["rep"] if i == 0 else 1)
                           for i in indices)
                rho = load / (count * cls.C)
                if rho >= 1.0:
                    return {"L": float("inf"), "E": float("inf"),
                            "C": float("inf"), "D": float("inf")}
                for index in indices:
                    service = wl.stages[index].w / cls.C
                    latency += service
                    if self.use_queue_bound:
                        latency += service * rho / (2.0 * (1.0 - rho))
                peak = cls.P_peak if tier == "cloud" else cls.P_peak - cls.P_idle
                energy += rho * peak * horizon * count
        if tiers is not None and "rep" in p and "link_cls" in p:
            link = p["link_cls"]
            stages = [s.s_in for s in wl.stages]
            hops = [(stages[0], "access")]
            if tiers[0] == "edge":
                hops.append((stages[1], "access"))
                if p["rep"] > 1:
                    hops.append(((p["rep"] - 1) * wl.s_sync, "access"))
            hops.append((stages[2], "wan" if tiers[2] == "cloud" else "access"))
            for payload, kind in hops:
                if kind == "access":
                    latency += payload * 8 / link.B + link.prop
                    energy += payload * arrival * link.e * horizon
                else:
                    latency += payload * 8 / WAN_B + WAN_PROP
                    energy += payload * arrival * WAN_E * horizon
                volume += payload * arrival
        return {"L": latency, "E": energy, "C": cost, "D": volume}

    @staticmethod
    def _key(p):
        return tuple(sorted((k, getattr(v, "name", v)) for k, v in p.items()))

    def fast_bounds(self, p):
        self.calls += 1
        key = self._key(p)
        cached = self._cache.get(key)
        if cached is None:
            cached = self._float_bounds(p)
            self._cache[key] = cached
        out = dict(cached)
        out["C_exact"] = decimal_value(out["C"]) if out["C"] != float("inf") else None
        if out["C_exact"] is None:
            del out["C_exact"]
        return out

    def bounds(self, p):
        return self._wrap(p)

    def certify(self, p):
        return self._wrap(p)
