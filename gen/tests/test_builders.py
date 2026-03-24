import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from builders.cpp import CppFile
from builders.cpp import CppObject
from builders.cpp import CppScope
from builders.dts import DtsNamespace
from builders.dts import DtsObject


class TestCppFile(unittest.TestCase):
    def test_include_and_function(self):
        f = CppFile()
        f.include('napi.h')
        f.blank()
        f.function('void Init()', 'return;')
        out = f.render()
        self.assertIn('#include <napi.h>', out)
        self.assertIn('void Init()\n{\n  return;\n}', out)

    def test_raw(self):
        f = CppFile()
        f.raw('// hello')
        self.assertEqual(f.render(), '// hello')


class TestCppObject(unittest.TestCase):
    def test_set(self):
        obj = CppObject('o')
        obj.set('key', 'val')
        self.assertEqual(obj.render(), 'o.Set("key", val);')


class TestCppScope(unittest.TestCase):
    def test_stmt(self):
        s = CppScope()
        s.stmt('int x = 1')
        self.assertEqual(s.render(), 'int x = 1;')

    def test_raw(self):
        s = CppScope()
        s.raw('x.Do();')
        self.assertEqual(s.render(), 'x.Do();')

    def test_blank(self):
        s = CppScope()
        s.stmt('a')
        s.blank()
        s.stmt('b')
        self.assertEqual(s.render(), 'a;\n\nb;')


class TestDtsObject(unittest.TestCase):
    def test_readonly_field(self):
        obj = DtsObject('Foo')
        obj.field('bar', 'number')
        out = obj.render()
        self.assertIn('readonly bar: number;', out)

    def test_writable_field(self):
        obj = DtsObject('Foo')
        obj.field('bar', 'number', readonly=False)
        out = obj.render()
        self.assertIn('bar: number;', out)
        self.assertNotIn('readonly bar', out)


class TestDtsNamespace(unittest.TestCase):
    def test_renders_declare(self):
        ns = DtsNamespace('enums')
        ns.member('readonly X: { readonly A: 1; };')
        out = ns.render()
        self.assertTrue(out.startswith('declare const enums:'))
        self.assertIn('readonly X:', out)


if __name__ == '__main__':
    unittest.main()
