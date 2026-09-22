"""Cold subprocess schema loading and optional application reflection cache."""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import capnp

parser = argparse.ArgumentParser()
parser.add_argument('--child', choices=['source', 'compiled', 'lazy', 'create'])
parser.add_argument('--archive', default='/tmp/openpilot-schema-archive')
parser.add_argument('--repeat', type=int, default=11)
args = parser.parse_args()
archive = Path(args.archive)
source = Path('/home/batman/openpilot/openpilot/cereal/log.capnp')
imports = ['/home/batman/openpilot/opendbc_repo/opendbc/car']
if args.child:
    start = time.perf_counter()
    if args.child in ('source', 'create'):
        module = capnp.load(str(source), imports=imports)
        if args.child == 'create':
            archive.write_bytes(module._parser.export_schemas())
            archive.with_suffix('.id').write_text(str(module.schema.node.id))
    else:
        module = capnp.load_compiled(archive.read_bytes(), int(archive.with_suffix('.id').read_text()), lazy=args.child == 'lazy')
    message = module.Event.new_message(carState={'vEgo': 12.5})
    assert message.carState.vEgo == 12.5
    print((time.perf_counter() - start) * 1000)
    sys.exit()

module = capnp.load(str(source), imports=imports)
archive.write_bytes(module._parser.export_schemas())
archive.with_suffix('.id').write_text(str(module.schema.node.id))
print('archive_bytes', archive.stat().st_size)
for mode in ('source', 'compiled', 'lazy', 'create'):
    total, load = [], []
    for _ in range(args.repeat):
        start = time.perf_counter()
        output = subprocess.check_output([sys.executable, __file__, '--child', mode, '--archive', str(archive)], env=os.environ)
        total.append((time.perf_counter() - start) * 1000)
        load.append(float(output))
    print(mode, 'load_ms', statistics.median(load), 'process_ms', statistics.median(total), 'load_range', min(load), max(load))

from openpilot.system.webrtc.schema import generate_struct
schema = module.Event.schema.fields['carState'].schema
from benchmarks.bench_openpilot import bench
from copy import deepcopy
cached = generate_struct(schema)
encoded = json.dumps(cached)
bench('reflection uncached', lambda: generate_struct(module.Event.schema.fields['carState'].schema), 1, 5)
bench('reflection deepcopy', lambda: deepcopy(cached), 1, 5)
bench('reflection JSON copy', lambda: json.loads(encoded), 1, 5)
bench('reflection shared', lambda: cached, 1, 5)
assert json.loads(encoded) == generate_struct(schema)

from experiments.allocation.reflection import ReflectionCache
cache = ReflectionCache()
assert cache.generate_struct(module.Event.schema.fields['carState']) == cached
bench('reflection cached API', lambda: cache.generate_struct(module.Event.schema.fields['carState']), 1, 5)
bench('reflection JSON API', lambda: cache.encoded(module.Event.schema.fields['carState']), 1, 5)
