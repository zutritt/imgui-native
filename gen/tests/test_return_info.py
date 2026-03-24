import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.types import return_info
from tests.test_fixtures import FakeRegistry


class TestReturnInfo(unittest.TestCase):
    def setUp(self):
        self.reg = FakeRegistry()

    def test_void_returns_none(self):
        desc = {'kind': 'Builtin', 'builtin_type': 'void'}
        ri = return_info(desc, self.reg)
        self.assertIsNone(ri)

    def test_bool_return(self):
        desc = {'kind': 'Builtin', 'builtin_type': 'bool'}
        ri = return_info(desc, self.reg)
        self.assertIsNotNone(ri)
        self.assertEqual(ri.ts_type, 'boolean')
        self.assertIn('{val}', ri.wrap)

    def test_float_return(self):
        desc = {'kind': 'Builtin', 'builtin_type': 'float'}
        ri = return_info(desc, self.reg)
        self.assertIsNotNone(ri)
        self.assertEqual(ri.ts_type, 'number')

    def test_const_char_ptr_return(self):
        desc = {
            'kind': 'Pointer',
            'inner_type': {
                'kind': 'Builtin',
                'builtin_type': 'char',
                'storage_classes': ['const'],
            },
        }
        ri = return_info(desc, self.reg)
        self.assertIsNotNone(ri)
        self.assertEqual(ri.ts_type, 'string | null')


if __name__ == '__main__':
    unittest.main()
