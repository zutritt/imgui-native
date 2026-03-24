from __future__ import annotations

from config import BORROW_ONLY
from config import NEEDS_CPP_CONSTRUCTOR
from core.naming import struct_name as sn
from data.types_builtin import BY_VALUE


def _by_value_ctor_body(cname: str) -> str:
    if cname == 'ImVec2':
        return (
            'if (info.Length() >= 2) {\n'
            '  value.x = info[0].As<Napi::Number>().FloatValue();\n'
            '  value.y = info[1].As<Napi::Number>().FloatValue();\n'
            '} else { value = {}; }'
        )
    if cname == 'ImVec4':
        return (
            'if (info.Length() >= 4) {\n'
            '  value.x = info[0].As<Napi::Number>().FloatValue();\n'
            '  value.y = info[1].As<Napi::Number>().FloatValue();\n'
            '  value.z = info[2].As<Napi::Number>().FloatValue();\n'
            '  value.w = info[3].As<Napi::Number>().FloatValue();\n'
            '} else { value = {}; }'
        )
    if cname == 'ImColor':
        f = 'info[{i}].As<Napi::Number>().FloatValue()'
        return '\n'.join(
            [
                f'value.Value.x = info.Length() > 0 ? {f.format(i=0)} : 0;',
                f'value.Value.y = info.Length() > 1 ? {f.format(i=1)} : 0;',
                f'value.Value.z = info.Length() > 2 ? {f.format(i=2)} : 0;',
                f'value.Value.w = info.Length() > 3 ? {f.format(i=3)} : 1;',
            ]
        )
    return 'value = {};'


def _regular_ctor_body(cname: str, is_owned_struct: bool) -> str:
    js = sn(cname)
    if cname == 'ImGuiContext':
        return (
            'if (info[0].IsExternal()) {\n'
            '  ptr = info[0].As<Napi::External<ImGuiContext>>().Data();\n'
            '  owned = false;\n'
            '} else {\n'
            '  ptr = ImGui_CreateContext(nullptr);\n'
            '  owned = true;\n'
            '}'
        )
    ext_block = f'ptr = info[0].As<Napi::External<{cname}>>().Data();\n'
    if is_owned_struct:
        ext_block += 'owned = info.Length() > 1 && info[1].As<Napi::Boolean>().Value();'
    else:
        ext_block += 'owned = false;'
    if cname in BORROW_ONLY:
        err = f'Napi::TypeError::New(info.Env(), "{js} cannot be constructed directly")'
        return (
            f'if (info[0].IsExternal()) {{\n  {ext_block}\n}} else {{\n'
            f'  {err}.ThrowAsJavaScriptException();\n}}'
        )
    if cname in NEEDS_CPP_CONSTRUCTOR:
        new_block = f'ptr = IM_NEW({cname});\nowned = true;'
    else:
        new_block = f'ptr = new {cname}{{}};\nowned = true;'
    return f'if (info[0].IsExternal()) {{\n  {ext_block}\n}} else {{\n  {new_block}\n}}'


def _dtor_body(cname: str, registry) -> str:
    if cname in BY_VALUE:
        return ''
    if cname == 'ImGuiContext':
        return 'if (owned) ImGui_DestroyContext(ptr);'
    if cname in NEEDS_CPP_CONSTRUCTOR:
        return 'if (owned) IM_DELETE(ptr);'
    if cname in registry.owned_structs:
        delete_fn = registry.owned_structs[cname]
        return f'if (owned) {delete_fn}(reinterpret_cast<::{cname}*>(ptr));'
    if cname in BORROW_ONLY:
        return ''
    return 'if (owned) delete ptr;'


def _by_value_new_body(cname: str) -> str:
    if cname == 'ImVec2':
        return 'return constructor.New({Napi::Number::New(env, v.x), Napi::Number::New(env, v.y)});'
    if cname == 'ImVec4':
        return (
            'return constructor.New({\n'
            '  Napi::Number::New(env, v.x), Napi::Number::New(env, v.y),\n'
            '  Napi::Number::New(env, v.z), Napi::Number::New(env, v.w)});'
        )
    if cname == 'ImColor':
        return (
            'return constructor.New({\n'
            '  Napi::Number::New(env, v.Value.x), Napi::Number::New(env, v.Value.y),\n'
            '  Napi::Number::New(env, v.Value.z), Napi::Number::New(env, v.Value.w)});'
        )
    return 'return constructor.New({});'
