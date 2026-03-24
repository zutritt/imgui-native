import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from core.naming import enum_element
from core.naming import enum_name
from core.naming import free_fn_name
from core.naming import method_name
from core.naming import strip_imgui_prefix


class TestStripImguiPrefix(unittest.TestCase):
    def test_imgui_prefix(self):
        self.assertEqual(strip_imgui_prefix('ImGuiIO'), 'IO')
        self.assertEqual(strip_imgui_prefix('ImGuiStyle'), 'Style')

    def test_im_prefix(self):
        self.assertEqual(strip_imgui_prefix('ImVec2'), 'Vec2')
        self.assertEqual(strip_imgui_prefix('ImDrawList'), 'DrawList')
        self.assertEqual(strip_imgui_prefix('ImColor'), 'Color')

    def test_no_prefix(self):
        self.assertEqual(strip_imgui_prefix('Image'), 'Image')
        self.assertEqual(strip_imgui_prefix('Import'), 'Import')

    def test_short_im(self):
        self.assertEqual(strip_imgui_prefix('Im'), 'Im')


class TestMethodName(unittest.TestCase):
    def test_strip_class_and_camel(self):
        self.assertEqual(method_name('ImDrawList_AddLine', 'ImDrawList_', False), 'addLine')

    def test_strip_ex(self):
        self.assertEqual(method_name('ImDrawList_AddLineEx', 'ImDrawList_', True), 'addLine')

    def test_no_ex_strip_when_no_helper(self):
        self.assertEqual(method_name('ImDrawList_AddLineEx', 'ImDrawList_', False), 'addLineEx')


class TestFreeFnName(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(free_fn_name('ImGui_GetWindowPos', False), 'getWindowPos')
        self.assertEqual(free_fn_name('ImGui_Begin', False), 'begin')

    def test_strip_ex(self):
        self.assertEqual(free_fn_name('ImGui_DragFloatEx', True), 'dragFloat')

    def test_no_ex_strip(self):
        self.assertEqual(free_fn_name('ImGui_TreeNodeEx', False), 'treeNodeEx')


class TestEnumNames(unittest.TestCase):
    def test_enum_name(self):
        self.assertEqual(enum_name('ImGuiWindowFlags_'), 'WindowFlags')
        self.assertEqual(enum_name('ImDrawFlags_'), 'DrawFlags')

    def test_element_name(self):
        self.assertEqual(enum_element('WindowFlags_NoTitleBar', 'WindowFlags'), 'NoTitleBar')
        self.assertEqual(enum_element('Standalone', 'WindowFlags'), 'Standalone')


if __name__ == '__main__':
    unittest.main()
