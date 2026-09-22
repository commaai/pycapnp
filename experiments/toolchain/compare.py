"""Fresh-process ABBA comparisons using saved, independently built extensions."""

import argparse
import hashlib
import json
import re
from statistics import median
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--python", required=True)
p.add_argument("--openpilot", required=True)
p.add_argument("--log", required=True)
p.add_argument("--candidate", required=True)
p.add_argument("--cpu", default="17")
p.add_argument("--label", required=True)
p.add_argument("--repeat", type=int, default=5)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
results = root / "experiments/toolchain/results"
binary = next((root / "capnp/lib").glob("*.so"))
env = dict(os.environ, PYTHONPATH=f"{root}:{a.openpilot}")
identities = {
    variant: hashlib.sha256((results / (variant + ".so")).read_bytes()).hexdigest()
    for variant in ("baseline", a.candidate)
}
(results / (a.label + ".metadata.json")).write_text(
    json.dumps(
        {
            "arguments": vars(a),
            "binaries": identities,
            "log_sha256": hashlib.sha256(Path(a.log).read_bytes()).hexdigest(),
        },
        indent=2,
    )
    + "\n"
)
original = binary.read_bytes()
try:
    for index, variant in enumerate(["baseline", a.candidate, a.candidate, "baseline"]):
        shutil.copy2(results / (variant + ".so"), binary)
        with (results / f"{a.label}-{index}-{variant}.bench.txt").open("w") as output:
            subprocess.run(
                ["taskset", "-c", a.cpu, a.python, "benchmarks/bench_openpilot.py", a.log, "--repeat", str(a.repeat)],
                cwd=root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=True,
            )
finally:
    binary.write_bytes(original)

pattern = re.compile(r"^(.+?)\s+([0-9.]+) us/item", re.M)
measurements = []
for index, variant in enumerate(["baseline", a.candidate, a.candidate, "baseline"]):
    measurements.append(
        {
            k.strip(): float(v)
            for k, v in pattern.findall((results / f"{a.label}-{index}-{variant}.bench.txt").read_text())
        }
    )
lines = [
    f"# {a.label}: baseline versus {a.candidate}",
    "",
    "ABBA fresh-process comparison; speedup >1 favors candidate.",
    "",
    "| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |",
    "|---|---:|---:|---:|---:|",
]
for name in measurements[0]:
    aa = [measurements[0][name], measurements[3][name]]
    bb = [measurements[1][name], measurements[2][name]]
    ratios = [x / y for x, y in zip(aa, bb)]
    lines.append(
        f"| {name} | {aa[0]:.2f}/{aa[1]:.2f} | {bb[0]:.2f}/{bb[1]:.2f} | "
        f"{ratios[0]:.3f}/{ratios[1]:.3f} | {median(ratios):.3f} |"
    )
(root / "experiments/toolchain" / (a.label + ".md")).write_text("\n".join(lines) + "\n")
