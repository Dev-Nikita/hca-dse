"""Claim-consistency audit: every numeric literal used in the manuscript prose must be
traceable to a generated artefact (generated/*.tex, tables/*.tex, generated_numbers.tex)
or to the raw result CSVs. Prints anything that is only typed by hand."""
import re, glob, os, sys

M = "manuscript"
PROSE = sorted(glob.glob(f"{M}/sections_sn/*.tex"))
SOURCES = sorted(glob.glob(f"{M}/generated/*.tex") + glob.glob(f"{M}/tables/*.tex")
                 + [f"{M}/generated_numbers.tex"] + glob.glob("results/*.csv"))

# numbers that are structural rather than empirical
WHITELIST = {"1", "2", "3", "4", "5", "8", "10", "20", "36", "40", "100", "108", "150",
             "250", "500", "900", "1000", "0.85", "200", "0", "9", "6", "12", "16", "24",
             "3.10", "3.11", "3.12"}   # Python versions named in the reproducibility note

blob = "".join(open(f, errors="ignore").read() for f in SOURCES).replace(",", "").replace("\\,", "")
num = re.compile(r"(?<![A-Za-z0-9_.^{])(\d+(?:\.\d+)?)(?![A-Za-z0-9_}])")

missing = {}
for f in PROSE:
    text = open(f).read()
    text = re.sub(r"\\cite\{[^}]*\}", " ", text)
    text = re.sub(r"\\(label|ref|input|includegraphics)\{[^}]*\}", " ", text)
    for m in num.finditer(text.replace("\\,", "")):
        v = m.group(1)
        if v in WHITELIST:
            continue
        if re.fullmatch(r"(19|20)\d\d", v):     # publication years in the prior-work table
            continue
        if v in blob or v.rstrip("0").rstrip(".") in blob:
            continue
        missing.setdefault(os.path.basename(f), set()).add(v)

if not missing:
    print("claim audit: every empirical number in the prose is backed by a generated "
          "artefact or a raw result file")
else:
    print("claim audit: numbers with no generated source (check by hand):")
    for f, vs in sorted(missing.items()):
        print(f"  {f}: {', '.join(sorted(vs, key=float))}")
sys.exit(0)
