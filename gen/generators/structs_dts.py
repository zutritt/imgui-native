from __future__ import annotations

from builders.dts import DtsClass
from config import BORROW_ONLY
from core.naming import method_name
from core.naming import struct_name as sn
from core.naming import to_camel
from data.types import return_info
from data.types_builtin import BY_VALUE
from data.types_field import field_getter
from data.types_field import field_setter
from generators.call import build_call_body
from generators.call import build_dts_args


def dts_class(s: dict, registry) -> str:
    cname = s['name']
    js = sn(cname)
    cls = DtsClass(js)

    is_bv = cname in BY_VALUE
    if is_bv:
        if cname == 'ImVec2':
            cls.member('constructor(x: number, y: number);')
        elif cname == 'ImVec4':
            cls.member('constructor(x: number, y: number, z: number, w: number);')
        elif cname == 'ImColor':
            cls.member('constructor(r?: number, g?: number, b?: number, a?: number);')
        else:
            cls.member('constructor();')
    elif cname not in BORROW_ONLY and cname != 'ImGuiContext':
        cls.member('constructor();')

    for f in s.get('fields', []):
        fname = f['name']
        if fname.startswith('_') or f.get('is_internal'):
            continue
        g = field_getter(f, registry)
        if not g:
            continue
        _, ts = g
        sv = field_setter(f, registry)
        ro = '' if sv else 'readonly '
        cls.member(f'{ro}{to_camel(fname)}: {ts};')

    seen: set[str] = set()
    for m in registry.methods_for(cname):
        if m.get('is_internal') or m.get('is_manual_helper') or m.get('is_imstr_helper'):
            continue
        mjs = method_name(m['name'], cname + '_', registry.has_helper(m['name']))
        if mjs in seen:
            continue
        seen.add(mjs)
        body = build_call_body(m, registry, c_self=None if m.get('is_static') else 'ptr')
        if body is None:
            continue
        ri = return_info(m['return_type']['description'], registry, m['name'])
        ts_ret = ri.ts_type if ri else 'void'
        args_str = build_dts_args(m, registry)
        prefix = 'static ' if m.get('is_static') else ''
        cls.member(f'{prefix}{mjs}({args_str}): {ts_ret};')

    return cls.render()
