"""Check the sealed release and regenerate every numerical statement from it.

The sealed data and source files are checked against their SHA-256 manifest. Every
generator then runs in an empty scratch directory that sees only the sealed release,
and each table and numerical paragraph it writes is compared byte for byte with the
copy used to typeset the paper. When those copies are not present (for example in the
code-only repository), the comparison uses the digests in expected_outputs.json.
`--record` rewrites that file from the paper copies.
"""
from pathlib import Path
import hashlib, json, os, subprocess, sys, tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
EXPECTED = HERE / "expected_outputs.json"
GENERATORS = ("e14_des_endtoend/make_e14_claims.py", "e15_feedback/make_e15_claims.py",
              "e17_generic_bb/make_e17_claims.py", "e18_decision_regret/make_e18_claims.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


release = Path(os.environ.get("HCADSE_RESULTS", "results/release-20261112/data")).resolve().parent
manifest = json.loads((release / "manifest.json").read_text())
for name, digest in manifest["data_sha256"].items():
    assert sha(release / "data" / name) == digest, "sealed data changed: " + name
for name, digest in manifest["source_sha256"].items():
    assert sha(release / "source" / name) == digest, "sealed source changed: " + name

with tempfile.TemporaryDirectory() as scratch:
    root = Path(scratch)
    for sub in ("generated", "tables", "figures"):
        (root / "manuscript" / sub).mkdir(parents=True)
    (root / "results").mkdir()
    for item in sorted((release / "data").iterdir()):
        if item.is_dir():
            (root / "results" / item.name).symlink_to(item)
    (root / "results" / release.name).symlink_to(release)
    env = dict(os.environ, HCADSE_RESULTS=str(release / "data"))
    quiet = dict(cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(HERE / "make_paper_assets.py")], **quiet)
    subprocess.run([sys.executable, str(HERE / "make_claims.py")], **quiet)
    for generator in GENERATORS:
        subprocess.run([sys.executable, str(HERE / generator), str(root)], **quiet)
    # the prospective screening table and its prose replace the E14 paragraph
    subprocess.run([sys.executable, str(HERE / "make_h6_claims.py"),
                    "--scores", str(root / "results" / "h6" / "scores"),
                    "--table", str(root / "manuscript" / "tables" / "des_prospective.tex"),
                    "--prose", str(root / "manuscript" / "generated" / "e14.tex"),
                    "--manifest", str(root / "h6_assets.json")], **quiet)
    produced = {p.relative_to(root).as_posix(): sha(p)
                for p in sorted((root / "manuscript").rglob("*.tex"))}

local = {k: sha(REPO / k) for k in produced if (REPO / k).is_file()}
if "--record" in sys.argv:
    assert set(local) == set(produced), "paper copies missing: %s" % sorted(set(produced) - set(local))
    EXPECTED.write_text(json.dumps(produced, indent=1, sort_keys=True) + "\n")
reference = local if local else json.loads(EXPECTED.read_text())
differ = sorted(k for k in produced if reference.get(k) != produced[k])
assert not differ, "regenerated output differs from the paper: %s" % differ
print("Sealed hashes and %d regenerated tables/paragraphs (%s): PASS"
      % (len(produced), "paper copies" if local else "recorded digests"))
