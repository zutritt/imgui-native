import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from data.typedefs import TypedefResolver

SAMPLE_TYPEDEFS = [
    {
        'name': 'ImU32',
        'type': {'description': {'kind': 'Builtin', 'builtin_type': 'unsigned_int'}},
    },
    {
        'name': 'ImU64',
        'type': {'description': {'kind': 'Builtin', 'builtin_type': 'unsigned_long_long'}},
    },
    {'name': 'ImTextureID', 'type': {'description': {'kind': 'User', 'name': 'ImU64'}}},
    {
        'name': 'ImGuiWindowFlags',
        'type': {'description': {'kind': 'Builtin', 'builtin_type': 'int'}},
    },
    {
        'name': 'ImGuiInputTextCallback',
        'type': {'description': {'kind': 'Type', 'name': 'ImGuiInputTextCallback'}},
    },
]


class TestTypedefResolver(unittest.TestCase):
    def setUp(self):
        self.r = TypedefResolver(SAMPLE_TYPEDEFS)

    def test_direct_builtin(self):
        result = self.r.resolve('ImU32')
        self.assertEqual(result['builtin_type'], 'unsigned_int')

    def test_chain(self):
        result = self.r.resolve('ImTextureID')
        self.assertEqual(result['builtin_type'], 'unsigned_long_long')

    def test_external_size_t(self):
        result = self.r.resolve('size_t')
        self.assertEqual(result['builtin_type'], 'unsigned_int')

    def test_unknown(self):
        self.assertIsNone(self.r.resolve('NonexistentType'))

    def test_function_pointer_typedef(self):
        self.assertTrue(self.r.is_function_pointer('ImGuiInputTextCallback'))

    def test_not_function_pointer(self):
        self.assertFalse(self.r.is_function_pointer('ImU32'))

    def test_is_known(self):
        self.assertTrue(self.r.is_known('ImU32'))
        self.assertTrue(self.r.is_known('size_t'))
        self.assertFalse(self.r.is_known('Nonexistent'))


if __name__ == '__main__':
    unittest.main()
