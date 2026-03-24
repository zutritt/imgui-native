import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from config import BINDINGS_FILE
from config import NEEDS_CPP_CONSTRUCTOR
from config import OWNED_RETURNS
from data.loader import load_bindings
from data.registry import Registry


def _load_registry():
    if not BINDINGS_FILE.exists():
        return None
    return Registry(load_bindings(BINDINGS_FILE))


class TestSanityChecks(unittest.TestCase):
    """Assumption checks that must hold for the generator to produce correct output.
    These fail early when imgui is updated and assumptions break."""

    @classmethod
    def setUpClass(cls):
        cls.reg = _load_registry()
        if cls.reg is None:
            raise unittest.SkipTest('dcimgui.json not found')

    def test_exactly_4_by_value_structs(self):
        self.assertEqual(len(self.reg.by_value_structs), 4)

    def test_exactly_4_opaque_structs(self):
        self.assertEqual(len(self.reg.opaque_structs), 4)

    def test_imvector_count_is_26(self):
        self.assertEqual(len(self.reg.imvector_structs), 26)

    def test_no_heap_constructor_wrappers(self):
        # ImTextureData_Create is an in-place initializer, not a heap allocator
        KNOWN_CREATE = {'ImGui_CreateContext', 'ImTextureData_Create'}
        for f in self.reg.all_functions:
            name = f['name']
            if name.endswith('_Create') or name.endswith('_CreateContext'):
                self.assertIn(name, KNOWN_CREATE, f'Unexpected constructor: {name}')

    def test_clone_output_exists(self):
        names = {f['name'] for f in self.reg.all_functions}
        self.assertIn('ImDrawList_CloneOutput', names)

    def test_owned_returns_functions_exist(self):
        names = {f['name'] for f in self.reg.all_functions}
        for fn_name in OWNED_RETURNS:
            self.assertIn(fn_name, names)

    def test_cpp_constructor_structs_exist(self):
        names = {s['name'] for s in self.reg.all_structs}
        for sn in NEEDS_CPP_CONSTRUCTOR:
            self.assertIn(sn, names)

    def test_cpp_constructor_structs_are_not_by_value(self):
        by_value = {s['name'] for s in self.reg.by_value_structs}
        for sn in NEEDS_CPP_CONSTRUCTOR:
            self.assertNotIn(sn, by_value)

    def test_no_duplicate_function_names(self):
        names = [f['name'] for f in self.reg.all_functions]
        self.assertEqual(len(names), len(set(names)))

    def test_all_helpers_are_default_argument_helper(self):
        for h in self.reg.helpers:
            self.assertTrue(h.get('is_default_argument_helper'), h['name'])

    def test_forward_declared_have_no_fields(self):
        for s in self.reg.opaque_structs:
            self.assertEqual(len(s.get('fields', [])), 0, s['name'])

    def test_varargs_functions_exist(self):
        count = 0
        for f in self.reg.all_functions:
            for arg in f.get('arguments', []):
                if arg.get('is_varargs'):
                    count += 1
                    break
        self.assertGreater(count, 10)

    def test_function_pointer_typedefs_resolvable(self):
        from data.typedefs import FUNCTION_POINTER_TYPEDEFS

        for name in FUNCTION_POINTER_TYPEDEFS:
            self.assertTrue(
                self.reg.typedefs.is_function_pointer(name),
                f'{name} not detected as function pointer',
            )

    def test_size_t_resolvable(self):
        result = self.reg.typedefs.resolve('size_t')
        self.assertIsNotNone(result)

    def test_imtextureid_chain_resolves(self):
        result = self.reg.typedefs.resolve('ImTextureID')
        self.assertIsNotNone(result)
        self.assertEqual(result['kind'], 'Builtin')


if __name__ == '__main__':
    unittest.main()
