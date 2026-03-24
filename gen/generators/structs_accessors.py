from __future__ import annotations

from core.naming import method_name
from core.naming import struct_name as sn
from core.naming import to_camel
from core.text import indent
from data.types_builtin import BY_VALUE
from data.types_field import field_getter
from data.types_field import field_setter
from generators.call import build_call_body


def _fn(sig: str, body: str) -> str:
    return f'{sig}\n{{\n{indent(body)}\n}}'


def accessor_impls(s: dict, registry) -> list[str]:
    cname = s['name']
    wrap = f'{sn(cname)}Wrap'
    is_bv = cname in BY_VALUE
    impls = []
    for f in s.get('fields', []):
        fname = f['name']
        if fname.startswith('_') or f.get('is_internal'):
            continue
        g = field_getter(f, registry)
        if not g:
            continue
        body, _ = g
        if is_bv:
            body = body.replace('ptr->', 'value.')
        impls.append(_fn(f'Napi::Value {wrap}::Get{fname}(const Napi::CallbackInfo& info)', body))
        sv = field_setter(f, registry)
        if sv:
            if is_bv:
                sv = sv.replace('ptr->', 'value.')
            set_sig = (
                f'void {wrap}::Set{fname}(const Napi::CallbackInfo& info, const Napi::Value& val)'
            )
            impls.append(_fn(set_sig, sv))
    return impls


def method_impls(s: dict, registry) -> list[str]:
    cname = s['name']
    wrap = f'{sn(cname)}Wrap'
    impls = []
    seen: set[str] = set()
    for m in registry.methods_for(cname):
        if m.get('is_internal') or m.get('is_manual_helper') or m.get('is_imstr_helper'):
            continue
        js = method_name(m['name'], cname + '_', registry.has_helper(m['name']))
        if js in seen:
            continue
        seen.add(js)
        mfn = to_camel(js[0].upper() + js[1:]) + 'Method'
        is_static = m.get('is_static', False)
        body = build_call_body(m, registry, c_self=None if is_static else 'ptr')
        if body is None:
            impls.append(f'// SKIP: {m["name"]} (unsupported param types)')
            continue
        meth_sig = f'Napi::Value {wrap}::{mfn}(const Napi::CallbackInfo& info)'
        impls.append(_fn(meth_sig, body))
    return impls
