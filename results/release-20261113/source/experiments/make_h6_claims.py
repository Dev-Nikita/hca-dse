"""Generate the prospective H6 manuscript table and prose from sealed score files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CASES = (("S2", "sensing"), ("S3", "telemetry"),
         ("S3", "control"), ("S3", "sensing"))
EPSILONS = (0.0, 0.2)


def load_row(score_dir: Path, scale: str, workload: str, epsilon: float):
    path = score_dir / f"{scale}_{workload}.json"
    payload = json.loads(path.read_text())
    row = next(item for item in payload["rows"] if item["eps"] == epsilon)
    return row, path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", type=Path, default=Path("audit/results/h6/scores"))
    parser.add_argument("--table", type=Path,
                        default=Path("manuscript/tables/des_prospective.tex"))
    parser.add_argument("--prose", type=Path, default=Path("manuscript/generated/e14.tex"))
    parser.add_argument("--manifest", type=Path,
                        default=Path("audit/results/h6/manuscript_assets.json"))
    args = parser.parse_args()

    selected = {}
    sources = {}
    for scale, workload in CASES:
        for epsilon in EPSILONS:
            row, path = load_row(args.scores, scale, workload, epsilon)
            selected[(scale, workload, epsilon)] = row
            sources[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    lines = [
        r"\scriptsize",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"scale & workload & $\varepsilon$ & candidates & reduction & recall \\",
        r"\midrule",
    ]
    for scale, workload in CASES:
        for epsilon in EPSILONS:
            row = selected[(scale, workload, epsilon)]
            lines.append(f"{scale} & {workload:<9} & {epsilon:.2f} & "
                         f"{row['selected']:<4d} & {row['evaluation_reduction']:.1f}"
                         r"$\times$ & " + f"{row['recall']:.3f} " + r"\\")
    lines.extend((r"\bottomrule", r"\end{tabular}"))
    table = "\n".join(lines) + "\n"

    zero_rows = [selected[(*case, 0.0)] for case in CASES]
    s2 = selected[("S2", "sensing", 0.2)]
    telemetry = selected[("S3", "telemetry", 0.2)]
    control = selected[("S3", "control", 0.2)]
    sensing = selected[("S3", "sensing", 0.2)]
    cost_regret = 100 * control["objective_best_relative_regret"][2]
    prose = (
        r"\input{generated/refdefs}%" + "\n"
        r"\RefDesEndTab{} reports the sealed prospective check on the four retained per-design DES" + "\n"
        f"archives. With no margin, the analytical front selects "
        f"{min(r['selected'] for r in zero_rows)}--{max(r['selected'] for r in zero_rows)} candidates and recovers\n"
        f"{min(r['recall'] for r in zero_rows):.3f}--{max(r['recall'] for r in zero_rows):.3f} of the hybrid reference front. "
        f"At $\\varepsilon=0.20$, sensing reaches full\n"
        f"recall at {s2['selected']} candidates on S2 and {sensing['selected']} on S3, while telemetry remains complete. Control\n"
        f"reaches only {control['hits']} of {control['des_front']} reference points ({control['recall']:.3f}) at "
        f"{control['selected']} candidates because {control['missed_analytically_infeasible']} DES-front\n"
        f"architectures fail analytical feasibility and therefore cannot enter any objective-margin\n"
        f"candidate set. The best available cost is consequently {cost_regret:.2f}\\% worse than the held-out\n"
        "reference best in that case. The count reductions are empirical screening ratios, not\n"
        "wall-clock speed-ups or DES-level exactness guarantees.\n\n"
        "The S3 reference archives use one seed per design. The earlier five-seed near-front check\n"
        "is conditional rather than exhaustive. Moreover, the retained archives contain the\n"
        "DES-feasible universe rather than every structural design, so the experiment establishes\n"
        "leakage-free selection and held-out recall but does not independently regenerate the\n"
        "complete simulator run or its wall-clock time.\n"
    )

    args.table.parent.mkdir(parents=True, exist_ok=True)
    args.prose.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.table.write_text(table)
    args.prose.write_text(prose)
    manifest = {
        "schema": "h6-manuscript-assets-v1",
        "sources": sources,
        "outputs": {
            args.table.as_posix(): hashlib.sha256(table.encode()).hexdigest(),
            args.prose.as_posix(): hashlib.sha256(prose.encode()).hexdigest(),
        },
        "epsilons_rendered": list(EPSILONS),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

