"""Regression test for the controlled bound comparison on S1.

Re-runs the five bound configurations on the smallest scale and checks the
evaluation counts, the expanded-state counts and front equality against the
sealed matrix, so a change in the bounds, the search or the certification
protocol cannot silently move the numbers the manuscript reports.
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "e17_generic_bb"))

from bounders import CachedPartialCostBounder, PositiveQueueBounder  # noqa: E402

from hcadse import search as search_mod  # noqa: E402
from hcadse.bounder import Bounder  # noqa: E402
from hcadse.metrics import objset  # noqa: E402
from hcadse.model import WORKLOADS, make_space  # noqa: E402
from hcadse.search import exhaustive, hca_dse  # noqa: E402

CONFIGS = {
    "G1c": (CachedPartialCostBounder, {}),
    "G2m": (Bounder, dict(use_queue_bound=False)),
    "G2": (Bounder, {}),
    "G3": (PositiveQueueBounder, {}),
}


def sealed(scale="S1"):
    # the sealed release when HCADSE_RESULTS points at one, the working tree otherwise
    base = Path(os.environ.get("HCADSE_RESULTS", ROOT / "results"))
    path = base / "e17_generic_bb" / "bb_matrix.csv"
    if not path.exists():
        path = ROOT / "results" / "e17_generic_bb" / "bb_matrix.csv"
    rows = [r for r in csv.DictReader(path.open()) if r["scale"] == scale]
    out = {}
    for r in rows:
        out[(r["workload"], r["config"])] = (int(r["evals"]), int(r["nodes"]))
    return out


def test_s1_matrix():
    expected = sealed()
    for workload, wl in WORKLOADS.items():
        space = make_space("S1")
        reference = objset(exhaustive(space, wl).front)
        for name, (bounder, kwargs) in CONFIGS.items():
            original = search_mod.Bounder
            search_mod.Bounder = bounder
            try:
                stats = hca_dse(space, wl, **kwargs)
            finally:
                search_mod.Bounder = original
            assert objset(stats.front) == reference, (workload, name, "front")
            assert (stats.n_evaluated, stats.n_nodes) == expected[(workload, name)], (
                workload, name, stats.n_evaluated, stats.n_nodes,
                expected[(workload, name)])
        # the retraction, as a test: the generic bound is not beaten on calls
        assert expected[(workload, "G1c")][0] <= expected[(workload, "G2")][0]


if __name__ == "__main__":
    test_s1_matrix()
    print("S1 bound matrix reproduced, including the generic parity on calls")
