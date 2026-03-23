from textwrap import indent
from config import GEN_DTS, GEN_NAPI


def generate_enums(bindings):
    cpp_lines = []
    cpp_lines.append('#include <napi.h>')
    cpp_lines.append('')
    cpp_lines.append('void InitEnums(Napi::Env env, Napi::Object exports)')
    cpp_lines.append('{')
    cpp_lines.append('  Napi::Object enums = Napi::Object::New(env);')
    cpp_lines.append('  Napi::Function freeze = env.Global().Get("Object").As<Napi::Object>().Get("freeze").As<Napi::Function>();')
    cpp_lines.append('')

    dts_lines = []
    dts_lines.append('declare const enums: {')

    for enum in bindings['enums']:
        enum_cpp_lines, enum_dts_lines = generate_enum(enum)

        cpp_lines.append(indent(enum_cpp_lines, '  '))
        cpp_lines.append('')

        dts_lines.append(indent(enum_dts_lines, '  '))
        dts_lines.append('')

    cpp_lines.append('  freeze.Call({enums});')
    cpp_lines.append('  exports.Set("enums", enums);')
    cpp_lines.append('}')

    dts_lines.append('};')

    cpp = '\n'.join(cpp_lines)
    dts = '\n'.join(dts_lines)

    with open(GEN_NAPI / 'enums.cpp', 'w') as file:
        file.write(cpp)

    with open(GEN_DTS / 'enums.d.ts', 'w') as file:
        file.write(dts)

def generate_enum(spec):
    name = normalize_name(spec['name'])

    cpp_lines = []
    cpp_lines.append(f'Napi::Object _{name} = Napi::Object::New(env);')

    dts_lines = []
    dts_lines.append(f'readonly {name}: {{')

    for element in spec['elements']:
        if element['is_count'] or element['is_internal'] is True or element['is_internal'] is None:
            continue

        element_name = normalize_name(element['name'], remove_prefix=f"{name}_")

        cpp_lines.append(f'_{name}.Set("{element_name}", Napi::Number::New(env, {element["value"]}));')
        dts_lines.append(f'  readonly {element_name}: {element["value"]};')

    cpp_lines.append(f'freeze.Call({{_{name}}});')
    cpp_lines.append(f'enums.Set("{name}", _{name});')
    dts_lines.append('};')

    return '\n'.join(cpp_lines), '\n'.join(dts_lines)


def normalize_name(name: str, remove_prefix: str | None = None) -> str:
    if name.startswith('ImGui'):
        name = name.removeprefix('ImGui')
    elif name.startswith('Im') and name[2].isupper():
        name = name.removeprefix('Im')

    if name.endswith('_'):
        name = name[:-1]

    if remove_prefix:
        name = name.removeprefix(remove_prefix)

    return name
