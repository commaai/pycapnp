"""Fresh-process import + first CarState read/write; fixture prep excluded."""

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from openpilot.tools.lib.logreader import LogReader

parser = argparse.ArgumentParser()
parser.add_argument("rlog")
parser.add_argument("--repeat", type=int, default=9)
args = parser.parse_args()
event = next(m for m in LogReader(args.rlog) if m.which() == "carState")
with tempfile.TemporaryDirectory() as temp:
    fixture = Path(temp) / "event.bin"
    fixture.write_bytes(event.as_builder().to_bytes())
    snippets = {
        "dynamic": 'from openpilot.cereal import log\nr=log.Event.from_bytes(w).__enter__()\nv=r.carState.vEgo\nb=log.Event.new_message();b.init("carState").vEgo=v;out=b.to_bytes()',
        "generated_cython": 'import generated_cython as m\nv=m.from_bytes(w).carState.vEgo\nb=m.new();b.init("carState").vEgo=v;out=b.to_bytes()',
        "generated_native": 'import generated_native as m\nv=m.from_bytes(w).carState.vEgo\nb=m.new();b.init("carState").vEgo=v;out=b.to_bytes()',
    }
    results = {name: [] for name in snippets}
    for rep in range(args.repeat):
        order = list(snippets) if rep % 2 == 0 else list(reversed(snippets))
        for name in order:
            code = (
                f"from pathlib import Path\nw=Path({str(fixture)!r}).read_bytes()\n"
                + snippets[name]
                + "\nassert len(out)>0\n"
            )
            start = time.perf_counter()
            subprocess.run([sys.executable, "-c", code], check=True, stdout=subprocess.DEVNULL)
            results[name].append((time.perf_counter() - start) * 1000)
    print(
        json.dumps(
            {
                name: {"median_ms": statistics.median(v), "min_ms": min(v), "max_ms": max(v), "samples_ms": v}
                for name, v in results.items()
            },
            indent=2,
        )
    )
