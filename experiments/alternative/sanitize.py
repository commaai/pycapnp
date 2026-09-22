"""Build and run ASan/UBSan over the exact extension kernel and Python outputs."""

from pathlib import Path
import argparse
import sys
import os
import struct
import subprocess
import sysconfig
import tempfile
from openpilot.tools.lib.logreader import LogReader
from run import ROOT, layout

parser = argparse.ArgumentParser()
parser.add_argument("rlog", type=Path, nargs="?", default=Path("/tmp/pr3704_logs/1.rlog.zst"))
args = parser.parse_args()

with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    (temp / "layout.h").write_text(layout())
    groups = {kind: 0 for kind in ["carState", "carControl", "modelV2", "longitudinalPlan", "can"]}
    with (temp / "seeds").open("wb") as stream:
        for event in LogReader(str(args.rlog)):
            kind = event.which()
            if kind in groups and groups[kind] < 10:
                data = event.as_builder().to_bytes()
                stream.write(struct.pack("<Q", len(data)) + data)
                groups[kind] += 1
            if all(count == 10 for count in groups.values()):
                break
    libdir = sysconfig.get_config_var("LIBDIR")
    subprocess.run(
        [
            "cc",
            "-O1",
            "-g",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-I" + sysconfig.get_paths()["include"],
            "-I" + str(temp),
            str(ROOT / "sanitize.c"),
            "-L" + libdir,
            "-Wl,-rpath," + libdir,
            f"-lpython{sys.version_info.major}.{sys.version_info.minor}",
            "-o",
            str(temp / "sanitize"),
        ],
        check=True,
    )
    subprocess.run(
        [str(temp / "sanitize"), str(temp / "seeds")],
        env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1"),
        check=True,
    )
