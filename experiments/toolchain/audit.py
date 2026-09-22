"""Audit retained binaries, actual command lines, and PGO coverage after a run."""

import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
results = root / "experiments/toolchain/results"
manifest = {}
for binary in sorted(results.glob("*.so")):
    if "rejected" in binary.name:
        continue
    variant = binary.stem
    lines = (results / (variant + ".build.txt")).read_text().splitlines()
    for line in lines:
        if "[-Wmissing-profile]" in line:
            assert "#source-location.c++.gcda" in line, line
        if "[-Wprofile-instr-unprofiled]" in line:
            assert 'file "source-location.c++"' in line, line
        assert "[-Wcoverage-mismatch]" not in line, line
        assert "[-Wprofile-instr-out-of-date]" not in line, line
    entry = {
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "bytes": binary.stat().st_size,
        "extension_build_commands": [line for line in lines if ("-c capnp/" in line or " -shared " in line)],
    }
    profiles = results / (variant + "-profiles")
    if profiles.exists() and not variant.startswith("clang"):
        entry["profile_files"] = sorted(p.name for p in profiles.glob("*.gcda"))
        for required in (
            "#capnp#lib#capnp.gcda",
            "dynamic.c++.gcda",
            "layout.c++.gcda",
            "message.c++.gcda",
            "parser.c++.gcda",
        ):
            assert any(required in name for name in entry["profile_files"])
    if profiles.exists() and variant.startswith("clang"):
        entry["profile_summary"] = subprocess.check_output(
            ["llvm-profdata", "show", str(profiles / "training.profdata")], text=True
        )
        text = (results / (variant + ".profiles.txt")).read_text()
        entry["profile_function_families"] = {}
        for name in ("__pyx", "DynamicStruct", "FlatArrayMessageReader", "SchemaParser"):
            entry["profile_function_families"][name] = text.count(name)
            assert entry["profile_function_families"][name]
    manifest[variant] = entry
(results / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(results / "experiment-sources.json").write_text(
    json.dumps(
        {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                root / "setup.py",
                root / "capnp/lib/capnp.cpp",
                root / "test/test_toolchain.py",
                *sorted((root / "experiments/toolchain").glob("*.py")),
            ]
        },
        indent=2,
    )
    + "\n"
)
