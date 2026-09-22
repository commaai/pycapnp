"""Safety, schema defaults/evolution, all Event arms, and mutable API checks."""

import gc
import struct
import sys
from opendbc.car import structs
import generated_cython
import generated_native
from openpilot.cereal import log, messaging
from benchmark import compare, equal, fill


def primitive(t):
    k = t.which()
    if k == "bool":
        return True
    if k.startswith("int"):
        return -(2 ** (int(k[3:]) - 2))
    if k.startswith("uint"):
        return 2 ** (int(k[4:]) - 1)
    if k.startswith("float"):
        return 1.25
    if k == "text":
        return "héllo 🙂"
    if k == "data":
        return b"\x00\xffbinary"
    if k == "void":
        return None
    return None


def values(schema, depth=0):
    if depth > 10:
        return {}
    result = {}
    union = False
    for name, f in schema.fields.items():
        p = f.proto
        if p.discriminantValue != 65535:
            if union:
                continue
            union = True
        if p.which() == "group":
            result[name] = values(f.schema, depth + 1)
            continue
        t = p.slot.type
        k = t.which()
        if k == "struct":
            result[name] = values(f.schema, depth + 1)
        elif k == "list":
            inner = t.list.elementType
            if inner.which() == "struct":
                result[name] = [values(f.schema.elementType, depth + 1)]
            elif inner.which() == "enum":
                result[name] = [next(iter(f.schema.elementType.enumerants))]
            elif inner.which() == "list":
                result[name] = []
            else:
                result[name] = [primitive(inner)]
        elif k == "enum":
            result[name] = next(iter(f.schema.enumerants))
        elif k == "anyPointer":
            continue  # Branded maps are covered by real logs.
        else:
            result[name] = primitive(t)
    return result


def main():
    records = []
    for name, f in log.Event.schema.fields.items():
        if f.proto.discriminantValue == 65535:
            continue
        t = f.proto.slot.type
        if t.which() == "struct":
            record = {name: values(f.schema)}
        elif t.which() == "list":
            record = {name: [values(f.schema.elementType)]} if t.list.elementType.which() == "struct" else {name: []}
        else:
            record = {name: primitive(t)}
        records.append(log.Event.new_message(**record).to_dict())
    for mod in (generated_native, generated_cython):
        for record in records:
            wire = log.Event.new_message(**record).to_bytes()
            compare(mod.from_bytes(wire), record, log.Event.schema)
            assert equal(messaging.log_from_bytes(mod.from_dict(record)).to_dict(), record)
            assert equal(messaging.log_from_bytes(fill(mod.new(), record).to_bytes()).to_dict(), record)
        # Bytes subclasses can own arbitrary references; copying avoids an invisible GC cycle.
        collected = []

        class OwnedBytes(bytes):
            def __del__(self):
                collected.append(True)

        data = OwnedBytes(log.Event.new_message(carState={}).to_bytes())
        reader = mod.from_bytes(data)
        data.reader = reader
        del data, reader
        gc.collect()
        assert collected == [True]
        # Missing data/pointer sections simulate an older zero-sized root schema.
        empty = mod.from_bytes(struct.pack("<IIQ", 0, 1, 0))
        assert empty.valid and empty.logMonoTime == 0
        # Multi-segment writer, native library handles far pointers.
        record = {"can": [{"address": 1, "src": 2, "dat": b"x" * 100_000}]}
        wire = mod.from_dict(record)
        assert mod.from_bytes(wire).can[0].dat == b"x" * 100_000
        # Mutating union, child-owner lifetime, primitive range/type checks.
        b = mod.new()
        c = b.init("carState")
        c.vEgo = 12.5
        assert b.carState.vEgo == 12.5
        b.init("carControl").enabled = True
        try:
            b.carState
        except ValueError:
            pass
        else:
            raise AssertionError("inactive union")
        del b
        gc.collect()
        c.vEgo = 4.0
        assert c.vEgo == 4.0
        with structs.CarState.from_bytes(c.to_bytes()) as child_read:
            assert child_read.vEgo == 4.0
        for record in (
            {"logMonoTime": -1},
            {"logMonoTime": 2**64},
            {"valid": "true"},
            {"x": 1},
            {1: 1},
            {"carState": {"gearShifter": "INVALID"}},
        ):
            try:
                mod.from_dict(record)
            except (ValueError, TypeError, OverflowError):
                pass
            else:
                raise AssertionError(record)
        for bad in (b"", b"bad", b"\xff" * 8, struct.pack("<IIQ", 0, 1, 0xFFFFFFFFFFFFFFFF)):
            try:
                mod.from_bytes(bad).which()
            except ValueError:
                pass
            else:
                raise AssertionError(bad)
        bad = b"\xff" * 8
        before = sys.getrefcount(bad)
        for _ in range(100):
            try:
                mod.from_bytes(bad)
            except ValueError:
                pass
        assert sys.getrefcount(bad) == before
        b = mod.new()
        plan = b.init("longitudinalPlan")
        view = plan.init("speeds", 3)
        view[0] = 1.25
        view[-1] = 3.5
        assert list(view) == [1.25, 0.0, 3.5] and plan.speeds == list(view)
        assert list(plan.view("speeds")) == list(view)
        read = mod.from_bytes(b.to_bytes()).longitudinalPlan.view("speeds")
        del b, plan
        gc.collect()
        assert len(read) == 3 and read[-1] == 3.5
        for index in (-4, 3):
            try:
                read[index]
            except IndexError:
                pass
            else:
                raise AssertionError("out of bounds")
        try:
            read[0] = 2
        except ValueError:
            pass
        else:
            raise AssertionError("mutable reader")
        print(mod.__name__, len(records), "Event arms: PASS")
    for name in dir(generated_cython):
        if name == "Base" or name.startswith("S") and name[1:].isdigit():
            obj = getattr(generated_cython, name)()
            try:
                obj.which()
            except ValueError:
                pass
            else:
                raise AssertionError(name)
    print("all uninitialized Cython constructors safely reject access: PASS")


if __name__ == "__main__":
    main()
