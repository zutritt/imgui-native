BY_VALUE = {'ImVec2', 'ImVec4', 'ImColor', 'ImTextureRef'}

_WRAP_CLS = {
    'ImVec2': 'Vec2Wrap',
    'ImVec4': 'Vec4Wrap',
    'ImColor': 'ColorWrap',
    'ImTextureRef': 'TextureRefWrap',
}
_EXTRACT_FN = {
    'ImVec2': 'ExtractImVec2',
    'ImVec4': 'ExtractImVec4',
    'ImColor': 'ExtractImColor',
    'ImTextureRef': 'ExtractImTextureRef',
}
_MUT_REF = {'bool': 'BoolRef', 'int': 'IntRef', 'float': 'FloatRef', 'double': 'DoubleRef'}

_NUM = {
    'bool': ('Napi::Boolean', 'Value()', 'boolean'),
    'int': ('Napi::Number', 'Int32Value()', 'number'),
    'unsigned_int': ('Napi::Number', 'Uint32Value()', 'number'),
    'short': ('Napi::Number', 'Int32Value()', 'number'),
    'unsigned_short': ('Napi::Number', 'Uint32Value()', 'number'),
    'char': ('Napi::Number', 'Int32Value()', 'number'),
    'unsigned_char': ('Napi::Number', 'Uint32Value()', 'number'),
    'float': ('Napi::Number', 'FloatValue()', 'number'),
    'double': ('Napi::Number', 'DoubleValue()', 'number'),
    'long_long': ('Napi::BigInt', 'Int64Value', 'bigint'),
    'unsigned_long_long': ('Napi::BigInt', 'Uint64Value', 'bigint'),
}

_C_TYPE = {
    'bool': 'bool',
    'int': 'int',
    'unsigned_int': 'unsigned int',
    'short': 'short',
    'unsigned_short': 'unsigned short',
    'char': 'char',
    'unsigned_char': 'unsigned char',
    'float': 'float',
    'double': 'double',
    'long_long': 'long long',
    'unsigned_long_long': 'unsigned long long',
}


def wrap_builtin(bt: str, val: str) -> str | None:
    """Return C++ expression wrapping C value `val` as a JS Napi value.

    >>> wrap_builtin('bool', 'x')
    'Napi::Boolean::New(env, x)'
    >>> wrap_builtin('float', 'x')
    'Napi::Number::New(env, x)'
    >>> wrap_builtin('void', 'x') is None
    True
    """
    info = _NUM.get(bt)
    if not info:
        return None
    napi, _, _ = info
    if 'BigInt' in napi:
        t = 'uint64_t' if 'unsigned' in bt else 'int64_t'
        return f'Napi::BigInt::New(env, ({t}){val})'
    if napi == 'Napi::Boolean':
        return f'Napi::Boolean::New(env, {val})'
    return f'Napi::Number::New(env, {val})'


def extract_builtin(bt: str, idx: int) -> tuple[list[str], str] | None:
    """Return (pre_decl_lines, c_expr) for extracting builtin from info[idx].

    >>> extract_builtin('float', 0)
    ([], 'info[0].As<Napi::Number>().FloatValue()')
    >>> extract_builtin('void', 0) is None
    True
    """
    info = _NUM.get(bt)
    if not info:
        return None
    napi, method, _ = info
    if 'BigInt' in napi:
        var = f'_arg{idx}'
        signed = bt == 'long_long'
        t = 'int64_t' if signed else 'uint64_t'
        m = 'Int64Value' if signed else 'Uint64Value'
        pre = [f'bool _loss{idx}; {t} {var} = info[{idx}].As<{napi}>().{m}(&_loss{idx});']
        return pre, var
    return [], f'info[{idx}].As<{napi}>().{method}'


def ts_builtin(bt: str) -> str | None:
    """Return TypeScript type string for a builtin type.

    >>> ts_builtin('float')
    'number'
    >>> ts_builtin('bool')
    'boolean'
    >>> ts_builtin('void') is None
    True
    """
    info = _NUM.get(bt)
    return info[2] if info else None
