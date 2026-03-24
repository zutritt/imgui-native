from __future__ import annotations

from config import OWNED_RETURNS
from core.naming import struct_name as sn
from data.types_builtin import _WRAP_CLS
from data.types_builtin import BY_VALUE
from data.types_builtin import ts_builtin
from data.types_builtin import wrap_builtin
from data.types_defs import ParamInfo
from data.types_defs import RetInfo
from data.types_params import _param_array
from data.types_params import _param_builtin
from data.types_params import _param_user
from data.types_pointer import _param_pointer


def param_info(arg: dict, next_arg: dict | None, idx: int, registry) -> ParamInfo | None:
    if arg.get('is_varargs'):
        return None
    name = arg.get('name', f'arg{idx}')
    desc = arg['type']['description']
    kind = desc['kind']
    default_val = arg.get('default_value')

    if kind == 'Builtin':
        return _param_builtin(desc, idx, default_val)
    if kind == 'User':
        return _param_user(desc, name, idx, default_val, registry)
    if kind == 'Pointer':
        return _param_pointer(desc, name, idx, default_val, next_arg, registry)
    if kind == 'Array':
        return _param_array(desc, name, idx)
    return None


def return_info(desc: dict, registry, func_name: str = '') -> RetInfo | None:
    kind = desc['kind']
    if kind == 'Builtin':
        bt = desc.get('builtin_type', '')
        if bt == 'void':
            return None
        w = wrap_builtin(bt, '{val}')
        ts = ts_builtin(bt)
        return RetInfo(wrap=w, ts_type=ts or 'unknown') if w and ts else None
    if kind == 'User':
        uname = desc['name']
        if uname in BY_VALUE:
            cls = _WRAP_CLS[uname]
            return RetInfo(wrap=f'{cls}::New(env, {{val}})', ts_type=cls.replace('Wrap', ''))
        r = registry.typedefs.resolve(uname)
        if r and r['kind'] == 'Builtin':
            w = wrap_builtin(r['builtin_type'], '{val}')
            ts = ts_builtin(r['builtin_type'])
            return RetInfo(wrap=w, ts_type=ts or 'unknown') if w and ts else None
        wrap_cls = f'{sn(uname)}Wrap'
        return RetInfo(wrap=f'{wrap_cls}::Wrap(env, {{val}})', ts_type=sn(uname))
    if kind == 'Pointer':
        inner = desc['inner_type']
        ik = inner['kind']
        if ik == 'Builtin':
            ibt = inner.get('builtin_type', '')
            if ibt == 'char':
                return RetInfo(
                    wrap='({val} ? Napi::String::New(env, {val}) : env.Null())',
                    ts_type='string | null',
                )
            return None
        if ik == 'User':
            uname = inner['name']
            if uname in BY_VALUE:
                cls = _WRAP_CLS[uname]
                return RetInfo(wrap=f'{cls}::Wrap(env, {{val}})', ts_type=cls.replace('Wrap', ''))
            wrap_cls = f'{sn(uname)}Wrap'
            if func_name in OWNED_RETURNS:
                return RetInfo(wrap=f'{wrap_cls}::WrapOwned(env, {{val}})', ts_type=sn(uname))
            return RetInfo(wrap=f'{wrap_cls}::Wrap(env, {{val}})', ts_type=sn(uname))
        return None
    return None
