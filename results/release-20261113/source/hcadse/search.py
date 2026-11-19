"""Search strategies: exhaustive ground truth, HCA-DSE, random baseline."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import random, time
from .model import DesignSpace, VAR_ORDER
from .evaluate import evaluate
from .bounds import lower_bounds, infeasible_by_bounds, dominated_by_bounds
from .bounder import Bounder
from .intervals import certified_objectives


# ---------------------------------------------------------------------------
# structural validity (Stage 1)
# ---------------------------------------------------------------------------

def structurally_valid(partial: dict) -> bool:
    if "n_g" in partial and "n_e" in partial and partial["n_g"] > partial["n_e"]:
        return False
    if "rep" in partial and "n_e" in partial and partial["rep"] > partial["n_e"]:
        return False
    if "rep" in partial and "policy" in partial and partial["policy"] == "cloud-first" \
            and partial["rep"] > 1:
        return False  # no edge instances to replicate
    return True


def pareto_front(points: List[Tuple[dict, tuple]]) -> List[Tuple[dict, tuple]]:
    out = []
    for xa, fa in points:
        dom = False
        for xb, fb in points:
            if all(fb[i] <= fa[i] for i in range(len(fa))) and \
               any(fb[i] < fa[i] for i in range(len(fa))):
                dom = True
                break
        if not dom:
            out.append((xa, fa))
    return out


@dataclass
class SearchStats:
    method: str
    n_raw: int = 0
    n_structural: int = 0
    n_feasible_bound: int = 0
    n_evaluated: int = 0
    n_feasible: int = 0
    runtime: float = 0.0
    pruned_structural: int = 0
    pruned_bound: int = 0
    pruned_dominance: int = 0
    proposal_count: int = 0
    structural_rejections: int = 0
    feasibility_rejections: int = 0
    queue_active_partial: int = 0
    queue_pruned_partial: int = 0
    n_bound_calls: int = 0
    n_nodes: int = 0          # partial states visited (never materialises |X|)
    t_bounds: float = 0.0
    t_eval: float = 0.0
    t_dominance: float = 0.0
    t_pareto: float = 0.0
    front: List[Tuple[dict, tuple]] = field(default_factory=list)


def exhaustive(space: DesignSpace, wl) -> SearchStats:
    t0 = time.perf_counter()
    s = SearchStats("exhaustive", n_raw=space.size)
    pts = []
    for x in space.enumerate():
        if not structurally_valid(x):
            s.pruned_structural += 1
            continue
        s.n_structural += 1
        s.n_evaluated += 1
        te = time.perf_counter()
        r = evaluate(x, wl)
        s.t_eval += time.perf_counter() - te
        if r.feasible:
            s.n_feasible += 1
            pts.append((x, r.objectives))
    tp = time.perf_counter()
    s.front = pareto_front(pts)
    s.t_pareto = time.perf_counter() - tp
    s.runtime = time.perf_counter() - t0
    return s


def hca_dse(space: DesignSpace, wl, use_bounds=True, use_dominance=True,
            use_structural=True, record_pruned=None, variable_order=None,
            use_queue_bound=True, measure_queue=False, record_decisions=None) -> SearchStats:
    """Hierarchical constraint-aware DFS over the prefix tree."""
    t0 = time.perf_counter()
    s = SearchStats("hca-dse", n_raw=space.size)
    archive: List[dict] = []           # certified archive points used only for pruning
    pts: List[Tuple[dict, tuple]] = []
    order = list(VAR_ORDER if variable_order is None else variable_order)
    if len(order) != len(VAR_ORDER) or set(order) != set(VAR_ORDER):
        raise ValueError("variable_order must be a permutation of VAR_ORDER")
    bd = Bounder(space, wl, use_queue_bound=use_queue_bound)
    bd_noqueue = Bounder(space, wl, use_queue_bound=False) if measure_queue else None

    def archive_add(x: dict, f: tuple):
        certifier = getattr(bd, "certified_objectives", certified_objectives)
        intervals = certifier(x, wl)
        archive.append({"value": f, "upper": tuple(interval.hi for interval in intervals)})

    def subtree_size(depth: int) -> int:
        n = 1
        for v in order[depth:]:
            n *= len(space.domain(v))
        return n

    def rec(depth: int, partial: dict):
        s.n_nodes += 1
        if depth == len(order):
            s.n_evaluated += 1
            te = time.perf_counter()
            r = evaluate(partial, wl)
            s.t_eval += time.perf_counter() - te
            if r.feasible:
                s.n_feasible += 1
                pts.append((dict(partial), r.objectives))
                archive_add(partial, r.objectives)
            return
        var = order[depth]
        for val in space.domain(var):
            s.proposal_count += 1
            nxt = dict(partial); nxt[var] = val
            if use_structural and not structurally_valid(nxt):
                s.pruned_structural += subtree_size(depth + 1)
                if record_pruned is not None:
                    record_pruned.append(("structural", dict(nxt)))
                continue
            if use_bounds or use_dominance:
                tb = time.perf_counter()
                # Instrumentation must not change the search policy.  In particular,
                # measure_queue previously disabled the fast-proposal/certification
                # protocol and could therefore visit a different tree from the run it
                # was intended to describe.
                two_stage = hasattr(bd, "fast_bounds") and hasattr(bd, "certify")
                proposal = bd.fast_bounds(nxt) if two_stage else bd.bounds(nxt)
                fast_infeasible = use_bounds and infeasible_by_bounds(proposal, wl)
                fast_dominated = False
                if use_dominance and archive:
                    vector = (proposal["L"], proposal["E"], proposal["C"], proposal["D"])
                    fast_dominated = any(
                        all(point["value"][i] <= vector[i] for i in range(4)) and
                        any(point["value"][i] < vector[i] for i in range(4))
                        for point in archive)
                lb = (bd.certify(nxt) if two_stage and (fast_infeasible or fast_dominated)
                      else proposal)
                if measure_queue and use_queue_bound and depth + 1 < len(order):
                    from .bounds import _queue_bound
                    qdelay = _queue_bound(nxt, space, wl)
                    if qdelay > 0:
                        s.queue_active_partial += 1
                        noqueue = bd_noqueue.bounds(nxt)
                        # The diagnostic comparison is certified independently, but
                        # only `lb` and `certified_candidate` below may authorize the
                        # actual pruning decision.
                        audit_with_q = bd.certify(nxt)
                        with_q = ((use_bounds and infeasible_by_bounds(audit_with_q, wl)) or
                                  (use_dominance and dominated_by_bounds(audit_with_q, archive)))
                        without_q = ((use_bounds and infeasible_by_bounds(noqueue, wl)) or
                                     (use_dominance and dominated_by_bounds(noqueue, archive)))
                        if with_q and not without_q:
                            s.queue_pruned_partial += 1
                s.t_bounds += time.perf_counter() - tb
                certified_candidate = (not two_stage) or (fast_infeasible or fast_dominated)
                if certified_candidate and use_bounds and infeasible_by_bounds(lb, wl):
                    s.pruned_bound += subtree_size(depth + 1)
                    if record_pruned is not None:
                        record_pruned.append(("feasibility", dict(nxt)))
                    if record_decisions is not None:
                        record_decisions.append({"kind": "feasibility", "partial": dict(nxt),
                                                 "bounds": lb})
                    continue
                td = time.perf_counter()
                dom = (certified_candidate and use_dominance and
                       dominated_by_bounds(lb, archive))
                s.t_dominance += time.perf_counter() - td
                if dom:
                    s.pruned_dominance += subtree_size(depth + 1)
                    if record_pruned is not None:
                        record_pruned.append(("dominance", dict(nxt)))
                    if record_decisions is not None:
                        lower = tuple(lb["_intervals"][name].lo
                                      for name in ("L", "E", "C", "D"))
                        witness = next(point for point in archive
                                       if all(point["upper"][i] <= lower[i] for i in range(4))
                                       and any(point["upper"][i] < lower[i] for i in range(4)))
                        record_decisions.append({"kind": "dominance", "partial": dict(nxt),
                                                 "lower": lower,
                                                 "archive_upper": witness["upper"]})
                    continue
            rec(depth + 1, nxt)

    rec(0, {})
    s.n_bound_calls = bd.calls
    tp = time.perf_counter()
    s.front = pareto_front(pts)
    s.t_pareto = time.perf_counter() - tp
    s.runtime = time.perf_counter() - t0
    return s


def random_search(space: DesignSpace, wl, budget: int, seed: int = 0) -> SearchStats:
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    if budget and not any(structurally_valid(x) for x in space.enumerate()):
        raise ValueError("no structurally valid designs")
    rng = random.Random(seed)
    t0 = time.perf_counter()
    s = SearchStats("random", n_raw=space.size)
    pts = []
    while s.n_evaluated < budget:
        x = {v: rng.choice(space.domain(v)) for v in VAR_ORDER}
        s.proposal_count += 1
        if not structurally_valid(x):
            s.structural_rejections += 1
            continue
        s.n_evaluated += 1
        r = evaluate(x, wl)
        if not r.feasible:
            s.feasibility_rejections += 1
        if r.feasible:
            s.n_feasible += 1
            pts.append((x, r.objectives))
    s.front = pareto_front(pts)
    s.runtime = time.perf_counter() - t0
    return s
