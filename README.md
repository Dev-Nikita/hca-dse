# HCA-DSE

Research code and sealed results for HCA-DSE, an exact design-space exploration method
for heterogeneous edge–cloud cyber-physical architectures. The search prunes partial
designs with objective-specific admissible bounds (latency with contention and a
retry/load fixed point, energy, cost, network volume) and interval-safe comparisons,
and preserves the analytical Pareto front of the model.

## Layout

| Path | Content |
|---|---|
| `hcadse/` | model, evaluator, bounds, interval arithmetic, search |
| `experiments/` | experiment drivers (E1–E18) and the scripts that turn sealed results into tables and numbers |
| `tests/` | unit, pruning-safety and regression tests |
| `testbed/` | containerised edge/gateway/cloud testbed (Go services, Docker Compose specs) |
| `results/release-20261112/` | sealed release: `data/` (result files), `source/` (code that produced them), `logs/`, `manifest.json` (SHA-256 of every file) |

## Requirements

Python 3.10 with the packages pinned in `requirements-lock.txt`:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-lock.txt
```

## Verify the sealed release

```bash
make verify
```

This checks the SHA-256 of every sealed data and source file, re-checks exactness and
the persisted timing summaries, then runs every table/number generator in an empty
scratch directory against the sealed data only and compares each output with the
digests in `experiments/expected_outputs.json`. Any difference fails the check.

Regenerated tables and numbers can be written to `manuscript/` for inspection with
`make assets`.

## Tests

```bash
make test
```

## Re-running experiments

`make reproduce` re-executes the computational experiments into a new release
directory. Wall-clock timings and the containerised measurements are physical
observations: a re-run reproduces counts, fronts and derived quantities, not the
timings bit for bit. The decision-regret study (E18) needs no simulation:

```bash
python3 experiments/e18_decision_regret/e18_decision_regret.py \
    results/release-20261112/data/e14_des_endtoend/dumps/S3_*.json.gz \
    --selections results/release-20261112/data/h6/manifests --out /tmp/e18
```

See `testbed/README.md` for the containerised measurements.

## Status

This repository accompanies a manuscript under review. Please do not redistribute
before publication. A licence and an archived, version-specific DOI will be added on
publication.
