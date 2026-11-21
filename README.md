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
| `experiments/` | experiment drivers (E1–E22) and the scripts that turn sealed results into tables and numbers |
| `tests/` | unit, pruning-safety and regression tests |
| `testbed/` | containerised edge/gateway/cloud testbed (Go services, Docker Compose specs) |
| `results/release-20261113/` | sealed release: `data/` (result files), `source/` (code that produced them), `logs/`, `manifest.json` (SHA-256 of every file) |

The `git_head` field of `manifest.json` records the commit of the author's working
repository at sealing time; it is not a commit of this repository. The SHA-256 entries
identify every sealed file.

## Requirements

Python 3.12 (NumPy 2.5 and SciPy 1.18 do not install on Python 3.10 or 3.11).
`make verify` and `make test` need every pinned package except `z3-solver`:

```bash
python3.12 -m venv .venv && . .venv/bin/activate
grep -v '^z3-solver' requirements-lock.txt > requirements-verify.txt
pip install -r requirements-verify.txt
pip install pytest    # only for `make test`
```

Z3 is needed only to re-run the solver experiments (E11, E12, E16 and the solver
encodings of E15). The full pinned set, including `z3-solver`, installs on macOS/arm64,
the environment of record:

```bash
pip install -r requirements-lock.txt
```

On Linux/aarch64 no `z3-solver` wheel was available in our test (both the pinned and the
current release tried to build from source and failed), so the solver experiments should
be re-run on macOS/arm64.

Environments of record: the audit run and the template-A studies were computed with
Python 3.12.3 on macOS/arm64 with the pinned packages; the template-B study (E19), which
uses only the standard library, and the sealing of `release-20261113` used Python 3.10.12
on Linux/aarch64 (the interpreter recorded in `manifest.json`). `make verify` and
`make test` pass in a clean Python 3.12 environment on Linux/aarch64 with every pinned
package except `z3-solver`.

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

Version 0.2.1 (20 November 2026, DOI
[10.5281/zenodo.24394702](https://doi.org/10.5281/zenodo.24394702)): numerical experiment data and search algorithms are unchanged. It corrects
the installation instructions (Python 3.12, Z3 on Linux/aarch64) and the record of the
environments, and changes the wording of one generated paragraph (E19); the generator,
its recorded output digests and the release manifest are updated accordingly.

Version 0.2.2 (21 November 2026, DOI
[10.5281/zenodo.24425265](https://doi.org/10.5281/zenodo.24425265)) adds comparisons with the generic partial-cost bound, each with a protocol
fixed before the runs: constraint regimes for the closed-form model
(`experiments/e20_regimes/`), the retry model with the generic bound unlifted and lifted
through the certified fixed point (`experiments/e21_retry_bb/`), and six retry-model
variants (`experiments/e22_retry_sensitivity/`). `hcadse/intervals.py` now reads the
retry parameters from `hcadse/feedback.py`, so that a model variant changes the evaluator
and every bound together; at the published parameters its results are unchanged. Earlier
data and results are unchanged.

Version 0.2.3 (21 November 2026, DOI
[10.5281/zenodo.24426261](https://doi.org/10.5281/zenodo.24426261)) re-times the lifted generic bound of E21 (median of three runs, with the
rate-independent part of the bound computed once per prefix, as in the proposed bound; the
bound itself is unchanged, bit for bit) and corrects the wording of two generated
sentences. Evaluation and state counts are unchanged.

The accompanying manuscript has not yet been peer-reviewed. The verification procedure
regenerates the reported computational results from the retained data; the physical
measurements are included as recorded observations and are not re-executed.

## Licence

Copyright 2026 Nikita Tarasov. Licensed under the Apache License, Version 2.0 (see
`LICENSE` and `NOTICE`) from version 0.2.1 on. Versions 0.1 and 0.2 were archived at
Zenodo under CC BY 4.0. If you use this code, please cite the Zenodo record of the version
you used.
