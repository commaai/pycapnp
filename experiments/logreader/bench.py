"""Equal-output log workloads; I/O/decompression excluded from all timings."""
import argparse
import gc
import hashlib
import json
import os
import pickle
import random
import statistics
import subprocess
import time
from pathlib import Path

import capnp
import zstandard
from openpilot.cereal import log
from openpilot.tools.lib.logreader import LogReader
from capnp.logstream import RawLog, project_many
from capnp.lib.capnp import project_stream

QUERIES = {
    'scalar': ('carState', ['logMonoTime','carState.vEgo','carState.steeringAngleDeg','carState.wheelSpeeds.fl']),
    'wide': ('carState', ['logMonoTime'] + ['carState.' + p for p in ['vEgo','aEgo','steeringAngleDeg','steeringRateDeg','wheelSpeeds.fl','wheelSpeeds.fr','wheelSpeeds.rl','wheelSpeeds.rr']]),
    'model': ('modelV2', ['logMonoTime','modelV2.position.x','modelV2.position.y','modelV2.leadsV3.x']),
    'can': ('can', ['logMonoTime','can.address','can.dat','can.src']),
    'rare': ('carParams', ['logMonoTime','carParams.mass']),
}


def field(value, parts):
    if isinstance(value, capnp._DynamicListReader):
        return [field(v,parts) for v in value]
    if parts:
        return field(getattr(value,parts[0]),parts[1:])
    return value.raw if isinstance(value,capnp.lib.capnp._DynamicEnum) else value


def reference(data, selected, paths):
    parts = [p.split('.') for p in paths]
    return [tuple(field(e,p) for p in parts) for e in LogReader.from_bytes(data) if e.which() == selected]


def idiomatic(data, query):
    selected = QUERIES[query][0]
    rows = []
    for e in LogReader.from_bytes(data):
        if e.which() != selected:
            continue
        if query == 'scalar':
            c = e.carState
            row = (e.logMonoTime,c.vEgo,c.steeringAngleDeg,c.wheelSpeeds.fl)
        elif query == 'wide':
            c = e.carState
            wheels = c.wheelSpeeds
            row = (e.logMonoTime,c.vEgo,c.aEgo,c.steeringAngleDeg,c.steeringRateDeg,wheels.fl,wheels.fr,wheels.rl,wheels.rr)
        elif query == 'model':
            m = e.modelV2
            p = m.position
            row = (e.logMonoTime,list(p.x),list(p.y),[list(lead.x) for lead in m.leadsV3])
        elif query == 'can':
            frames = e.can
            row = (e.logMonoTime,[f.address for f in frames],[f.dat for f in frames],[f.src for f in frames])
        else:
            row = (e.logMonoTime,e.carParams.mass)
        rows.append(row)
    return rows


def consume(events):
    return [(e.logMonoTime,e.which()) for e in events]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('logs', nargs='+')
    parser.add_argument('--repeat', type=int, default=5)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    data = []
    for path in args.logs:
        with Path(path).open('rb') as compressed:
            with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
                data.append(reader.read())
    cases, counts = {}, {}
    for query, (selected, paths) in QUERIES.items():
        expected = [reference(d,selected,paths) for d in data]
        native = lambda selected=selected, paths=paths: [project_stream(d,log.Event.schema,selected,paths) for d in data]
        threaded = lambda selected=selected, paths=paths: project_many(data,log.Event,selected,paths,workers=args.workers)
        assert expected == native() == threaded() == [idiomatic(d,query) for d in data], query
        counts[query] = [len(rows) for rows in expected]
        cases[query+'_logreader'] = lambda query=query: [idiomatic(d,query) for d in data]
        cases[query+'_native'] = native
        cases[query+'_threads'] = threaded
    sample = list(LogReader.from_bytes(data[0]))[::100]
    sample_bytes = b''.join(e.as_builder().to_bytes() for e in sample)
    rawlog = RawLog(sample_bytes,log.Event)
    raw = list(rawlog)
    def roundtrip(events):
        return consume(pickle.loads(pickle.dumps(events,protocol=5)))
    def buffer_roundtrip(events):
        buffers = []
        metadata = pickle.dumps(events,protocol=5,buffer_callback=buffers.append)
        return consume(pickle.loads(metadata,buffers=buffers))
    assert roundtrip(raw) == roundtrip(rawlog) == roundtrip(sample) == buffer_roundtrip(rawlog)
    assert b''.join(e.serialized_view() for e in raw) == sample_bytes
    for d in data:
        assert consume(LogReader.from_bytes(d)) == consume(RawLog(d,log.Event))
        assert consume(list(LogReader.from_bytes(d))[::100]) == consume(RawLog(d,log.Event)[i] for i in range(0,len(RawLog(d,log.Event)),100))
    cases.update({
        'setup_eager_logreader': lambda: [LogReader.from_bytes(d) for d in data],
        'setup_lazy_rawlog': lambda: [RawLog(d,log.Event) for d in data],
        'consume_logreader': lambda: [consume(LogReader.from_bytes(d)) for d in data],
        'consume_rawlog': lambda: [consume(RawLog(d,log.Event)) for d in data],
        'sparse_logreader': lambda: [consume(list(LogReader.from_bytes(d))[::100]) for d in data],
        'sparse_rawlog': lambda: [consume(r[i] for i in range(0,len(r),100)) for r in (RawLog(d,log.Event) for d in data)],
        'pickle_logreader': lambda: roundtrip(sample),
        'pickle_raw_events': lambda: roundtrip(raw),
        'pickle_raw_log': lambda: roundtrip(rawlog),
        'pickle_raw_log_oob': lambda: buffer_roundtrip(rawlog),
        'forward_prepared_logreader': lambda: b''.join(e.as_builder().to_bytes() for e in sample),
        'forward_prepared_raw': lambda: b''.join(e.serialized_view() for e in raw),
        'forward_cold_logreader': lambda: b''.join(e.as_builder().to_bytes() for e in LogReader.from_bytes(sample_bytes)),
        'forward_cold_raw': lambda: RawLog(sample_bytes,log.Event).to_bytes(),
    })
    loops = {}
    for name, fn in cases.items():
        start = time.perf_counter()
        result = fn()
        del result
        loops[name] = max(1,min(10000,int(0.1 / max(time.perf_counter()-start,1e-9))))
    samples = {name:[] for name in cases}
    rng = random.Random(0)
    for _ in range(args.repeat):
        order = list(cases)
        rng.shuffle(order)
        for name in order:
            gc.collect()
            start = time.perf_counter()
            for _ in range(loops[name]):
                result = cases[name]()
                del result
            samples[name].append((time.perf_counter()-start)*1000/loops[name])
    output = {
        'revision': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'extension': capnp.lib.capnp.__file__, 'affinity': sorted(os.sched_getaffinity(0)),
        'workers': args.workers, 'repeat': args.repeat, 'loops': loops,
        'files': [{'path':p,'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()} for p,d in zip(args.logs,data)],
        'query_rows': counts,
        'results': {name:{'median_ms':statistics.median(values),'samples_ms':values} for name,values in samples.items()},
    }
    print(json.dumps(output,indent=2))


if __name__ == '__main__':
    main()
