"""Compare the same real message records across allocator policies."""
import argparse
import gc
import hashlib
import json
import sys
import struct
import random
import time
from statistics import median
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.bench_openpilot import fill
import capnp
from openpilot.cereal import log, messaging
from openpilot.tools.lib.logreader import LogReader

parser = argparse.ArgumentParser()
parser.add_argument('rlog')
parser.add_argument('--validate-only', action='store_true')
parser.add_argument('--train', default='/tmp/pr3704_logs/1.rlog.zst')
parser.add_argument('--repeat', type=int, default=5)
args = parser.parse_args()
cases = {}
def bench(name, operation, count, repeats):
    cases[name] = (operation, count)

events = list(LogReader(args.rlog))
first = {m.which(): m for m in reversed(events)}
selected = [events[i * len(events) // 1000] for i in range(1000)] + list(first.values())
wire = [m.as_builder().to_bytes() for m in selected]
readers = [messaging.log_from_bytes(b) for b in wire]
records = [m.to_dict() for m in readers]
sizes = [m.total_size.word_count + 1 for m in readers]
print('corpus', hashlib.sha256(b''.join(wire)).hexdigest(), len(wire), 'bytes', sum(map(len, wire)))
del events, first, selected

def build(factory, values, fields=False):
    if fields:
        return fill(factory(), values).to_bytes()
    builder = factory()
    builder.from_dict(values)
    return builder.to_bytes()

factories = {'default': lambda: log.Event.new_message()}
for words in (64, 256, 1024, 4096, 16384):
    factories[f'presize {words}'] = lambda words=words: capnp._MallocMessageBuilder(words).init_root(log.Event.schema)
    pool = capnp.BuilderPool(words, 1)
    factories[f'pool {words}'] = lambda pool=pool: pool.new_message(log.Event.schema)

training = list(LogReader(args.train))
trained_sizes = {}
for msg in training[:len(training) // 2]:
    kind = msg.which()
    trained_sizes[kind] = max(trained_sizes.get(kind, 1), msg.total_size.word_count + 1)
print('trained cached buffer bound bytes', sum(trained_sizes.values()) * 8, '(capacity * words * 8; native metadata and live messages extra)')
del training
for recycle in (False, True):
    pool = capnp.BuilderPool(1024, 1, recycle_builder=recycle)
    factories[f'pool1024 recycle={recycle}'] = lambda pool=pool: pool.new_message(log.Event.schema)

for words in (64, 256, 1024, 4096, 16384):
    pool = capnp.BuilderPool(words, 1, recycle_builder=True, reset_arena=True)
    factories[f'arena reset {words}'] = lambda pool=pool: pool.new_message(log.Event.schema)
bench('public kwargs', lambda: [log.Event.new_message(**r).to_bytes() for r in records], len(records), args.repeat)
for fields in (False, True):
    for name, factory in factories.items():
        def operation(factory=factory, fields=fields):
            return [build(factory, record, fields) for record in records]
        bench(('fields ' if fields else 'from_dict ') + name, operation, len(records), args.repeat)
    def exact(fields=fields):
        return [build(lambda n=n: capnp._MallocMessageBuilder(n).init_root(log.Event.schema), record, fields)
                for record, n in zip(records, sizes)]
    bench(('fields ' if fields else 'from_dict ') + 'input-size presize', exact, len(records), args.repeat)
    for pooled in (False, True):
        trained = {}
        for kind, words in trained_sizes.items():
            if pooled:
                pool = capnp.BuilderPool(words, 1, recycle_builder=True, reset_arena=True)
                trained[kind] = lambda pool=pool: pool.new_message(log.Event.schema)
            else:
                trained[kind] = lambda words=words: capnp._MallocMessageBuilder(words).init_root(log.Event.schema)
        kinds = [m.which() for m in readers]
        def operation(trained=trained, kinds=kinds, fields=fields):
            return [build(trained.get(kind, factories['default']), record, fields) for kind, record in zip(kinds, records)]
        bench(('fields ' if fields else 'from_dict ') + ('trained pool' if pooled else 'trained size'), operation, len(records), args.repeat)


# Isolate allocator impact for otherwise cheap fixed-size messages.
for name, factory in factories.items():
    bench('empty ' + name, lambda factory=factory: [factory().to_bytes() for _ in range(1000)], 1000, args.repeat)
gc.collect()


def canonical(message):
    return json.dumps(message.to_dict(verbose=True), sort_keys=True, default=lambda b: b.hex())
expected = [canonical(m) for m in readers]
empty = log.Event.new_message().to_bytes()
loops, samples = {}, {name: [] for name in cases}
for name, (operation, count) in cases.items():
    result = operation()
    if name.startswith('empty '):
        assert all(value == empty for value in result), name
    else:
        assert [canonical(messaging.log_from_bytes(value)) for value in result] == expected, name
    if not name.startswith('empty '):
        print('segments', name, sum(struct.unpack_from('<I', value)[0] > 0 for value in result), 'multisegment/', len(result))
    start = time.perf_counter()
    operation()
    loops[name] = max(1, int(0.08 / (time.perf_counter() - start)))
if args.validate_only:
    print('all variants semantically equivalent')
    sys.exit()
rng = random.Random(12345)
for _ in range(args.repeat):
    order = list(cases)
    rng.shuffle(order)
    for name in order:
        operation, count = cases[name]
        gc.collect()
        start = time.perf_counter()
        for _ in range(loops[name]):
            operation()
        samples[name].append((time.perf_counter() - start) * 1e6 / loops[name] / count)
for name, times in samples.items():
    print(f'{name:30} {median(times):8.3f} us/item [{min(times):.3f}, {max(times):.3f}]')
