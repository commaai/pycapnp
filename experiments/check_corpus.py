"""Fingerprint real-message conversions for cross-build semantic comparisons."""

import argparse
import base64
import hashlib
import json
from pathlib import Path

import capnp
from openpilot.cereal import log, messaging
from openpilot.tools.lib.logreader import LogReader


def encode_extra(value):
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode()}
    raise TypeError(type(value).__name__)


def canonical(value):
    return json.dumps(value, sort_keys=True, default=encode_extra).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--messages", type=int, default=1000)
    args = parser.parse_args()
    results = {}
    for path in args.logs:
        events = list(LogReader(str(path.resolve())))
        first = {m.which(): m for m in reversed(events)}
        count = min(args.messages, len(events))
        selected = [events[i * len(events) // count] for i in range(count)] + list(first.values())
        checksums = {name: hashlib.sha256() for name in ("wire", "dict", "verbose", "kwargs")}
        for event in selected:
            wire = event.as_builder().to_bytes()
            message = messaging.log_from_bytes(wire)
            values = message.to_dict()
            verbose = message.to_dict(verbose=True)
            rebuilt = log.Event.new_message(**values)
            # Compare semantic representations: an explicit-default pointer may
            # have a different allocation layout after dictionary construction.
            assert canonical(rebuilt.to_dict()) == canonical(values), event.which()
            checksums["wire"].update(wire)
            for name, value in (("dict", values), ("verbose", verbose), ("kwargs", rebuilt.to_dict())):
                checksums[name].update(canonical(value))
        results[str(path)] = {"count": len(selected), "types": sorted(first),
                              "checksums": {name: value.hexdigest() for name, value in checksums.items()}}
    print(json.dumps({"capnp": capnp.__file__, "results": results}, indent=2))


if __name__ == "__main__":
    main()
