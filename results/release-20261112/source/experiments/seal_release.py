"""Seal a result release: data, source, logs and a hash manifest.

The computational experiments are sealed by `reproduce.py` into an audit release;
the deployment measurements (e9_*) and the simulator and solver studies that run
separately (e13-e17) are added here, so that one directory regenerates every
number of the manuscript and `verify_manuscript_numbers.py` can check it.

    python3 experiments/seal_release.py --audit results/audit-h7b-20261026 \
        --name release-YYYYMMDD
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

EXTRA_DATA = ("e9_per_design_docker.csv", "e9_per_design_local.csv",
              "e9_per_design_mean.csv", "e9_summary_docker.csv",
              "e9_summary_local.csv", "e9_summary_mean.csv", "e9_testbed.csv",
              "e9_testbed_local.csv", "e9_testbed_local_mm1.csv",
              "e9_testbed_local_sharedlink.csv", "e9_testbed_round2.csv",
              "e13_reliability.csv")
EXTRA_TREES = ("e14_des_endtoend", "e15_feedback", "e16_lazy_oracle",
               "e17_generic_bb", "e18_decision_regret")
SOURCE_TREES = ("hcadse", "experiments", "testbed", "tests")
SOURCE_FILES = ("Makefile", "requirements-lock.txt")
# Paths listed in release-exclude.txt (one per line) are local tooling that no
# result depends on; they are left out of the sealed source.
EXCLUDE_FILE = Path("release-exclude.txt")
SOURCE_EXCLUDE = tuple(line.strip() for line in
                       (EXCLUDE_FILE.read_text().splitlines() if EXCLUDE_FILE.exists() else [])
                       if line.strip() and not line.startswith("#"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_tree(src: Path, dst: Path) -> None:
    for item in sorted(src.rglob("*")):
        if item.is_dir() or "__pycache__" in item.parts:
            continue
        target = dst / item.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True, help="sealed computational audit release")
    ap.add_argument("--name", required=True)
    ap.add_argument("--results", default="results")
    a = ap.parse_args()

    results = Path(a.results)
    audit = Path(a.audit)
    out = results / a.name
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)

    for item in sorted((audit / "data").iterdir()):
        shutil.copy2(item, out / "data" / item.name)
    for name in EXTRA_DATA:
        source = results / name
        if source.exists():
            shutil.copy2(source, out / "data" / name)
        else:
            print("missing, not sealed:", name, file=sys.stderr)
    for tree in EXTRA_TREES:
        if (results / tree).is_dir():
            copy_tree(results / tree, out / "data" / tree)
    for sub in ("scores", "manifests"):
        if (Path("audit/results/h6") / sub).is_dir():
            copy_tree(Path("audit/results/h6") / sub, out / "data" / "h6" / sub)
    if (audit / "logs").is_dir():
        copy_tree(audit / "logs", out / "logs")

    for tree in SOURCE_TREES:
        if Path(tree).is_dir():
            copy_tree(Path(tree), out / "source" / tree)
    for name in SOURCE_EXCLUDE:
        target = out / "source" / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for name in SOURCE_FILES:
        if Path(name).exists():
            shutil.copy2(Path(name), out / "source" / name)

    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    previous = {}
    if (audit / "manifest.json").exists():
        previous = json.loads((audit / "manifest.json").read_text())
    manifest = {
        "release": a.name,
        "sealed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "derived_from_audit": previous.get("release", str(audit)),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "git_head": head,
        "data_sha256": {str(p.relative_to(out / "data")): sha(p)
                        for p in sorted((out / "data").rglob("*")) if p.is_file()},
        "source_sha256": {str(p.relative_to(out / "source")): sha(p)
                          for p in sorted((out / "source").rglob("*")) if p.is_file()},
        "packages": previous.get("packages"),
        "testbed_provenance": previous.get("testbed_provenance"),
        "timing_policy": previous.get("timing_policy"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("sealed %s: %d data files, %d source files"
          % (out, len(manifest["data_sha256"]), len(manifest["source_sha256"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
