"""Alternate independent processes for the unchanged openpilot benchmark."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
from statistics import median
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()

    return {
        "path": str(path), "commit": git("rev-parse", "HEAD"),
        "diff": git("diff", "HEAD"), "status": git("status", "--short"),
        "extensions": {str(p.relative_to(path)): digest(p) for p in path.glob("capnp/lib/*.so")},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("rlog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--python", default="/home/batman/openpilot/.venv/bin/python")
    parser.add_argument("--openpilot", type=Path, default=Path("/home/batman/openpilot"))
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--messages", type=int, default=1000)
    parser.add_argument("--cpu", type=int, default=0)
    args = parser.parse_args()
    if min(args.rounds, args.repeat, args.messages) < 1:
        parser.error("rounds, repeat, and messages must be positive")
    paths = {name: getattr(args, name).resolve() for name in ("baseline", "candidate")}
    script = Path(__file__).resolve().parents[1] / "benchmarks/bench_openpilot.py"
    result = {
        "host": platform.platform(), "cpu": args.cpu, "script_sha256": digest(script),
        "rlog": str(args.rlog.resolve()), "rlog_sha256": digest(args.rlog),
        "implementations": {name: identity(path) for name, path in paths.items()},
        "runs": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    corpus = None
    for round_index in range(args.rounds):
        order = ("baseline", "candidate") if round_index % 2 == 0 else ("candidate", "baseline")
        for name in order:
            env = dict(os.environ, PYTHONPATH=f"{paths[name]}:{args.openpilot.resolve()}", PYTHONHASHSEED="0")
            command = ["taskset", "-c", str(args.cpu), args.python, str(script), str(args.rlog.resolve()),
                       "--repeat", str(args.repeat), "--messages", str(args.messages)]
            completed = subprocess.run(command, cwd=paths[name], env=env, capture_output=True, text=True)
            run = {"name": name, "round": round_index, "time": time.time(), "command": command,
                   "stdout": completed.stdout, "stderr": completed.stderr, "returncode": completed.returncode}
            result["runs"].append(run)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            completed.check_returncode()
            found = re.search(r"^sha256=(\w+) bytes=(\d+)$", completed.stdout, re.M)
            if found is None or (corpus is not None and found.groups() != corpus):
                raise RuntimeError("Missing or unequal corpus hashes")
            corpus = found.groups()
            run["us_per_item"] = {
                match[1].strip(): float(match[2]) for match in re.finditer(
                    r"^(.+?)\s+([0-9.]+) us/item", completed.stdout, re.M
                )
            }
            if len(run["us_per_item"]) != 12:
                raise RuntimeError("Expected all 12 benchmark cases")
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(f"Finished {name} round {round_index + 1}", flush=True)
    for case in result["runs"][0]["us_per_item"]:
        values = {name: median(r["us_per_item"][case] for r in result["runs"] if r["name"] == name)
                  for name in paths}
        print(f"{case:20} {values['baseline']:9.2f} -> {values['candidate']:9.2f} us/item "
              f"({values['baseline'] / values['candidate']:.3f}x)")


if __name__ == "__main__":
    main()
