"""Plain-assert test runner. Usage: python3 tests/run_tests.py

Finds tests/test_*.py, runs every function named test_*. A test may raise
unittest.SkipTest to be reported as SKIPPED (never counted as passed).
Exit code is 0 only if no test failed.
"""

import importlib
import os
import sys
import traceback
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def main():
    passed, failed, skipped = 0, [], []
    for filename in sorted(os.listdir(HERE)):
        if not (filename.startswith("test_") and filename.endswith(".py")):
            continue
        module = importlib.import_module(filename[:-3])
        for name in sorted(n for n in dir(module) if n.startswith("test_")):
            fn = getattr(module, name)
            if not callable(fn):
                continue
            label = f"{filename[:-3]}.{name}"
            try:
                fn()
            except unittest.SkipTest as e:
                skipped.append((label, str(e)))
                print(f"SKIP  {label}: {e}")
            except Exception:
                failed.append(label)
                print(f"FAIL  {label}")
                traceback.print_exc()
            else:
                passed += 1
                print(f"ok    {label}")
    total = passed + len(failed) + len(skipped)
    print(f"\n{total} tests: {passed} passed, {len(failed)} failed, {len(skipped)} skipped")
    for label, reason in skipped:
        print(f"  skipped {label}: {reason}")
    for label in failed:
        print(f"  failed  {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
