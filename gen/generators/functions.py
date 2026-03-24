from __future__ import annotations

from builders.cpp import CppFile
from builders.dts import DtsFile
from config import GEN_DTS
from config import GEN_NAPI
from core.naming import free_fn_name
from core.text import indent
from data.types import return_info
from generators.call import build_call_body
from generators.call import build_dts_args


def generate_functions(registry) -> int:
    f = CppFile()
    f.raw('#include "structs.h"')
    f.raw('#include <string>')
    f.blank()

    dts = DtsFile()
    init_sets: list[str] = []
    skip_count = 0

    for func in registry.free_functions:
        js = free_fn_name(func['name'], registry.has_helper(func['name']))
        body = build_call_body(func, registry)
        if body is None:
            f.raw(f'// SKIP: {func["name"]} (unsupported param types)')
            skip_count += 1
            continue
        sig = f'static Napi::Value _{js}(const Napi::CallbackInfo& info)'
        f.raw(f'{sig}\n{{\n{indent(body)}\n}}')
        f.blank()
        init_sets.append(f'  exports.Set("{js}", Napi::Function::New(env, _{js}));')

        args_str = build_dts_args(func, registry)
        if args_str is not None:
            ri = return_info(func['return_type']['description'], registry, func['name'])
            ts_ret = ri.ts_type if ri else 'void'
            dts.raw(f'export declare function {js}({args_str}): {ts_ret};')

    init_body = '\n'.join(init_sets)
    f.raw(f'void InitFunctions(Napi::Env env, Napi::Object exports)\n{{\n{init_body}\n}}')

    (GEN_NAPI / 'functions.cpp').write_text(f.render())
    (GEN_DTS / 'functions.d.ts').write_text(dts.render())
    return skip_count
