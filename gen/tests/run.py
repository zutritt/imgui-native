import doctest
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.naming
import core.text


def suite():
    s = unittest.TestSuite()

    s.addTests(doctest.DocTestSuite(core.text))
    s.addTests(doctest.DocTestSuite(core.naming))

    loader = unittest.TestLoader()
    s.addTests(loader.discover(str(Path(__file__).parent), pattern='test_*.py'))

    return s


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    sys.exit(0 if result.wasSuccessful() else 1)
