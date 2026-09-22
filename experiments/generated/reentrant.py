"""Run mutation-callback regressions in subprocesses so crashes are reported."""

import argparse
import importlib
from pathlib import Path
import subprocess
import sys

CASES = (
    "clear_list",
    "clear_outer_dict",
    "mutate_keys",
    "property_list",
    "list_view",
    "nested_lists",
    "raise_after_clear",
    "property_dict",
    "list_view_dict",
    "index_callback",
    "length_hint",
)


def run(module, case):
    mod = importlib.import_module(module)
    from openpilot.cereal import messaging

    class Mutator:
        def __init__(self, action, fail=False):
            self.action = action
            self.fail = fail

        def __float__(self):
            self.action()
            if self.fail:
                raise RuntimeError("conversion failed")
            return 1.5

    if case == "clear_list":
        values = []
        values.extend([Mutator(values.clear), 2.5])
        wire = mod.from_dict({"longitudinalPlan": {"speeds": values}})
        assert list(messaging.log_from_bytes(wire).longitudinalPlan.speeds) == [1.5, 2.5]
    elif case == "clear_outer_dict":
        record = {}
        record.update(
            {"longitudinalPlan": {"speeds": [Mutator(record.clear), 2.5], "shouldStop": True}, "valid": False}
        )
        wire = mod.from_dict(record)
        reader = messaging.log_from_bytes(wire)
        assert (
            list(reader.longitudinalPlan.speeds) == [1.5, 2.5]
            and reader.longitudinalPlan.shouldStop
            and not reader.valid
        )
    elif case == "mutate_keys":
        child = {}

        def mutate():
            child.clear()
            child.update({str(i): i for i in range(1000)})

        child.update({"speeds": [Mutator(mutate)], "shouldStop": True})
        wire = mod.from_dict({"longitudinalPlan": child})
        assert messaging.log_from_bytes(wire).longitudinalPlan.shouldStop
    elif case == "property_list":
        event = mod.new()
        plan = event.init("longitudinalPlan")
        values = []
        values.extend([Mutator(values.clear), 2.5])
        plan.speeds = values
        assert plan.speeds == [1.5, 2.5]
    elif case == "list_view":
        event = mod.new()
        view = event.init("longitudinalPlan").init("speeds", 2)
        # Replacement can orphan the old list but cannot free its arena while a view exists.
        view[0] = Mutator(lambda: event.init("carState"))
        assert view[0] == 1.5
    elif case == "nested_lists":
        # A struct-list item can clear the outer collection containing the live item.
        event = mod.new()

        class Iterable:
            def __iter__(self):
                leads.clear()
                return iter([1.0, 2.0])

        leads = [{"x": Iterable()}]
        wire = mod.from_dict({"modelV2": {"leadsV3": leads}})
        assert list(messaging.log_from_bytes(wire).modelV2.leadsV3[0].x) == [1.0, 2.0]
    elif case == "property_dict":
        event = mod.new()
        child = {}
        child.update({"speeds": [Mutator(child.clear), 2.5], "shouldStop": True})
        event.longitudinalPlan = child
        assert event.longitudinalPlan.speeds == [1.5, 2.5] and event.longitudinalPlan.shouldStop
    elif case == "list_view_dict":
        view = mod.new().init("modelV2").init("leadsV3", 1)
        child = {}
        child.update({"x": [Mutator(child.clear), 2.5], "prob": 0.5})
        view[0] = child
        assert view[0].x == [1.5, 2.5] and view[0].prob == 0.5
    elif case == "index_callback":
        root = {}

        class Index:
            def __index__(self):
                root.clear()
                return 7

        root.update({"longitudinalPlan": {"speeds": [Index(), 2.5]}, "valid": False})
        reader = messaging.log_from_bytes(mod.from_dict(root))
        assert list(reader.longitudinalPlan.speeds) == [7.0, 2.5] and not reader.valid
    elif case == "length_hint":
        root = {}

        class Values:
            def __init__(self):
                self.index = 0

            def __iter__(self):
                return self

            def __length_hint__(self):
                root.clear()
                return 2

            def __next__(self):
                self.index += 1
                if self.index > 2:
                    raise StopIteration
                return float(self.index)

        root.update({"longitudinalPlan": {"speeds": Values()}, "valid": False})
        reader = messaging.log_from_bytes(mod.from_dict(root))
        assert list(reader.longitudinalPlan.speeds) == [1.0, 2.0] and not reader.valid
    elif case == "raise_after_clear":
        values = []
        values.extend([Mutator(values.clear, True), 2.5])
        try:
            mod.from_dict({"longitudinalPlan": {"speeds": values}})
        except RuntimeError as exc:
            assert str(exc) == "conversion failed"
        else:
            raise AssertionError("missing conversion exception")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--module")
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.module:
        run(args.module, args.case)
    else:
        for module in ("generated_native", "generated_cython"):
            for case in CASES:
                subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--module", module, "--case", case], check=True
                )
        print(f"{len(CASES) * 2} reentrant subprocess regressions: PASS")
