"""Run the unchanged workload using archives for every imported source schema.

The prepare phase is untimed and explicit. Artifacts must be regenerated after
schema changes; this harness is not a transparent production disk-cache policy.
"""
import json
import runpy
import sys
from pathlib import Path

import capnp

root = Path('/tmp/openpilot-compiled-workload')
if sys.argv[1] == 'prepare':
    from openpilot.cereal import log, custom
    from opendbc.car.structs import car
    root.mkdir(exist_ok=True)
    metadata = {}
    for module in (log, custom, car):
        path = Path(module.__file__).resolve()
        archive = root / (path.name + '.bin')
        archive.write_bytes(module._parser.export_schemas())
        metadata[str(path)] = [str(archive), module.schema.node.id]
    (root / 'index.json').write_text(json.dumps(metadata))
    sys.exit()

mode = sys.argv.pop(1)
assert mode in ('eager', 'lazy')
metadata = json.loads((root / 'index.json').read_text())

def load(path, display_name=None, imports=None):
    key = str(Path(path).resolve())
    if key not in metadata:
        raise ValueError(f'Unprepared schema: {key}')
    archive, schema_id = metadata[key]
    module = capnp.load_compiled(Path(archive).read_bytes(), schema_id, display_name or Path(path).name, lazy=mode == 'lazy')
    module.__file__ = key
    module.__path__ = [str(Path(key).parent)]
    return module

capnp.load = load
runpy.run_path(str(Path(__file__).resolve().parents[2] / 'benchmarks/bench_openpilot.py'), run_name='__main__')
