import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from data.loader import load_bindings
from data.registry import Registry
from generators.functions import generate_functions
from generators.structs import generate_structs


def _load_registry():
    if not BINDINGS_FILE.exists():
        return None
    return Registry(load_bindings(BINDINGS_FILE))


class TestFunctionsGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = _load_registry()
        if cls.reg is None:
            raise unittest.SkipTest('dcimgui.json not found')
        GEN_NAPI.mkdir(parents=True, exist_ok=True)
        GEN_DTS.mkdir(parents=True, exist_ok=True)
        generate_structs(cls.reg)
        cls.skip_count = generate_functions(cls.reg)
        cls.cpp = (GEN_NAPI / 'functions.cpp').read_text()
        cls.dts = (GEN_DTS / 'functions.d.ts').read_text()

    def test_cpp_has_init_functions(self):
        self.assertIn('void InitFunctions(', self.cpp)

    def test_cpp_has_begin(self):
        self.assertIn('_begin(', self.cpp)
        self.assertIn('ImGui_Begin(', self.cpp)

    def test_cpp_begin_has_string_extract(self):
        self.assertIn('Utf8Value()', self.cpp)

    def test_cpp_begin_has_bool_ref(self):
        self.assertIn('BoolRef::Unwrap', self.cpp)

    def test_cpp_begin_returns_bool(self):
        self.assertIn('Napi::Boolean::New(env, _r)', self.cpp)

    def test_cpp_has_end(self):
        self.assertIn('_end(', self.cpp)
        self.assertIn('ImGui_End(', self.cpp)

    def test_cpp_color_convert_out_params(self):
        self.assertIn('_colorConvertRGBtoHSV', self.cpp)
        self.assertIn('float _out_h = 0;', self.cpp)
        self.assertIn('_obj.Set("out_h"', self.cpp)

    def test_cpp_varargs_fmt(self):
        self.assertIn('"%s"', self.cpp)

    def test_cpp_exports_set(self):
        self.assertIn('exports.Set("begin"', self.cpp)
        self.assertIn('exports.Set("end"', self.cpp)

    def test_dts_has_begin(self):
        self.assertIn('function begin(', self.dts)

    def test_dts_has_end(self):
        self.assertIn('function end(', self.dts)

    def test_dts_begin_signature(self):
        self.assertIn('name: string', self.dts)

    def test_skip_count_reasonable(self):
        total = len(self.reg.free_functions)
        self.assertGreater(total, 0)
        self.assertLess(self.skip_count, total)

    def test_create_context(self):
        self.assertIn('_createContext', self.cpp)
        self.assertIn('ImGui_CreateContext', self.cpp)
        self.assertIn('ContextWrap::Wrap', self.cpp)

    def test_get_io(self):
        self.assertIn('IOWrap::Wrap', self.cpp)


if __name__ == '__main__':
    unittest.main()
