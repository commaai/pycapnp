"""Run each mode in a fresh process; compare incremental process peak RSS."""
import json
import resource
import sys
from pathlib import Path

import zstandard
from openpilot.cereal import log
from capnp.lib.capnp import project_stream
from bench import QUERIES

mode,query,path=sys.argv[1:]
with Path(path).open('rb') as compressed:
    with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
        data=reader.read()
options={'staged':{},'fused':{'fused':True},'flat':{'flat':True}}[mode]
selected,paths=QUERIES[query]
before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
result=project_stream(data,log.Event.schema,selected,paths,**options)
after=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({'mode':mode,'query':query,'rows':len(result),'base_peak_kib':before,'peak_kib':after,'incremental_peak_kib':after-before}))
