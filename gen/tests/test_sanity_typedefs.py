import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BINDINGS_FILE
from data.loader import load_bindings
from data.registry import Registry
from data.typedefs import FUNCTION_POINTER_TYPEDEFS


def _load_registry():
    if not BINDINGS_FILE.exists():
        return None
    return Registry(load_bindings(BINDINGS_FILE))


class TestSanityTypedefs(unittest.TestCase):
    """Typedef resolution sanity checks."""

    @classmethod
    def setUpClass(cls):
        cls.reg = _load_registry()
        if cls.reg is None:
            raise unittest.SkipTest('dcimgui.json not found')

    def test_function_pointer_typedefs_resolvable(self):
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
