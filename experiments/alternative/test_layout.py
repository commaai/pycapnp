"""Reject unsupported schema evolution instead of silently compiling wrong accessors."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import capnp
from openpilot.cereal import log
from run import layout, require_field

with tempfile.TemporaryDirectory() as directory:
    schema = Path(directory) / "validation.capnp"
    schema.write_text("""@0xdbd49a865d1e30a7;
struct Sample {
 good @0 :Float32;
 bad @1 :UInt32;
 nums @2 :List(Float32);
 other @3 :List(Float64);
 payload @4 :Data = "nonempty";
 child @5 :Sample;
 union { variant @6 :Float32; otherwise @7 :Void; }
}
""")
    sample = capnp.load(str(schema)).Sample.schema
    require_field(sample, "good", "float32")
    require_field(sample, "nums", "list", "float32")
    require_field(sample, "child", "struct")
    for name, kind, element in [
        ("bad", "float32", None),
        ("other", "list", "float32"),
        ("payload", "data", None),
        ("variant", "float32", None),
    ]:
        try:
            require_field(sample, name, kind, element)
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported schema accepted")
    event = log.Event.schema
    fields = dict(event.fields)
    control = fields["carControl"]
    slot = control.proto.slot
    displaced = SimpleNamespace(
        type=slot.type,
        defaultValue=slot.defaultValue,
        hadExplicitDefault=slot.hadExplicitDefault,
        offset=slot.offset + 1,
    )
    fields["carControl"] = SimpleNamespace(
        schema=control.schema, proto=SimpleNamespace(slot=displaced, discriminantValue=control.proto.discriminantValue)
    )
    try:
        layout(SimpleNamespace(fields=fields, node=event.node))
    except ValueError:
        pass
    else:
        raise AssertionError("displaced union pointer accepted")
print("schema scalar/list/default/union-slot rejection checks passed")
