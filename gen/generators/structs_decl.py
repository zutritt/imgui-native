from __future__ import annotations

from core.naming import method_name
from core.naming import struct_name as sn
from core.naming import to_camel
from data.types_builtin import BY_VALUE
from data.types_field import field_getter
from data.types_field import field_setter
from generators.structs_init import struct_init_body


def _accessor_decls(cname: str, fields: list[dict], registry) -> list[str]:
    decls = []
    for f in fields:
        fname = f['name']
        if fname.startswith('_') or f.get('is_internal'):
            continue
        if not field_getter(f, registry):
            continue
        decls.append(f'  Napi::Value Get{fname}(const Napi::CallbackInfo& info);')
        if field_setter(f, registry):
            decls.append(
                f'  void Set{fname}(const Napi::CallbackInfo& info, const Napi::Value& val);'
            )
    return decls


def _method_decls(cname: str, registry) -> list[str]:
    decls = []
    seen: set[str] = set()
    for m in registry.methods_for(cname):
        if m.get('is_internal') or m.get('is_manual_helper') or m.get('is_imstr_helper'):
            continue
        js = method_name(m['name'], cname + '_', registry.has_helper(m['name']))
        if js in seen:
            continue
        seen.add(js)
        is_static = m.get('is_static', False)
        mfn = to_camel(js[0].upper() + js[1:]) + 'Method'
        if is_static:
            decls.append(f'  static Napi::Value {mfn}(const Napi::CallbackInfo& info);')
        else:
            decls.append(f'  Napi::Value {mfn}(const Napi::CallbackInfo& info);')
    return decls


def struct_header_decl(s: dict, registry) -> str:
    cname = s['name']
    js = sn(cname)
    wrap = f'{js}Wrap'
    fields = s.get('fields', [])
    is_owned = cname in registry.owned_structs

    lines = [
        f'class {wrap} : public Napi::ObjectWrap<{wrap}> {{',
        'public:',
        '  static Napi::FunctionReference constructor;',
    ]

    if cname in BY_VALUE:
        lines.append(f'  {cname} value;')
        lines.append(f'  static Napi::Value New(Napi::Env env, {cname} v);')
    else:
        lines.append(f'  {cname}* ptr; bool owned;')
        lines.append(f'  static Napi::Value Wrap(Napi::Env env, {cname}* raw);')
        if is_owned:
            lines.append(f'  static Napi::Value WrapOwned(Napi::Env env, {cname}* raw);')

    lines.append(f'  {wrap}(const Napi::CallbackInfo& info);')
    lines.append(f'  ~{wrap}();')
    lines.append('  static Napi::Object Init(Napi::Env env, Napi::Object exports);')

    private = _accessor_decls(cname, fields, registry) + _method_decls(cname, registry)
    if private:
        lines.append('private:')
        lines.extend(private)

    lines.append('};')
    return '\n'.join(lines)


__all__ = ['struct_header_decl', 'struct_init_body']
