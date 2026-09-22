"""Render per-workload medians, ratios, sizes, and profile coverage evidence."""

import hashlib
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parent
results = root / "results"
pattern = re.compile(r"^(.+?)\s+([0-9.]+) us/item", re.M)
measurements = {
    f.name.removesuffix(".bench.txt"): dict((k.strip(), float(v)) for k, v in pattern.findall(f.read_text()))
    for f in results.glob("*.bench.txt")
    if "-training" not in f.name
}
variants = [
    v
    for v in (
        "baseline",
        "o2",
        "native",
        "lto",
        "pgo",
        "pgo-lto",
        "pgo-lto-native",
        "pgo-lto-hidden",
        "clang",
        "clang-thinlto",
        "clang-pgo-thinlto",
        "clang-pgo-thinlto-native-hidden",
    )
    if v in measurements
]
lines = [
    "# Measured compiler variants",
    "",
    "Exploratory sequential runs under concurrent host load; these are NOT controlled speedup comparisons.",
    "Median microseconds per benchmark item; lower is better. Use the final paired results for conclusions.",
    "",
    "| Workload | " + " | ".join(variants) + " |",
    "|---|" + "---:|" * len(variants),
]
for name in measurements["baseline"]:
    lines.append("| " + name + " | " + " | ".join(f"{measurements[v][name]:.2f}" for v in variants) + " |")
lines += ["", "## Binary evidence", "", "| Variant | Bytes (unstripped) | SHA256 |", "|---|---:|---|"]
for variant in variants:
    binary = results / (variant + ".so")
    lines.append(f"| {variant} | {binary.stat().st_size} | {hashlib.sha256(binary.read_bytes()).hexdigest()} |")
    (results / (variant + ".size.txt")).write_text(subprocess.check_output(["size", str(binary)], text=True))
(root / "measurements.md").write_text("\n".join(lines) + "\n")
