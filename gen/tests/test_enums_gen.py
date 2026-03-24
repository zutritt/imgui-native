import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from data.loader import load_bindings
from data.registry import Registry
from generators.enums import generate_enums


def _load_registry():
    if not BINDINGS_FILE.exists():
        return None
    return Registry(load_bindings(BINDINGS_FILE))


class TestEnumsGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = _load_registry()
        if cls.reg is None:
            raise unittest.SkipTest('dcimgui.json not found')
        GEN_NAPI.mkdir(parents=True, exist_ok=True)
        GEN_DTS.mkdir(parents=True, exist_ok=True)
        generate_enums(cls.reg)
        cls.cpp = (GEN_NAPI / 'enums.cpp').read_text()
        cls.dts = (GEN_DTS / 'enums.d.ts').read_text()

    def test_cpp_has_init_function(self):
        self.assertIn('void InitEnums(', self.cpp)

    def test_cpp_has_napi_include(self):
        self.assertIn('#include <napi.h>', self.cpp)

    def test_cpp_has_freeze(self):
        self.assertIn('freeze.Call', self.cpp)

    def test_cpp_has_window_flags(self):
        self.assertIn('WindowFlags', self.cpp)
        self.assertIn('NoTitleBar', self.cpp)

    def test_dts_is_declare_const(self):
        self.assertTrue(self.dts.startswith('declare const enums:'))

    def test_dts_has_window_flags(self):
        self.assertIn('WindowFlags', self.dts)
        self.assertIn('NoTitleBar', self.dts)

    def test_dts_has_readonly(self):
        self.assertIn('readonly', self.dts)

    def test_no_count_elements(self):
        self.assertNotIn('_COUNT', self.cpp)
        self.assertNotIn('_COUNT', self.dts)


if __name__ == '__main__':
    unittest.main()
