from __future__ import annotations

from data.types import param_info
from data.types import return_info


def build_call_body(func: dict, registry, c_self: str | None = None) -> str | None:
    args = func.get('arguments', [])
    has_varargs = any(a.get('is_varargs') for a in args)
    real_args = [a for a in args if not a.get('is_varargs') and not a.get('is_instance_pointer')]

    decls: list[str] = []
    c_args: list[str] = [c_self] if c_self else []
    out_params: list[tuple[str, str]] = []
    js_idx = 0
    i = 0
    while i < len(real_args):
        a = real_args[i]
        next_a = real_args[i + 1] if i + 1 < len(real_args) else None
        pi = param_info(a, next_a, js_idx, registry)
        if pi is None:
            return None
        if pi.is_out:
            oname = a.get('name', f'out{i}')
            decls.append(f'{pi.out_c_type} _{oname} = 0;')
            out_params.append((oname, pi.out_c_type))
        else:
            decls.extend(pi.decls)
            js_idx += 1
        c_args.append(pi.c_arg)
        if pi.consumed_next:
            c_args.append(pi.size_c_arg)
            i += 2
        else:
            i += 1

    if has_varargs:
        c_args.append('"%s"')

    ret_desc = func['return_type']['description']
    ri = return_info(ret_desc, registry, func['name'])

    body_lines = ['Napi::Env env = info.Env();', *decls]
    call = f'{func["name"]}({", ".join(c_args)})'

    if ri:
        body_lines.append(f'auto _r = {call};')
        wrap = ri.wrap.replace('{val}', '_r')
        if out_params:
            body_lines.append('Napi::Object _obj = Napi::Object::New(env);')
            body_lines.append(f'_obj.Set("result", {wrap});')
            for n, _ in out_params:
                body_lines.append(f'_obj.Set("{n}", Napi::Number::New(env, _{n}));')
            body_lines.append('return _obj;')
        else:
            body_lines.append(f'return {wrap};')
    else:
        body_lines.append(f'{call};')
        if out_params:
            body_lines.append('Napi::Object _obj = Napi::Object::New(env);')
            for n, _ in out_params:
                body_lines.append(f'_obj.Set("{n}", Napi::Number::New(env, _{n}));')
            body_lines.append('return _obj;')
        else:
            body_lines.append('return env.Undefined();')

    return '\n'.join(body_lines)


def build_dts_args(func: dict, registry, skip_instance: bool = True) -> str | None:
    args = func.get('arguments', [])
    real_args = [a for a in args if not a.get('is_varargs')]
    if skip_instance:
        real_args = [a for a in real_args if not a.get('is_instance_pointer')]
    parts = []
    js_idx = 0
    i = 0
    while i < len(real_args):
        a = real_args[i]
        next_a = real_args[i + 1] if i + 1 < len(real_args) else None
        pi = param_info(a, next_a, js_idx, registry)
        if pi is None:
            i += 1
            continue
        if pi.is_out:
            i += 1
            continue
        aname = a.get('name', f'arg{js_idx}')
        opt = '?' if a.get('default_value') is not None else ''
        parts.append(f'{aname}{opt}: {pi.ts_type}')
        if pi.consumed_next:
            i += 2
        else:
            i += 1
        js_idx += 1
    return ', '.join(parts)
