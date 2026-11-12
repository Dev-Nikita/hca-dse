"""Regression lock: any change to bounds must keep exactness and cached==reference."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcadse.model import make_space, WORKLOADS, VAR_ORDER
from hcadse.bounds import lower_bounds
from hcadse.bounder import Bounder
from hcadse.search import exhaustive, hca_dse
from hcadse.metrics import objset


def test_cached_bounds_match_reference():
    sp = make_space("S2"); rng = random.Random(0)
    for wl in WORKLOADS.values():
        b = Bounder(sp, wl)
        xs = list(sp.enumerate()); rng.shuffle(xs)
        for x in xs[:150]:
            for d in range(len(VAR_ORDER) + 1):
                p = {v: x[v] for v in VAR_ORDER[:d]}
                a, c = lower_bounds(p, sp, wl), b.bounds(p)
                for k in "LECD":
                    if a[k] == float("inf") and c[k] == float("inf"):
                        continue
                    assert abs(a[k] - c[k]) <= 1e-9 * max(1.0, abs(a[k])), (k, d, a[k], c[k])
    print("cached bounds == reference bounds: OK")


def test_exactness_all_variants():
    for scale in ("S1", "S2", "S3"):
        sp = make_space(scale)
        for wl in WORKLOADS.values():
            ref = objset(exhaustive(sp, wl).front)
            for kw in (dict(use_bounds=True, use_dominance=True),
                       dict(use_bounds=True, use_dominance=False),
                       dict(use_bounds=False, use_dominance=True)):
                got = objset(hca_dse(sp, wl, **kw).front)
                assert got == ref, (scale, wl.name, kw)
        print(f"{scale}: P_HCA == P_exhaustive for all workloads and pruning variants")


if __name__ == "__main__":
    test_cached_bounds_match_reference()
    test_exactness_all_variants()
