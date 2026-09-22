"""Sequential main-agent reruns of the isolated experiments on a paused build host."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TREES = Path('/tmp/capnp-speed')
PY = '/home/batman/openpilot/.venv/bin/python'
OP = '/home/batman/openpilot'
TRAIN = '/tmp/pr3704_logs/1.rlog.zst'
HELD = '/tmp/opendbc_logs/ascent_1.rlog.zst'
OUT = ROOT / 'experiments/results'
JOBS = []


def add(name, tree, script, args=(), cpu='0', imports=None, overrides=None):
    cwd = TREES / tree
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('CAPNP_', 'GENERATED_')):
            del env[key]
    env['PYTHONPATH'] = imports or f'{cwd}:{OP}'
    env['PYTHONHASHSEED'] = '0'
    env.update(overrides or {})
    JOBS.append((name, cwd, ['taskset', '-c', cpu, PY, script, *map(str, args)], env))


add('dynamic-heldout', 'dynamic', str(ROOT / 'experiments/compare.py'),
    [TREES / 'baseline', TREES / 'dynamic', HELD, OUT / 'dynamic-heldout.json', '--rounds', '2'])
for label, knobs in [
    ('fastattr-off', {'CAPNP_FAST_GETATTR': '0'}),
    ('union-off', {'CAPNP_UNION_CACHE': '0'}),
    ('plans-off', {'CAPNP_UNION_CACHE': '0', 'CAPNP_DICT_PLANS': '0'}),
    ('primitive-export-off', {'CAPNP_PRIMITIVE_LISTS': '0'}),
    ('primitive-import-off', {'CAPNP_PRIMITIVE_IMPORT': '0'}),
    ('confirm', {}),
]:
    add('dynamic-' + label, 'dynamic', 'benchmarks/bench_openpilot.py', [TRAIN], overrides=knobs)
for tag, log in [('route', TRAIN), ('heldout', HELD)]:
    add('bulk-' + tag, 'bulk', 'experiments/bulk/bench.py', [log, '--output', OUT / f'bulk-{tag}.json'])
    add('generated-' + tag, 'generated', 'experiments/generated/benchmark.py', [log, '--repeat', '5'],
        imports=f'{TREES}/baseline:{OP}:{TREES}/generated/experiments/generated')
    add('consumer-' + tag, 'bulk', 'experiments/bulk/bench_generated_consumer.py',
        [log, '--output', OUT / f'consumer-{tag}.json'],
        imports=f'{TREES}/bulk:{OP}:{TREES}/generated/experiments/generated')
add('generated-vs-optimized', 'generated', 'experiments/generated/benchmark.py', [TRAIN, '--repeat', '5'],
    imports=f'{TREES}/dynamic:{OP}:{TREES}/generated/experiments/generated')
add('generated-ablation', 'generated', 'experiments/generated/ablate.py', [TRAIN],
    imports=f'{TREES}/baseline:{OP}:{TREES}/generated/experiments/generated')
add('generated-startup', 'baseline', str(TREES / 'generated/experiments/generated/startup.py'), [TRAIN, '--repeat', '15'],
    imports=f'{TREES}/baseline:{OP}:{TREES}/generated/experiments/generated')
add('logreader', 'logreader', 'experiments/logreader/bench.py', [TRAIN, HELD, '--repeat', '7'], cpu='0,1')
add('logreader-ablation', 'logreader', 'experiments/logreader/ablate.py', [TRAIN, HELD, '--repeat', '5'], cpu='0,1')
for tag, log in [('route', TRAIN), ('heldout', HELD)]:
    add('allocation-' + tag, 'allocation', 'experiments/allocation/bench_allocation.py',
        [log, '--train', '/tmp/pr3704_logs/0.rlog.zst', '--repeat', '9'])
add('schema-startup', 'allocation', 'experiments/allocation/bench_schema.py', ['--repeat', '15'])
JOBS.append(('schema-hyperfine', TREES / 'allocation',
             ['taskset', '-c', '0', 'hyperfine', '--warmup', '3', '--runs', '20', '--export-json',
              str(OUT / 'schema-hyperfine.json'), '-L', 'mode', 'source,compiled,lazy,create',
              PY + ' experiments/allocation/bench_schema.py --child {mode}'], JOBS[-1][3].copy()))
add('schema-prepare', 'allocation', 'experiments/allocation/bench_compiled_workload.py', ['prepare'])
for mode in ('eager', 'lazy'):
    add('schema-' + mode, 'allocation', 'experiments/allocation/bench_compiled_workload.py', [mode, TRAIN])
archive = ROOT / 'build/temp.linux-x86_64-cpython-312/capnproto/libcapnp-vendored.a'
for tag, log in [('route', TRAIN), ('heldout', HELD)]:
    imports = f'/tmp/capnp-speed-pybind-deps:{TREES}/baseline:{OP}'
    add('alternative-' + tag, 'alternative', 'experiments/alternative/run.py', [log], imports=imports)
    add('backend-control-' + tag, 'alternative', 'experiments/alternative/control.py',
        [log, '--archive', archive], imports=imports)
add('jit-startup', 'alternative', 'experiments/alternative/measure_startup.py',
    ['--runs', '15', '--output', OUT / 'jit-startup.json'],
    imports=f'/tmp/capnp-speed-pybind-deps:{TREES}/baseline:{OP}')
for candidate in ('pgo-lto-hidden', 'clang', 'clang-pgo-thinlto', 'clang-pgo-thinlto-native-hidden'):
    for tag, log in [('route', TRAIN), ('heldout', HELD)]:
        add('toolchain-' + candidate + '-' + tag, 'toolchain', 'experiments/toolchain/compare.py',
            ['--python', PY, '--openpilot', OP, '--log', log, '--candidate', candidate,
             '--cpu', '0', '--label', 'root-' + candidate + '-' + tag])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', help='Run job names containing this substring')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    for name, cwd, command, env in JOBS:
        if args.only and args.only not in name:
            continue
        metadata_path = OUT / f'{name}.run.json'
        if args.resume and metadata_path.exists() and json.loads(metadata_path.read_text()).get('returncode') == 0:
            continue
        metadata = {'name': name, 'cwd': str(cwd), 'command': command, 'pythonpath': env['PYTHONPATH'],
                    'tuning': {k: v for k, v in env.items() if k.startswith(('CAPNP_', 'GENERATED_'))},
                    'commit': subprocess.check_output(['git', '-C', str(cwd), 'rev-parse', 'HEAD'], text=True).strip(),
                    'extensions': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in list(cwd.glob('capnp/lib/*.so')) + list(cwd.glob('experiments/generated/*.so'))},
                    'started': time.time()}
        print('START', name, flush=True)
        with (OUT / f'{name}.txt').open('w') as output:
            proc = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        metadata.update(returncode=proc.returncode, elapsed=time.time() - metadata['started'])
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        print('END', name, proc.returncode, round(metadata['elapsed'], 1), flush=True)
        proc.check_returncode()


if __name__ == '__main__':
    main()
