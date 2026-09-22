"""Build compiler variants, train PGO separately, and run the unchanged openpilot benchmark."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--build-python", required=True)
p.add_argument("--bench-python", required=True)
p.add_argument("--openpilot", required=True)
p.add_argument("--train", required=True)
p.add_argument("--evaluate", required=True)
p.add_argument("--cpu", default="17")
p.add_argument("--build-cpus", default="18,19")
p.add_argument("--variants", nargs="+", default=["baseline", "o2", "native", "lto", "pgo", "pgo-lto", "pgo-lto-native"])
p.add_argument("--repeat", type=int, default=7)
a = p.parse_args()
out = ROOT / "experiments/toolchain/results"
out.mkdir(exist_ok=True)
base_env = dict(os.environ, PYTHONPATH=f"{ROOT}:{Path(a.openpilot).resolve()}")
for key in ("CFLAGS", "CXXFLAGS", "LDFLAGS", "CPPFLAGS", "PYCAPNP_OPT_FLAGS", "CC", "CXX"):
    base_env.pop(key, None)
abi = [
    subprocess.check_output(
        [python, "-c", "import sysconfig; print(sysconfig.get_config_var('SOABI'))"], text=True
    ).strip()
    for python in (a.build_python, a.bench_python)
]
assert abi[0] == abi[1], f"Build and benchmark ABI differ: {abi}"
meta = {
    "arguments": vars(a),
    "abi": abi[0],
    "cython": subprocess.check_output(
        [a.build_python, "-c", "import Cython; print(Cython.__version__)"], text=True
    ).strip(),
    "source_diff": subprocess.check_output(["git", "diff"], cwd=ROOT, text=True),
    "compiler": subprocess.check_output(["g++", "--version"], text=True),
    "logs": {
        key: hashlib.sha256(Path(value).read_bytes()).hexdigest()
        for key, value in [("train", a.train), ("evaluate", a.evaluate)]
    },
}
assert meta["logs"]["train"] != meta["logs"]["evaluate"], "Training and evaluation logs must differ"
(out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")


def command(cmd, name, env=base_env):
    with (out / name).open("w") as f:
        subprocess.run(cmd, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT, check=True)


def build(name, flags):
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    for binary in (ROOT / "capnp/lib").glob("*.so"):
        binary.unlink()
    # One switch applies to both C++ compilation paths and the extension link.
    env = dict(
        base_env,
        PYCAPNP_OPT_FLAGS=flags,
        CC="clang" if name.startswith("clang") else "gcc",
        CXX="clang++" if name.startswith("clang") else "g++",
    )
    start = time.monotonic()
    command(
        ["taskset", "-c", a.build_cpus, a.build_python, "setup.py", "build_ext", "--inplace", "-j", "2"],
        name + ".build.txt",
        env,
    )
    for line in (out / (name + ".build.txt")).read_text().splitlines():
        if "[-Wmissing-profile]" in line:
            # This archive member supplies debug-only diagnostics and is not
            # linked into the Release extension, so it cannot collect profiles.
            assert "#source-location.c++.gcda" in line, line
        if "[-Wprofile-instr-unprofiled]" in line:
            assert 'file "source-location.c++"' in line, line
    (out / (name + ".seconds")).write_text(f"{time.monotonic() - start:.2f}\n")


def bench(log, name, repeats):
    command(
        ["taskset", "-c", a.cpu, a.bench_python, "benchmarks/bench_openpilot.py", log, "--repeat", str(repeats)],
        name + ".bench.txt",
    )


for variant in a.variants:
    assert variant in {
        "baseline",
        "o2",
        "native",
        "lto",
        "pgo",
        "pgo-lto",
        "pgo-lto-native",
        "pgo-lto-hidden",
        "clang",
        "clang-thinlto",
        "clang-pgo-thinlto",
        "clang-pgo-thinlto-native-hidden",
    }
    flags = "-O2" if variant == "o2" else "-O3"
    if "lto" in variant:
        flags += " -flto=thin -fuse-ld=lld" if variant.startswith("clang") else " -flto=2 -fno-ipa-icf"
    if "hidden" in variant:
        flags += " -fvisibility=hidden -fno-semantic-interposition"
    if "native" in variant:
        flags += " -march=native"
    if "pgo" in variant:
        profiles = out / (variant + "-profiles")
        shutil.rmtree(profiles, ignore_errors=True)
        profiles.mkdir()
        if variant.startswith("clang"):
            build(variant + "-instrumented", flags + f" -fprofile-instr-generate={profiles}/training.profraw")
            bench(a.train, variant + "-training", 2)
            subprocess.run(
                [
                    "llvm-profdata",
                    "merge",
                    "-o",
                    str(profiles / "training.profdata"),
                    str(profiles / "training.profraw"),
                ],
                check=True,
            )
            command(
                ["llvm-profdata", "show", "--all-functions", "--counts", str(profiles / "training.profdata")],
                variant + ".profiles.txt",
            )
            command(["llvm-profdata", "show", str(profiles / "training.profdata")], variant + ".profile-summary.txt")
            profile_text = (out / (variant + ".profiles.txt")).read_text()
            for required in ("__pyx", "DynamicStruct", "FlatArrayMessageReader", "SchemaParser"):
                assert required in profile_text, f"Missing instrumented function family: {required}"
            flags += f" -fprofile-instr-use={profiles}/training.profdata -Werror=profile-instr-out-of-date"
        else:
            build(variant + "-instrumented", flags + f" -fprofile-generate={profiles}")
            bench(a.train, variant + "-training", 2)
            profile_names = [p.name for p in profiles.glob("*.gcda")]
            for required in (
                "#capnp#lib#capnp.gcda",
                "dynamic.c++.gcda",
                "layout.c++.gcda",
                "message.c++.gcda",
                "parser.c++.gcda",
            ):
                assert any(required in name for name in profile_names), f"Missing training profile: {required}"
            flags += f" -fprofile-use={profiles} -fprofile-correction -Werror=coverage-mismatch"
    build(variant, flags)
    binary = next((ROOT / "capnp/lib").glob("*.so"))
    shutil.copy2(binary, out / (variant + ".so"))
    provenance = dict(
        meta,
        flags=flags,
        actual_compiler=subprocess.check_output(
            ["clang++" if variant.startswith("clang") else "g++", "--version"], text=True
        ),
        experiment_source_sha256={
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                ROOT / "setup.py",
                ROOT / "capnp/lib/capnp.cpp",
                ROOT / "test/test_toolchain.py",
                *sorted((ROOT / "experiments/toolchain").glob("*.py")),
            ]
        },
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    )
    (out / (variant + ".metadata.json")).write_text(json.dumps(provenance, indent=2) + "\n")
    command(["taskset", "-c", a.cpu, a.build_python, "-m", "pytest", "-q", "test"], variant + ".tests.txt")
    bench(a.evaluate, variant, a.repeat)
    print(variant, "complete", flush=True)
