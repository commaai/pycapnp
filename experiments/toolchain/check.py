"""Check every saved binary, including optional openpilot integration tests."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--python", required=True)
p.add_argument("--openpilot", required=True)
p.add_argument("--cpu", default="17")
p.add_argument("--pytest-site", help="Optional site-packages directory providing pytest to benchmark Python")
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
results = root / "experiments/toolchain/results"
binary = next((root / "capnp/lib").glob("*.so"))
env = dict(os.environ, PYTHONPATH=f"{root}:{a.openpilot}", OPENPILOT_PATH=a.openpilot)
original = binary.read_bytes()
try:
    for variant in sorted(results.glob("*.so")):
        if "rejected" in variant.name:
            continue
        shutil.copy2(variant, binary)
        with variant.with_suffix(".integration.txt").open("w") as output:
            invocation = ["-m", "pytest"]
            if a.pytest_site:
                invocation = [
                    "-c",
                    "import site,sys; site.addsitedir(sys.argv.pop(1)); import pytest; raise SystemExit(pytest.main(sys.argv[1:]))",
                    a.pytest_site,
                ]
            subprocess.run(
                ["taskset", "-c", a.cpu, a.python, *invocation, "-q", "test"],
                cwd=root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=True,
            )
finally:
    binary.write_bytes(original)
