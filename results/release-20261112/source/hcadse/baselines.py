"""NSGA-II baseline (pymoo) over the same design space and evaluator."""
from __future__ import annotations
import numpy as np, time
from .model import DesignSpace, VAR_ORDER
from .evaluate import evaluate
from .search import structurally_valid, pareto_front, SearchStats


def nsga2(space: DesignSpace, wl, budget: int, seed: int = 0, pop: int = 40) -> SearchStats:
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.operators.sampling.rnd import IntegerRandomSampling
    from pymoo.operators.crossover.sbx import SBX
    from pymoo.operators.mutation.pm import PM
    from pymoo.core.repair import Repair


    if budget < 0:
        raise ValueError("budget must be nonnegative")
    if budget and not any(structurally_valid(x) for x in space.enumerate()):
        raise ValueError("no structurally valid designs")
    doms = [space.domain(v) for v in VAR_ORDER]
    s = SearchStats("nsga2", n_raw=space.size)
    pts = []

    class P(ElementwiseProblem):
        def __init__(self):
            super().__init__(n_var=len(VAR_ORDER), n_obj=4, n_constr=1,
                             xl=np.zeros(len(VAR_ORDER)),
                             xu=np.array([len(d) - 1 for d in doms]), vtype=int)

        def _evaluate(self, z, out, *a, **k):
            x = {v: doms[i][int(round(z[i]))] for i, v in enumerate(VAR_ORDER)}
            s.proposal_count += 1
            if not structurally_valid(x):
                s.structural_rejections += 1
                out["F"] = [1e9] * 4; out["G"] = [1.0]; return
            s.n_evaluated += 1
            r = evaluate(x, wl)
            if not r.feasible:
                s.feasibility_rejections += 1
            f = [v if np.isfinite(v) else 1e9 for v in r.objectives]
            out["F"] = f
            out["G"] = [0.0 if r.feasible else 1.0]
            if r.feasible:
                s.n_feasible += 1
                pts.append((x, r.objectives))

    class Round(Repair):
        def _do(self, problem, Z, **k):
            return np.rint(Z).astype(int)

    t0 = time.perf_counter()
    algo = NSGA2(pop_size=min(pop, max(1, budget)), sampling=IntegerRandomSampling(), repair=Round(),
                 crossover=SBX(prob=0.9, eta=15, vtype=float, repair=Round()),
                 mutation=PM(eta=20, vtype=float, repair=Round()),
                 eliminate_duplicates=True)
    problem = P()
    algo.setup(problem, termination=("n_gen", max(10000, budget * 100)), seed=seed, verbose=False)
    while s.n_evaluated < budget:
        remaining = budget - s.n_evaluated
        algo.n_offsprings = min(pop, remaining)
        candidates = algo.ask()
        if candidates is None or len(candidates) == 0:
            raise RuntimeError("NSGA-II exhausted proposals before the full-call budget")
        # A rejected proposal consumes no expensive call. The final batch cannot
        # exceed the remaining budget, even when every proposal is valid.
        candidates = candidates[:remaining]
        algo.evaluator.eval(problem, candidates)
        algo.tell(infills=candidates)
        if s.proposal_count > max(100000, budget * 10000):
            raise RuntimeError("NSGA-II could not spend the requested full-call budget")
    s.front = pareto_front(pts)
    s.runtime = time.perf_counter() - t0
    return s
