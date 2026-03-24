from __future__ import annotations

from core.naming import struct_name as sn
from data.types_builtin import _C_TYPE
from data.types_builtin import _EXTRACT_FN
from data.types_builtin import _MUT_REF
from data.types_builtin import BY_VALUE
from data.types_defs import ParamInfo


def _param_pointer(
    desc: dict, name: str, idx: int, default_val, next_arg, registry
) -> ParamInfo | None:
    inner = desc['inner_type']
    ik = inner['kind']
    sc = inner.get('storage_classes', [])
    is_const = 'const' in sc
    nullable = default_val == 'NULL'
    if ik == 'Builtin':
        return _ptr_builtin(inner, name, idx, nullable, is_const, next_arg)
    if ik == 'User':
        return _ptr_user(inner, name, idx, nullable)
    return None


def _ptr_builtin(
    inner: dict, name: str, idx: int, nullable: bool, is_const: bool, next_arg
) -> ParamInfo | None:
    ibt = inner.get('builtin_type', '')
    if ibt == 'char' and is_const:
        var = f'_{name}_s'
        pre = [f'std::string {var} = info[{idx}].As<Napi::String>().Utf8Value();']
        return ParamInfo(decls=pre, c_arg=f'{var}.c_str()', ts_type='string')
    if ibt == 'char' and not is_const and next_arg:
        nname = next_arg.get('name', '')
        if 'buf_size' in nname or nname == 'buf_size':
            var = f'_{name}_r'
            pre = [f'StringRef* {var} = StringRef::Unwrap(info[{idx}].As<Napi::Object>());']
            return ParamInfo(
                decls=pre,
                c_arg=f'{var}->Data()',
                ts_type='StringRef',
                consumed_next=True,
                size_c_arg=f'{var}->Size()',
            )
    if ibt == 'void':
        return None
    ref_cls = _MUT_REF.get(ibt)
    if ref_cls and not is_const:
        ct = _C_TYPE.get(ibt, ibt)
        if name.startswith('out_'):
            return ParamInfo(is_out=True, c_arg=f'&_{name}', ts_type='number', out_c_type=ct)
        if nullable:
            var = f'_{name}'
            pre = [
                f'{ct}* {var} = nullptr;',
                f'if (!info[{idx}].IsNull() && !info[{idx}].IsUndefined())',
                f'  {var} = {ref_cls}::Unwrap(info[{idx}].As<Napi::Object>())->Ptr();',
            ]
            return ParamInfo(decls=pre, c_arg=var, ts_type=f'{ref_cls} | null')
        return ParamInfo(
            c_arg=f'{ref_cls}::Unwrap(info[{idx}].As<Napi::Object>())->Ptr()',
            ts_type=ref_cls,
        )
    return None


def _ptr_user(inner: dict, name: str, idx: int, nullable: bool) -> ParamInfo | None:
    uname = inner['name']
    if uname in BY_VALUE:
        fn = _EXTRACT_FN[uname]
        return ParamInfo(c_arg=f'{fn}(info[{idx}])', ts_type=sn(uname))
    wrap_cls = f'{sn(uname)}Wrap'
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
