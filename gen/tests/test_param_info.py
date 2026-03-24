import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.types import param_info
from tests.test_fixtures import FakeRegistry
from tests.test_fixtures import make_builtin_arg
from tests.test_fixtures import make_ptr_arg


class TestParamInfo(unittest.TestCase):
    def setUp(self):
        self.reg = FakeRegistry()

    def test_float_param(self):
        a = make_builtin_arg('x', 'float')
        pi = param_info(a, None, 0, self.reg)
        self.assertIsNotNone(pi)
        self.assertEqual(pi.ts_type, 'number')
        self.assertIn('FloatValue()', pi.c_arg)

    def test_bool_param(self):
        a = make_builtin_arg('flag', 'bool')
        pi = param_info(a, None, 0, self.reg)
        self.assertIsNotNone(pi)
        self.assertEqual(pi.ts_type, 'boolean')

    def test_void_returns_none(self):
        a = make_builtin_arg('unused', 'void')
        pi = param_info(a, None, 0, self.reg)
        self.assertIsNone(pi)

    def test_varargs_returns_none(self):
        a = {
            'name': '...',
            'type': {'description': {'kind': 'Builtin', 'builtin_type': 'void'}},
            'is_varargs': True,
        }
        pi = param_info(a, None, 0, self.reg)
        self.assertIsNone(pi)

    def test_const_char_ptr(self):
        a = make_ptr_arg('label', 'Builtin', inner_bt='char', storage=['const'])
        pi = param_info(a, None, 0, self.reg)
        self.assertIsNotNone(pi)
        self.assertEqual(pi.ts_type, 'string')
        self.assertIn('.c_str()', pi.c_arg)

    def test_out_float_param(self):
        a = make_ptr_arg('out_h', 'Builtin', inner_bt='float')
        pi = param_info(a, None, 0, self.reg)
        self.assertIsNotNone(pi)
        self.assertTrue(pi.is_out)
        self.assertEqual(pi.out_c_type, 'float')

    def test_nullable_bool_ptr(self):
        a = make_ptr_arg('p_open', 'Builtin', inner_bt='bool', default='NULL')
        pi = param_info(a, None, 1, self.reg)
        self.assertIsNotNone(pi)
        self.assertIn('null', pi.ts_type)

    def test_with_default_value(self):
        a = make_builtin_arg('flags', 'int', default='0')
        pi = param_info(a, None, 2, self.reg)
        self.assertIsNotNone(pi)
        self.assertIn('IsUndefined', pi.c_arg)


if __name__ == '__main__':
    unittest.main()
