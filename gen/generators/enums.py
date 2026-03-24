from builders.cpp import CppFile
from builders.cpp import CppObject
from builders.cpp import CppScope
from builders.dts import DtsNamespace
from builders.dts import DtsObject
from config import GEN_DTS
from config import GEN_NAPI
from core.naming import enum_element
from core.naming import enum_name


def _should_skip_element(el: dict) -> bool:
    return el.get('is_count') or el.get('is_internal') is True or el.get('is_internal') is None


def _generate_enum_cpp(name: str, elements: list[dict], scope: CppScope):
    scope.stmt(f'Napi::Object _{name} = Napi::Object::New(env)')
    obj = CppObject(f'_{name}')
    for el in elements:
        el_name = enum_element(el['name'], name)
        obj.set(el_name, f'Napi::Number::New(env, {el["value"]})')
    scope.raw(obj.render())
    scope.stmt(f'freeze.Call({{_{name}}})')
    scope.stmt(f'enums.Set("{name}", _{name})')


def _generate_enum_dts(name: str, elements: list[dict], ns: DtsNamespace):
    obj = DtsObject(name)
    for el in elements:
        obj.field(enum_element(el['name'], name), str(el['value']))
    ns.member(obj.render())


def generate_enums(registry):
    scope = CppScope()
    ns = DtsNamespace('enums')

    for enum in registry.enums:
        name = enum_name(enum['name'])
        elements = [el for el in enum['elements'] if not _should_skip_element(el)]
        _generate_enum_cpp(name, elements, scope)
        scope.blank()
        _generate_enum_dts(name, elements, ns)
        ns.blank()

    cpp = CppFile()
    cpp.include('napi.h')
    cpp.blank()
    cpp.function(
        'void InitEnums(Napi::Env env, Napi::Object exports)',
        'Napi::Object enums = Napi::Object::New(env);\n'
        'Napi::Function freeze = env.Global().Get("Object").As<Napi::Object>()'
        '.Get("freeze").As<Napi::Function>();\n\n' + scope.render() + '\n'
        'freeze.Call({enums});\n'
        'exports.Set("enums", enums);',
    )

    (GEN_NAPI / 'enums.cpp').write_text(cpp.render())
    (GEN_DTS / 'enums.d.ts').write_text(ns.render())
