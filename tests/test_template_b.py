"""Template B: exact front and bound ordering on scale B1."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hcadse import template_b as tb


def test_front_and_evaluations():
    for wl in tb.WORKLOADS.values():
        oracle = tb.exhaustive("B1", wl, exact=True)
        ours = tb.search("B1", wl)
        generic = tb.search("B1", wl, relax=False)
        assert ours.front == oracle.front == generic.front
        assert ours.evals <= generic.evals
        assert ours.nodes <= generic.nodes


if __name__ == "__main__":
    test_front_and_evaluations()
    print("template B: exact front, no more evaluations than the partial cost: PASS")
