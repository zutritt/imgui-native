from __future__ import annotations

from core.naming import struct_name as sn
from data.types_builtin import _WRAP_CLS
from data.types_builtin import BY_VALUE


def _imvec_getter(fname: str, vec_type: str) -> tuple[str, str] | None:
    if fname == 'VtxBuffer':
        body = (
            'return Napi::ArrayBuffer::New(info.Env(), ptr->VtxBuffer.Data,\n'
            '  ptr->VtxBuffer.Size * sizeof(ImDrawVert));'
        )
        return body, 'ArrayBuffer'
    if fname == 'IdxBuffer':
        body = (
            'auto _b = Napi::ArrayBuffer::New(info.Env(), ptr->IdxBuffer.Data,\n'
            '  ptr->IdxBuffer.Size * sizeof(ImDrawIdx));\n'
            'return Napi::Uint16Array::New(info.Env(), ptr->IdxBuffer.Size, _b, 0);'
        )
        return body, 'Uint16Array'
    elem = vec_type.removeprefix('ImVector_')
    is_ptr = elem.endswith('Ptr')
    if is_ptr:
        elem = elem[:-3]
    if elem in BY_VALUE:
        cls = _WRAP_CLS[elem]
        access = f'ptr->{fname}.Data[i]' if is_ptr else f'&ptr->{fname}.Data[i]'
        body = (
            f'Napi::Env env = info.Env(); int _s = ptr->{fname}.Size;\n'
            f'Napi::Array _a = Napi::Array::New(env, _s);\n'
            f'for (int i = 0; i < _s; i++) _a.Set(i, {cls}::New(env, *{access}));\n'
            f'return _a;'
        )
        return body, f'Array<{cls.replace("Wrap", "")}>'
    js = sn(elem)
    wrap = f'{js}Wrap'
    access = f'ptr->{fname}.Data[i]' if is_ptr else f'&ptr->{fname}.Data[i]'
    body = (
        f'Napi::Env env = info.Env(); int _s = ptr->{fname}.Size;\n'
        f'Napi::Array _a = Napi::Array::New(env, _s);\n'
        f'for (int i = 0; i < _s; i++) _a.Set(i, {wrap}::Wrap(env, {access}));\n'
        f'return _a;'
    )
    return body, f'Array<{js}>'


def _array_getter(name: str, kind: str, desc: dict, bv: int | None) -> tuple[str, str] | None:
    if kind == 'Array':
        inner = desc.get('inner_type', {})
        ik = inner.get('kind', '')
        bt = inner.get('builtin_type', '') if ik == 'Builtin' else ''
        uname = inner.get('name', '') if ik == 'User' else ''
    else:
        bt = desc.get('builtin_type', '') if kind == 'Builtin' else ''
        uname = desc.get('name', '') if kind == 'User' else ''
    if bt == 'float' and bv:
        body = (
            f'auto b=Napi::ArrayBuffer::New(info.Env(),{bv}*sizeof(float));\n'
            f'memcpy(b.Data(),ptr->{name},{bv}*sizeof(float));\n'
            f'return Napi::Float32Array::New(info.Env(),{bv},b,0);'
        )
        return body, 'Float32Array'
    if bt in ('int', 'unsigned_int', 'short', 'unsigned_short', 'unsigned_char') and bv:
        body = (
            f'auto b=Napi::ArrayBuffer::New(info.Env(),{bv}*sizeof(int));\n'
            f'memcpy(b.Data(),ptr->{name},{bv}*sizeof(int));\n'
            f'return Napi::Int32Array::New(info.Env(),{bv},b,0);'
        )
        return body, 'Int32Array'
    if uname == 'ImVec4' and bv:
        body = (
            f'auto b=Napi::ArrayBuffer::New(info.Env(),{bv}*4*sizeof(float));\n'
            f'memcpy(b.Data(),ptr->{name},{bv}*4*sizeof(float));\n'
            f'return Napi::Float32Array::New(info.Env(),{bv}*4,b,0);'
        )
        return body, 'Float32Array'
    return None
