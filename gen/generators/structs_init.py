from __future__ import annotations

from core.naming import method_name
from core.naming import struct_name as sn
from core.naming import to_camel
from data.types_field import field_getter
from data.types_field import field_setter


def build_define_accessors(cname: str, fields: list[dict], registry) -> list[str]:
    entries = []
    wrap = f'{sn(cname)}Wrap'
    for f in fields:
        fname = f['name']
        if fname.startswith('_') or f.get('is_internal'):
            continue
        if not field_getter(f, registry):
            continue
        js_name = to_camel(fname)
        if field_setter(f, registry):
            entries.append(
                f'  InstanceAccessor<&{wrap}::Get{fname}, &{wrap}::Set{fname}>("{js_name}"),'
            )
        else:
            entries.append(f'  InstanceAccessor<&{wrap}::Get{fname}>("{js_name}"),')
    return entries


def build_define_methods(cname: str, registry) -> list[str]:
    entries = []
    seen: set[str] = set()
    wrap = f'{sn(cname)}Wrap'
    for m in registry.methods_for(cname):
        if m.get('is_internal') or m.get('is_manual_helper') or m.get('is_imstr_helper'):
            continue
        js = method_name(m['name'], cname + '_', registry.has_helper(m['name']))
        if js in seen:
            continue
        seen.add(js)
        mfn = to_camel(js[0].upper() + js[1:]) + 'Method'
        is_static = m.get('is_static', False)
        if is_static:
            entries.append(f'  StaticMethod<&{wrap}::{mfn}>("{js}"),')
        else:
            entries.append(f'  InstanceMethod<&{wrap}::{mfn}>("{js}"),')
    return entries


def struct_init_body(s: dict, registry) -> str:
    cname = s['name']
    js = sn(cname)
    fields = s.get('fields', [])
    acc = build_define_accessors(cname, fields, registry)
    meth = build_define_methods(cname, registry)
    entries_str = '\n'.join(acc + meth)
    body = f'auto fn = DefineClass(env, "{js}", {{\n{entries_str}\n}});\n'
    body += 'constructor = Napi::Persistent(fn);\n'
    body += 'constructor.SuppressDestruct();\n'
    body += f'exports.Set("{js}", fn);\n'
    body += 'return exports;'
    return body
