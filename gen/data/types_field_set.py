from __future__ import annotations

from data.types_builtin import _C_TYPE
from data.types_builtin import _EXTRACT_FN
from data.types_builtin import _NUM
from data.types_builtin import BY_VALUE


def field_setter(field: dict, registry) -> str | None:
    name = field['name']
    if name.startswith('_') or field.get('is_internal'):
        return None
    desc = field['type']['description']
    kind = desc['kind']
    is_arr = field.get('is_array', False)

    if is_arr:
        bounds = desc.get('bounds', '')
        bv = registry.resolve_array_bound(bounds) if bounds else None
        if kind == 'Array':
            inner = desc.get('inner_type', {})
            ik = inner.get('kind', '')
            bt = inner.get('builtin_type', '') if ik == 'Builtin' else ''
            uname = inner.get('name', '') if ik == 'User' else ''
        else:
            bt = desc.get('builtin_type', '') if kind == 'Builtin' else ''
            uname = desc.get('name', '') if kind == 'User' else ''
        if bt == 'float' and bv:
            return f'memcpy(ptr->{name}, val.As<Napi::Float32Array>().Data(), {bv}*sizeof(float));'
        if bt in ('int', 'unsigned_int') and bv:
            return f'memcpy(ptr->{name}, val.As<Napi::Int32Array>().Data(), {bv}*sizeof(int));'
        if uname == 'ImVec4' and bv:
            return (
                f'memcpy(ptr->{name}, val.As<Napi::Float32Array>().Data(), {bv}*4*sizeof(float));'
            )
        return None

    if kind == 'Builtin':
        bt = desc.get('builtin_type', '')
        if bt == 'void':
            return None
        info = _NUM.get(bt)
        if not info:
            return None
        napi, method, _ = info
        if 'BigInt' in napi:
            signed = bt == 'long_long'
            m = 'Int64Value' if signed else 'Uint64Value'
            ct = _C_TYPE.get(bt, bt)
            return f'bool _l; ptr->{name} = ({ct})val.As<{napi}>().{m}(&_l);'
        return f'ptr->{name} = val.As<{napi}>().{method};'

    if kind == 'User':
        uname = desc['name']
        if uname.startswith('ImVector_'):
            return None
        if uname in BY_VALUE:
            fn = _EXTRACT_FN[uname]
            return f'ptr->{name} = {fn}(val);'
        if registry.typedefs.is_function_pointer(uname):
            return None
        r = registry.typedefs.resolve(uname)
        if r and r['kind'] == 'Builtin':
            bt = r['builtin_type']
            info = _NUM.get(bt)
            if not info:
                return None
            napi, method, _ = info
            return f'ptr->{name} = ({uname})val.As<{napi}>().{method};'
    return None
