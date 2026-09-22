"""Measure complete Python process startup with cold JIT, cached JIT, and AOT load."""

from pathlib import Path
import argparse
import shlex
import subprocess
import sys
import tempfile
from run import ROOT, compile_kernel

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=ROOT / "startup.json")
parser.add_argument("--runs", type=int, default=10)
args = parser.parse_args()
with tempfile.TemporaryDirectory() as directory:
    cache = Path(directory)
    _, library, _, _ = compile_kernel(cache)
    common = [sys.executable, str(ROOT / "compile_process.py")]
    subprocess.run(
        [
            "hyperfine",
            "--warmup",
            "2",
            "--runs",
            str(args.runs),
            "--export-json",
            str(args.output),
            "--command-name",
            "cold runtime compile",
            shlex.join(common),
            "--command-name",
            "cached runtime compile",
            shlex.join(common + ["--cache", str(cache)]),
            "--command-name",
            "prebuilt extension load",
            shlex.join(common + ["--load", str(library)]),
        ],
        check=True,
    )
