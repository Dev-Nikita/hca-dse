"""Actual-call budgets, alternative-order bounds and simulator semantics."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from dataclasses import replace
from hcadse.model import make_space, WORKLOADS, VAR_ORDER
from hcadse.search import random_search, hca_dse, exhaustive, structurally_valid
from hcadse.baselines import nsga2
from hcadse.evaluate import evaluate
from hcadse.metrics import objset
from hcadse.bounder import Bounder
from hcadse.simulate import simulate
O2 = ['n_e','edge_cls','n_g','gw_cls','rep','policy','link_cls','cloud_cls']


def budgets():
    space = make_space('S2'); wl = WORKLOADS['control']
    for func, module in [(random_search, 'hcadse.search'), (nsga2, 'hcadse.baselines')]:
        for budget in [0, 1, 39, 41, 100, 250]:
            with patch(module + '.evaluate', wraps=evaluate) as spy:
                s = func(space, wl, budget, seed=1)
                assert spy.call_count == s.n_evaluated == budget
                assert s.proposal_count == s.structural_rejections + budget
                assert s.n_feasible + s.feasibility_rejections == budget
                assert all(structurally_valid(call.args[0]) for call in spy.call_args_list)
    print('instrumented evaluator-call budgets: PASS')


def orders():
    sp = make_space('S1')
    for wl in WORKLOADS.values():
        ref = objset(exhaustive(sp, wl).front)
        for order in [VAR_ORDER, O2]:
            for queue in [False, True]:
                bd = Bounder(sp, wl, use_queue_bound=queue)
                for x in sp.enumerate():
                    f = evaluate(x, wl).objectives
                    for depth in range(9):
                        p = {v: x[v] for v in order[:depth]}
                        lb = bd.bounds(p)
                        assert all(lb[k] <= val + 1e-9 for k,val in zip(['L','E','C','D'], f))
                s = hca_dse(sp, wl, variable_order=order, use_queue_bound=queue)
                assert objset(s.front) == ref
    print('O1/O2 with/without queue: bounds and exactness PASS')


def queue_instrumentation_is_observational():
    sp = make_space('S1')
    for wl in WORKLOADS.values():
        plain = hca_dse(sp, wl, use_queue_bound=True)
        measured = hca_dse(sp, wl, use_queue_bound=True, measure_queue=True)
        assert (measured.n_nodes, measured.n_evaluated) == (plain.n_nodes, plain.n_evaluated)
        assert objset(measured.front) == objset(plain.front)
    print('queue instrumentation leaves search decisions unchanged: PASS')


def simulation():
    sp = make_space('S1'); x = next(sp.enumerate()); x['rep'] = 2
    # With one request and two edge servers, replicated ingest is parallel.
    wl = replace(WORKLOADS['telemetry'], rate=0.000001)
    result = simulate(x, wl, n_req=1, warmup=0, seed=3)
    from hcadse.model import POLICIES, WAN_B, WAN_PROP
    from hcadse.evaluate import hops
    t1,t3=POLICIES[x['policy']]; cs={'edge':x['edge_cls'].C,'gw':x['gw_cls'].C,'cloud':x['cloud_cls'].C}
    expected=sum(s.w/cs[t] for s,t in zip(wl.stages,[t1,'gw',t3]))
    expected+=sum(8*p/(x['link_cls'].B if k=='access' else WAN_B)+(x['link_cls'].prop if k=='access' else WAN_PROP) for p,k in hops(x,wl))
    assert abs(result['mean']-expected)<1e-8,(result,expected)
    assert simulate(x,wl,n_req=5,warmup=1,seed=2)==simulate(x,wl,n_req=5,warmup=1,seed=2)
    print('DES single-request fork/join latency and seed repeatability: PASS')

if __name__ == '__main__':
    budgets(); orders(); queue_instrumentation_is_observational(); simulation()
