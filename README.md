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
| `experiments/` | experiment drivers (E1–E19) and the scripts that turn sealed results into tables and numbers |
| `tests/` | unit, pruning-safety and regression tests |
| `testbed/` | containerised edge/gateway/cloud testbed (Go services, Docker Compose specs) |
| `results/release-20261113/` | sealed release: `data/` (result files), `source/` (code that produced them), `logs/`, `manifest.json` (SHA-256 of every file) |

## Requirements

Python 3.10 with the packages pinned in `requirements-lock.txt`:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-lock.txt
pip install pytest    # only for `make test`
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
    results/release-20261113/data/e14_des_endtoend/dumps/S3_*.json.gz \
    --selections results/release-20261113/data/h6/manifests --out /tmp/e18
```

See `testbed/README.md` for the containerised measurements.

## Status and citation

Each tagged version is archived at Zenodo with its own DOI; the Zenodo record lists all
versions. Version 0.1 (12 November 2026): DOI
[10.5281/zenodo.24171466](https://doi.org/10.5281/zenodo.24171466).

Version 0.2 (November 2026) tightens the transfer-energy term of the bounds, which is now
exact once policy, replication and link class are assigned, adds a check that the bounds
dominate the assignment-monotone partial cost on every prefix of S1 and S2, and re-seals
all bound-dependent results as `release-20261113`. It also adds a second architecture
template with a fork-join stage graph and per-stage placement (`hcadse/template_b.py`,
`experiments/e19_template_b/`), whose pruning, feasibility, archive and front are decided
in exact rational arithmetic, with an independent reference implementation (`oracle.py`)
and a mutation analysis (`mutation.py`).

The accompanying manuscript has not yet been peer-reviewed. The verification procedure
regenerates the reported computational results from the retained data; the physical
measurements are included as recorded observations and are not re-executed.

No open-source licence has been granted at this time; all rights are reserved by the
author.
