from __future__ import annotations

from core.naming import struct_name as sn
from core.text import indent
from data.types_builtin import BY_VALUE
from generators.structs_accessors import accessor_impls
from generators.structs_accessors import method_impls
from generators.structs_ctor import _by_value_ctor_body
from generators.structs_ctor import _by_value_new_body
from generators.structs_ctor import _dtor_body
from generators.structs_ctor import _regular_ctor_body
from generators.structs_init import struct_init_body


def _fn(sig: str, body: str) -> str:
    return f'{sig}\n{{\n{indent(body)}\n}}'


def impl_blocks(s: dict, registry) -> list[str]:
    cname = s['name']
    js = sn(cname)
    wrap = f'{js}Wrap'
    is_bv = cname in BY_VALUE
    is_owned_struct = cname in registry.owned_structs
    blocks = [f'Napi::FunctionReference {wrap}::constructor;']

    if is_bv:
        new_sig = f'Napi::Value {wrap}::New(Napi::Env env, {cname} v)'
        blocks.append(_fn(new_sig, _by_value_new_body(cname)))
    else:
        wrap_body = (
            f'auto ext = Napi::External<{cname}>::New(env, raw);\nreturn constructor.New({{ext}});'
        )
        blocks.append(_fn(f'Napi::Value {wrap}::Wrap(Napi::Env env, {cname}* raw)', wrap_body))
        if is_owned_struct:
            owned_body = (
                f'auto ext = Napi::External<{cname}>::New(env, raw);\n'
                f'auto owned = Napi::Boolean::New(env, true);\n'
                f'return constructor.New({{ext, owned}});'
            )
            owned_sig = f'Napi::Value {wrap}::WrapOwned(Napi::Env env, {cname}* raw)'
            blocks.append(_fn(owned_sig, owned_body))

    ctor_body = _by_value_ctor_body(cname) if is_bv else _regular_ctor_body(cname, is_owned_struct)
    ctor_sig = f'{wrap}::{wrap}(const Napi::CallbackInfo& info) : Napi::ObjectWrap<{wrap}>(info)'
    blocks.append(_fn(ctor_sig, ctor_body))

    dtor_body = _dtor_body(cname, registry)
    blocks.append(_fn(f'{wrap}::~{wrap}()', dtor_body))

    init_sig = f'Napi::Object {wrap}::Init(Napi::Env env, Napi::Object exports)'
    blocks.append(_fn(init_sig, struct_init_body(s, registry)))

    blocks.extend(accessor_impls(s, registry))
    blocks.extend(method_impls(s, registry))
    return blocks
