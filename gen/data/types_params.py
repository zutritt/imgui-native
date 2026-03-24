from __future__ import annotations

from core.naming import struct_name as sn
from data.types_builtin import _C_TYPE
from data.types_builtin import _EXTRACT_FN
from data.types_builtin import _NUM
from data.types_builtin import BY_VALUE
from data.types_builtin import extract_builtin
from data.types_builtin import ts_builtin
from data.types_defs import ParamInfo


def _param_builtin(desc: dict, idx: int, default_val) -> ParamInfo | None:
    bt = desc.get('builtin_type', '')
    if bt == 'void':
        return None
    ext = extract_builtin(bt, idx)
    if ext is None:
        return None
    pre, c_expr = ext
    ts = ts_builtin(bt)
    if default_val and default_val != 'NULL':
        napi, method, _ = _NUM[bt]
        c_type = _C_TYPE.get(bt, bt)
        c_expr = (
            f'info[{idx}].IsUndefined() ? ({c_type}){default_val}'
            f' : info[{idx}].As<{napi}>().{method}'
        )
    return ParamInfo(decls=pre, c_arg=c_expr, ts_type=ts or 'unknown')


def _param_user(desc: dict, name: str, idx: int, default_val, registry) -> ParamInfo | None:
    uname = desc['name']
    if registry.typedefs.is_function_pointer(uname):
        return None
    if uname in BY_VALUE:
        fn = _EXTRACT_FN[uname]
        return ParamInfo(c_arg=f'{fn}(info[{idx}])', ts_type=sn(uname))
    r = registry.typedefs.resolve(uname)
    if r and r['kind'] == 'Builtin':
        bt = r['builtin_type']
        ext = extract_builtin(bt, idx)
        if ext is None:
            return None
        pre, c_expr = ext
        ts = ts_builtin(bt)
        if default_val and default_val != 'NULL':
            c_expr = f'info[{idx}].IsUndefined() ? ({uname}){default_val} : ({uname}){c_expr}'
        else:
            c_expr = f'({uname}){c_expr}'
        return ParamInfo(decls=pre, c_arg=c_expr, ts_type=ts or 'number')
    wrap_cls = f'{sn(uname)}Wrap'
    nullable = default_val == 'NULL'
    if nullable:
        var = f'_{name}'
        pre = [
            f'{uname}* {var} = nullptr;',
            f'if (!info[{idx}].IsNull() && !info[{idx}].IsUndefined())',
            f'  {var} = {wrap_cls}::Unwrap(info[{idx}].As<Napi::Object>())->ptr;',
        ]
        return ParamInfo(decls=pre, c_arg=var, ts_type=f'{sn(uname)} | null')
    return ParamInfo(
        c_arg=f'{wrap_cls}::Unwrap(info[{idx}].As<Napi::Object>())->ptr',
        ts_type=sn(uname),
    )


def _param_array(desc: dict, name: str, idx: int) -> ParamInfo | None:
    inner = desc.get('inner_type', {})
    ibt = inner.get('builtin_type', '') if inner.get('kind') == 'Builtin' else ''
    if ibt == 'float':
        var = f'_{name}_a'
        pre = [
            f'Napi::Float32Array {var} = info[{idx}].As<Napi::Float32Array>();',
            f'float* {name} = reinterpret_cast<float*>({var}.Data());',
        ]
        return ParamInfo(decls=pre, c_arg=name, ts_type='Float32Array')
    if ibt in ('int', 'unsigned_int', 'short', 'unsigned_short'):
        var = f'_{name}_a'
        pre = [
            f'Napi::Int32Array {var} = info[{idx}].As<Napi::Int32Array>();',
            f'int* {name} = reinterpret_cast<int*>({var}.Data());',
        ]
        return ParamInfo(decls=pre, c_arg=name, ts_type='Int32Array')
    return None
