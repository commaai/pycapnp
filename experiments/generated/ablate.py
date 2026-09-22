"""Same binary and wrapper layout, toggling one optimization per fresh process."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("rlog")
parser.add_argument("--worker", action="store_true")
args = parser.parse_args()
if args.worker:
    from benchmark import bench, scan
    import generated_cython
    import generated_native
    from openpilot.tools.lib.logreader import LogReader

    events = list(LogReader(args.rlog))
    first = {m.which(): m for m in reversed(events)}
    n = min(1000, len(events))
    wire = [m.as_builder().to_bytes() for m in [events[i * len(events) // n] for i in range(n)] + list(first.values())]
    for mod in (generated_native, generated_cython):
        bench(mod.__name__ + " read", lambda: scan(map(mod.from_bytes, wire), True), len(wire), 5)
else:
    for name, flag in [
        ("optimized", None),
        ("heap handle", "GENERATED_HEAP_HANDLE"),
        ("copied input", "GENERATED_COPY_INPUT"),
        ("uncached union", "GENERATED_UNCACHED_UNION"),
        ("optimized confirm", None),
    ]:
        print(name, flush=True)
        env = dict(os.environ)
        for key in ("GENERATED_HEAP_HANDLE", "GENERATED_COPY_INPUT", "GENERATED_UNCACHED_UNION"):
            env.pop(key, None)
        if flag:
            env[flag] = "1"
        subprocess.run([sys.executable, str(Path(__file__).resolve()), args.rlog, "--worker"], env=env, check=True)
