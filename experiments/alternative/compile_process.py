"""Process-level cold compilation, cache lookup, and prebuilt-load comparison."""

import argparse
import importlib.util
from pathlib import Path
import tempfile
from run import compile_kernel

parser = argparse.ArgumentParser()
parser.add_argument("--cache", type=Path)
parser.add_argument("--load", type=Path)
args = parser.parse_args()
if args.load:
    spec = importlib.util.spec_from_file_location("wire", args.load)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
elif args.cache:
    _, path, _, _ = compile_kernel(args.cache)
    print(path)
else:
    with tempfile.TemporaryDirectory() as directory:
        compile_kernel(Path(directory))
