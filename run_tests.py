#!/usr/bin/env python3
"""Run every test suite in the project.

    python run_tests.py           all suites
    python run_tests.py -v        verbose, one line per test
    python run_tests.py exam      only suites whose filename matches 'exam'
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbosity = 2 if "-v" in argv else 1
    filters = [a for a in argv if not a.startswith("-")]

    names = sorted(
        name[:-3] for name in os.listdir(TESTS)
        if name.startswith("test_") and name.endswith(".py")
    )
    if filters:
        names = [n for n in names if any(f in n for f in filters)]
    if not names:
        print("No test modules matched.")
        return 1

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in names:
        suite.addTests(loader.loadTestsFromModule(__import__(name)))

    print("Running %d suite(s): %s" % (len(names), ", ".join(names)))
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
