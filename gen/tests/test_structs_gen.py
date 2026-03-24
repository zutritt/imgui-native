import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from data.loader import load_bindings
from data.registry import Registry
from generators.structs import generate_structs


def _run_generate():
    if not BINDINGS_FILE.exists():
        return None
    reg = Registry(load_bindings(BINDINGS_FILE))
    GEN_NAPI.mkdir(parents=True, exist_ok=True)
    GEN_DTS.mkdir(parents=True, exist_ok=True)
    generate_structs(reg)
    h = (GEN_NAPI / 'structs.h').read_text()
    cpp = (GEN_NAPI / 'structs.cpp').read_text()
    dts = (GEN_DTS / 'structs.d.ts').read_text()
    return h, cpp, dts


class TestStructsHeader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = _run_generate()
        if result is None:
            raise unittest.SkipTest('dcimgui.json not found')
        cls.h, cls.cpp, cls.dts = result

    def test_pragma_once(self):
        self.assertIn('#pragma once', self.h)

    def test_init_structs_decl(self):
        self.assertIn('void InitStructs(', self.h)

    def test_vec2_wrap(self):
        self.assertIn('class Vec2Wrap', self.h)
        self.assertIn('ImVec2 value;', self.h)
        self.assertIn('static Napi::Value New(Napi::Env env, ImVec2 v);', self.h)

    def test_io_wrap(self):
        self.assertIn('class IOWrap', self.h)
        self.assertIn('ImGuiIO* ptr; bool owned;', self.h)
        self.assertIn('static Napi::Value Wrap(Napi::Env env, ImGuiIO* raw);', self.h)

    def test_context_wrap(self):
        self.assertIn('class ContextWrap', self.h)
        self.assertIn('ImGuiContext* ptr; bool owned;', self.h)

    def test_no_anonymous_types(self):
        self.assertNotIn('__anonymous', self.h)

    def test_no_imvector_structs(self):
        self.assertNotIn('ImVector_', self.h)


if __name__ == '__main__':
    unittest.main()
