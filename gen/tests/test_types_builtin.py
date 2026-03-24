import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.types_builtin import extract_builtin
from data.types_builtin import ts_builtin
from data.types_builtin import wrap_builtin


class TestWrapBuiltin(unittest.TestCase):
    def test_bool(self):
        self.assertEqual(wrap_builtin('bool', 'x'), 'Napi::Boolean::New(env, x)')

    def test_float(self):
        self.assertEqual(wrap_builtin('float', 'v'), 'Napi::Number::New(env, v)')

    def test_int(self):
        self.assertEqual(wrap_builtin('int', 'n'), 'Napi::Number::New(env, n)')

    def test_void_returns_none(self):
        self.assertIsNone(wrap_builtin('void', 'x'))

    def test_long_long(self):
        result = wrap_builtin('long_long', 'v')
        self.assertIn('BigInt', result)
        self.assertIn('int64_t', result)

    def test_unsigned_long_long(self):
        result = wrap_builtin('unsigned_long_long', 'v')
        self.assertIn('BigInt', result)
        self.assertIn('uint64_t', result)


class TestExtractBuiltin(unittest.TestCase):
    def test_float(self):
        pre, expr = extract_builtin('float', 0)
        self.assertEqual(pre, [])
        self.assertIn('FloatValue()', expr)

    def test_bool(self):
        pre, expr = extract_builtin('bool', 1)
        self.assertEqual(pre, [])
        self.assertIn('info[1]', expr)
        self.assertIn('Value()', expr)

    def test_bigint(self):
        pre, expr = extract_builtin('long_long', 0)
        self.assertEqual(len(pre), 1)
        self.assertIn('Int64Value', pre[0])
        self.assertIn('_arg0', expr)

    def test_void_returns_none(self):
        self.assertIsNone(extract_builtin('void', 0))


class TestTsBuiltin(unittest.TestCase):
    def test_float_is_number(self):
        self.assertEqual(ts_builtin('float'), 'number')

    def test_bool_is_boolean(self):
        self.assertEqual(ts_builtin('bool'), 'boolean')

    def test_bigint(self):
        self.assertEqual(ts_builtin('long_long'), 'bigint')

    def test_void_none(self):
        self.assertIsNone(ts_builtin('void'))


if __name__ == '__main__':
    unittest.main()
