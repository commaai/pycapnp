"""Full-message equality and error-path tests for selected direct-wire writers."""

from pathlib import Path
import tempfile
from openpilot.cereal import messaging
from run import compile_kernel, reference_write_can, reference_write_plan

with tempfile.TemporaryDirectory() as directory:
    module, _, _, _ = compile_kernel(Path(directory))
    tested = 0
    for count in [0, 1, 3, 17, 128, 1000]:
        for size in [0, 1, 7, 8, 9, 64]:
            row = (2**64 - 1, False, [(i, bytes(range(size)), i % 256) for i in range(count)])
            assert (
                messaging.log_from_bytes(module.write_can(row)).to_dict()
                == messaging.log_from_bytes(reference_write_can(row)).to_dict()
            )
            if len(row) == 3:
                actual, expected = module.write_can(row), reference_write_can(row)
            else:
                actual, expected = module.write_plan(row), reference_write_plan(row)
            assert messaging.log_from_bytes(actual).to_dict(verbose=True) == messaging.log_from_bytes(expected).to_dict(
                verbose=True
            )
            tested += 1
        for count2 in [0, 1, 4, 17]:
            row = (1234, True, [float(i) for i in range(count)], [-float(i) for i in range(count2)], True)
            assert (
                messaging.log_from_bytes(module.write_plan(row)).to_dict()
                == messaging.log_from_bytes(reference_write_plan(row)).to_dict()
            )
            if len(row) == 3:
                actual, expected = module.write_can(row), reference_write_can(row)
            else:
                actual, expected = module.write_plan(row), reference_write_plan(row)
            assert messaging.log_from_bytes(actual).to_dict(verbose=True) == messaging.log_from_bytes(expected).to_dict(
                verbose=True
            )
            tested += 1
    # __float__ may re-enter Python and mutate the original list while native code runs.
    values = []

    class MutatingFloat:
        def __float__(self):
            values.clear()
            return 1.0

    values.extend([MutatingFloat(), 2.0])
    decoded = messaging.log_from_bytes(module.write_plan((0, True, values, [], False)))
    assert list(decoded.longitudinalPlan.speeds) == [1.0, 2.0]
    invalid = [
        (module.write_can, (0, True, [(2**32, b"", 0)])),
        (module.write_can, (0, True, [(0, b"", 256)])),
        (module.write_can, (0, True, [(0, "", 0)])),
        (module.write_plan, (0, True, ["invalid"], [], False)),
        (module.write_plan, (-1, True, [], [], False)),
    ]
    for fn, row in invalid:
        try:
            fn(row)
        except (ValueError, TypeError, OverflowError):
            pass
        else:
            raise AssertionError("invalid writer input accepted")
    print(f"{tested} full-message list/Data writer cases and {len(invalid)} error cases passed")
