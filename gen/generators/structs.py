from __future__ import annotations

from config import GEN_DTS
from config import GEN_NAPI
from config import SKIP_STRUCTS
from core.naming import struct_name as sn
from generators.structs_decl import struct_header_decl
from generators.structs_dts import dts_class
from generators.structs_impl import impl_blocks


def _structs_to_generate(registry) -> list[dict]:
    result = list(registry.by_value_structs)
    for s in registry.opaque_structs:
        if s['name'] == 'ImGuiContext':
            result.append(s)
    for s in registry.regular_structs:
        if s['name'] not in SKIP_STRUCTS:
            result.append(s)
    return result


def generate_structs(registry):
    structs = _structs_to_generate(registry)

    h_lines = ['#pragma once', '#include <napi.h>', '#include "dcimgui.h"', '']
    for s in structs:
        h_lines.append(struct_header_decl(s, registry))
        h_lines.append('')
    h_lines.append('void InitStructs(Napi::Env env, Napi::Object exports);')
    (GEN_NAPI / 'structs.h').write_text('\n'.join(h_lines))

    cpp_lines = ['#include "structs.h"', '#include <string>', '']
    for s in structs:
        cpp_lines.extend(impl_blocks(s, registry))
        cpp_lines.append('')

    init_body = '\n'.join(f'  {sn(s["name"])}Wrap::Init(env, exports);' for s in structs)
    cpp_lines.append(f'void InitStructs(Napi::Env env, Napi::Object exports)\n{{\n{init_body}\n}}')
    (GEN_NAPI / 'structs.cpp').write_text('\n'.join(cpp_lines))

    dts_lines = []
    for s in structs:
        dts_lines.append(dts_class(s, registry))
        dts_lines.append('')
    (GEN_DTS / 'structs.d.ts').write_text('\n'.join(dts_lines))
