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


class TestStructsImpl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = _run_generate()
        if result is None:
            raise unittest.SkipTest('dcimgui.json not found')
        cls.h, cls.cpp, cls.dts = result

    def test_constructor_defs(self):
        self.assertIn('Napi::FunctionReference Vec2Wrap::constructor;', self.cpp)
        self.assertIn('Napi::FunctionReference IOWrap::constructor;', self.cpp)

    def test_vec2_new_factory(self):
        self.assertIn('Vec2Wrap::New(Napi::Env env, ImVec2 v)', self.cpp)
        self.assertIn('v.x', self.cpp)
        self.assertIn('v.y', self.cpp)

    def test_vec2_uses_value_not_ptr(self):
        self.assertIn('return Napi::Number::New(env, value.x);', self.cpp)
        self.assertIn('value.x = val.As<Napi::Number>().FloatValue();', self.cpp)

    def test_io_wrap_factory(self):
        self.assertIn('IOWrap::Wrap(Napi::Env env, ImGuiIO* raw)', self.cpp)

    def test_borrow_only_throws(self):
        self.assertIn('cannot be constructed directly', self.cpp)

    def test_context_uses_create(self):
        self.assertIn('ImGui_CreateContext(nullptr)', self.cpp)

    def test_init_structs(self):
        self.assertIn('void InitStructs(', self.cpp)
        self.assertIn('Vec2Wrap::Init(', self.cpp)
        self.assertIn('IOWrap::Init(', self.cpp)

    def test_define_class_format(self):
        self.assertIn('DefineClass(env, "Vec2"', self.cpp)
        self.assertIn('InstanceAccessor<', self.cpp)

    def test_dts_vec2_class(self):
        self.assertIn('class Vec2', self.dts)

    def test_dts_io_class(self):
        self.assertIn('class IO', self.dts)

    def test_dts_no_anonymous(self):
        self.assertNotIn('__anonymous', self.dts)

    def test_listclipper_constructable(self):
        self.assertIn('ptr = new ImGuiListClipper{}', self.cpp)

    def test_fontconfig_uses_im_new(self):
        self.assertIn('IM_NEW(ImFontConfig)', self.cpp)


if __name__ == '__main__':
    unittest.main()
