from __future__ import annotations

from core.naming import struct_name as sn
from data.types_builtin import _WRAP_CLS
from data.types_builtin import BY_VALUE
from data.types_builtin import ts_builtin
from data.types_builtin import wrap_builtin
from data.types_field_helpers import _array_getter
from data.types_field_helpers import _imvec_getter
from data.types_field_set import field_setter


def field_getter(field: dict, registry) -> tuple[str, str] | None:
    name = field['name']
    if name.startswith('_') or field.get('is_internal'):
        return None
    desc = field['type']['description']
    kind = desc['kind']
    if field.get('is_array', False):
        bounds = desc.get('bounds', '')
        bv = registry.resolve_array_bound(bounds) if bounds else None
        return _array_getter(name, kind, desc, bv)
    if kind == 'Builtin':
        bt = desc.get('builtin_type', '')
        if bt == 'void':
            return None
        w = wrap_builtin(bt, f'ptr->{name}')
        return (f'return {w};', ts_builtin(bt) or 'unknown') if w else None
    if kind == 'User':
        uname = desc['name']
        if uname.startswith('ImVector_'):
            return _imvec_getter(name, uname)
        if uname in BY_VALUE:
            cls = _WRAP_CLS[uname]
            return f'return {cls}::New(info.Env(), ptr->{name});', cls.replace('Wrap', '')
        if registry.typedefs.is_function_pointer(uname):
            return None
        r = registry.typedefs.resolve(uname)
        if r and r['kind'] == 'Builtin':
            w = wrap_builtin(r['builtin_type'], f'ptr->{name}')
            return (f'return {w};', ts_builtin(r['builtin_type']) or 'unknown') if w else None
        wc = f'{sn(uname)}Wrap'
        return (
            f'if (!ptr->{name}) return info.Env().Null();\n'
            f'return {wc}::Wrap(info.Env(), ptr->{name});'
        ), f'{sn(uname)} | null'
    if kind == 'Pointer':
        inner = desc['inner_type']
        ik = inner['kind']
        if ik == 'Builtin' and inner.get('builtin_type') == 'char':
            return (
                f'if (!ptr->{name}) return info.Env().Null();\n'
                f'return Napi::String::New(info.Env(), ptr->{name});'
            ), 'string | null'
        if ik == 'User':
            uname = inner['name']
            if uname in BY_VALUE:
                cls = _WRAP_CLS[uname]
                return (
                    f'if (!ptr->{name}) return info.Env().Null();\n'
                    f'return {cls}::Wrap(info.Env(), ptr->{name});'
                ), f'{cls.replace("Wrap", "")} | null'
            wc = f'{sn(uname)}Wrap'
            return (
                f'if (!ptr->{name}) return info.Env().Null();\n'
                f'return {wc}::Wrap(info.Env(), ptr->{name});'
            ), f'{sn(uname)} | null'
    return None


__all__ = ['field_getter', 'field_setter']
