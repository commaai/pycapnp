"""Same-output structural ablations, randomized order, calibrated repeats."""
import argparse
import gc
import json
import os
import random
import statistics
import time
from pathlib import Path

import zstandard
from openpilot.cereal import log
from capnp.lib.capnp import project_stream
from capnp.logstream import project_many
from bench import QUERIES, idiomatic

parser = argparse.ArgumentParser()
parser.add_argument('logs',nargs='+')
parser.add_argument('--repeat',type=int,default=5)
args = parser.parse_args()
data=[]
for path in args.logs:
    with Path(path).open('rb') as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
            data.append(reader.read())
cases={}
for query,(selected,paths) in QUERIES.items():
    expected = [idiomatic(d,query) for d in data]
    for mode,options in [('staged',{}),('flat',{'flat':True}),('unshared',{'shared':False}),('fused',{'fused':True})]:
        fn=lambda selected=selected,paths=paths,options=options: [project_stream(d,log.Event.schema,selected,paths,**options) for d in data]
        assert fn()==expected,(query,mode)
        cases[query+'_'+mode]=fn
    for workers in (1,2):
        cases[query+'_threads'+str(workers)]=lambda selected=selected,paths=paths,workers=workers: project_many(data,log.Event,selected,paths,workers=workers)
loops={}
for name,fn in cases.items():
    start=time.perf_counter()
    result=fn()
    del result
    loops[name]=max(1,min(10000,int(.1/max(time.perf_counter()-start,1e-9))))
samples={name:[] for name in cases}
rng=random.Random(1)
for _ in range(args.repeat):
    order=list(cases)
    rng.shuffle(order)
    for name in order:
        gc.collect()
        start=time.perf_counter()
        for _ in range(loops[name]):
            result=cases[name]()
            del result
        samples[name].append((time.perf_counter()-start)*1000/loops[name])
print(json.dumps({'affinity':sorted(os.sched_getaffinity(0)),'loops':loops,'samples_ms':samples,'median_ms':{k:statistics.median(v) for k,v in samples.items()}},indent=2))
