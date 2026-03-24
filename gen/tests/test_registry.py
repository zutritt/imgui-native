import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from config import BINDINGS_FILE
from data.loader import load_bindings
from data.registry import Registry


def _load_registry():
    if not BINDINGS_FILE.exists():
        return None
    return Registry(load_bindings(BINDINGS_FILE))


class TestRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = _load_registry()
        if cls.reg is None:
            raise unittest.SkipTest('dcimgui.json not found')

    def test_struct_classification_complete(self):
        total = (
            len(self.reg.by_value_structs)
            + len(self.reg.opaque_structs)
            + len(self.reg.imvector_structs)
            + len(self.reg.regular_structs)
        )
        self.assertEqual(total, len(self.reg.all_structs))

    def test_function_classification_complete(self):
        total = (
            len(self.reg.helpers)
            + len(self.reg.free_functions)
            + len(self.reg.methods)
            + len(self.reg.skipped_functions)
        )
        self.assertEqual(total, len(self.reg.all_functions))

    def test_by_value_names(self):
        names = {s['name'] for s in self.reg.by_value_structs}
        self.assertEqual(names, {'ImVec2', 'ImVec4', 'ImColor', 'ImTextureRef'})

    def test_opaque_names(self):
        names = {s['name'] for s in self.reg.opaque_structs}
        expected = {
            'ImGuiContext',
            'ImDrawListSharedData',
            'ImFontAtlasBuilder',
            'ImFontLoader',
        }
        self.assertEqual(names, expected)

    def test_imvector_all_have_three_fields(self):
        for s in self.reg.imvector_structs:
            field_names = {f['name'] for f in s.get('fields', [])}
            self.assertIn('Size', field_names, f'{s["name"]} missing Size')
            self.assertIn('Capacity', field_names, f'{s["name"]} missing Capacity')
            self.assertIn('Data', field_names, f'{s["name"]} missing Data')

    def test_has_helper_detection(self):
        self.assertTrue(self.reg.has_helper('ImGui_DragFloatEx'))
        self.assertFalse(self.reg.has_helper('ImGui_Begin'))
        self.assertFalse(self.reg.has_helper('ImGui_TreeNodeEx'))

    def test_all_helpers_have_ex_counterpart(self):
        all_names = {f['name'] for f in self.reg.all_functions}
        for h in self.reg.helpers:
            ex_name = h['name'] + 'Ex'
            self.assertIn(ex_name, all_names, f'Helper {h["name"]} has no Ex counterpart')

    def test_enum_counts_populated(self):
        self.assertIn('ImGuiCol_COUNT', self.reg.enum_counts)
        self.assertGreater(self.reg.enum_counts['ImGuiCol_COUNT'], 0)

    def test_resolve_array_bound_numeric(self):
        self.assertEqual(self.reg.resolve_array_bound('5'), 5)

    def test_resolve_array_bound_symbolic(self):
        result = self.reg.resolve_array_bound('ImGuiCol_COUNT')
        self.assertIsNotNone(result)
        self.assertGreater(result, 0)


if __name__ == '__main__':
    unittest.main()
