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

Python 3.12 with the packages pinned in `requirements-lock.txt` (NumPy 2.5 and SciPy 1.18
do not install on Python 3.10 or 3.11):

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-lock.txt
pip install pytest    # only for `make test`
```

The pinned `z3-solver` has no prebuilt wheel for Linux/aarch64 and fails to build there;
Z3 is used only by the solver experiments (E11, E12, E16 and the encodings of E15), so on that platform install the other
pins (`grep -v z3-solver requirements-lock.txt > lock.txt`) and a current `z3-solver` if
those baselines are needed. `make verify` and `make test` need neither.

Environments of record: the audit run and the template-A studies were computed with
Python 3.12.3 on macOS/arm64 with the pinned packages; the template-B study (E19), which
uses only the standard library, and the sealing of `release-20261113` used Python 3.10.12
on Linux/aarch64 (the interpreter recorded in `manifest.json`). `make verify` and
`make test` pass in a clean Python 3.12 environment on Linux/aarch64 with the pinned
packages.

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
observations: a re-run reproduces fronts and derived quantities, not the timings bit
for bit. Evaluation counts of the template-A search can differ slightly across Python
versions: under Python 3.10 and 3.11 the fronts and counts are identical for the control
and sensing workloads and two to five full evaluations higher for telemetry, because
compensated summation in 3.12 changes some bounds in the last binary digit. The decision-regret study (E18) needs no simulation:

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

Version 0.2 (19 November 2026, DOI
[10.5281/zenodo.24378698](https://doi.org/10.5281/zenodo.24378698)) tightens the transfer-energy term of the bounds, which is now
exact once policy, replication and link class are assigned, adds a check that the bounds
dominate the assignment-monotone partial cost on every prefix of S1 and S2, and re-seals
all bound-dependent results as `release-20261113`. It also adds a second architecture
template with a fork-join stage graph and per-stage placement (`hcadse/template_b.py`,
`experiments/e19_template_b/`), whose pruning, feasibility, archive and front are decided
in exact rational arithmetic, with an independent reference implementation (`oracle.py`)
and a mutation analysis (`mutation.py`).

Version 0.2.1 corrects the installation notes (Python 3.12, Z3 on Linux/aarch64) and the
record of the environments, and refines the wording of one regenerated paragraph; code,
data and results are unchanged.

The accompanying manuscript has not yet been peer-reviewed. The verification procedure
regenerates the reported computational results from the retained data; the physical
measurements are included as recorded observations and are not re-executed.

No open-source licence has been granted at this time; all rights are reserved by the
author.
