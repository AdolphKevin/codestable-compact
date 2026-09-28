#!/usr/bin/env python3
"""Run CodeStable's fixed developer regression set and print its bounded metrics."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


class ReliabilityResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.measurements = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        if hasattr(test, "metrics"):
            self.measurements.update(test.metrics)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.dont_write_bytecode = True
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_knowledge_reliability.py")
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1, resultclass=ReliabilityResult).run(suite)
    print(json.dumps({"ok": result.wasSuccessful(), "scope": "fixed synthetic developer fixtures only",
                      "tests_run": result.testsRun, "metrics": result.measurements}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
