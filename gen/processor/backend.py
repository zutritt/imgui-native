"""Backend NAPI generator.

Processes ImGui backend headers via dear_bindings and generates NAPI wrappers
in lib/gen/backend_napi/.  Each backend is exposed as a JS namespaced object
(e.g. exports.ImplGlfw, exports.ImplOpenGL3).

All backend wrappers are ALWAYS compiled into the addon regardless of whether
the corresponding native library is present.  If a backend was NOT compiled
(controlled by CMake options), calling any of its functions from JavaScript
throws a clear error message with a hint to recompile.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from config import ROOT_DIR
from processor.ts_names import make_unique_ts_identifiers

DEAR_BINDINGS_PY = ROOT_DIR / "deps" / "dear_bindings" / "dear_bindings.py"
IMGUI_DIR = ROOT_DIR / "deps" / "imgui"
BACKENDS_DIR = IMGUI_DIR / "backends"

GEN_BACKENDS_DIR = ROOT_DIR / "lib" / "gen" / "backends"   # dear_bindings output
GEN_BACKEND_NAPI_DIR = ROOT_DIR / "lib" / "gen" / "backend_napi"  # our NAPI wrappers

# ---------------------------------------------------------------------------
# Backend catalogue
# ---------------------------------------------------------------------------
# Each entry:
#   key        — short identifier (used for file names and variable names)
#   header     — backend header in deps/imgui/backends/
#   define     — CMake / C++ preprocessor define that enables this backend
#   js_name    — name of the exported JS object  (e.g. "ImplGlfw")
#   c_prefix   — exact C function prefix shared by all functions in this backend
#   error_msg  — message thrown when the backend was not compiled
BACKENDS: list[dict] = [
    {
        "key": "glfw",
        "header": "imgui_impl_glfw.h",
        "define": "IMGUI_BACKEND_GLFW",
        "js_name": "ImplGlfw",
        "c_prefix": "cImGui_ImplGlfw_",
        "error_msg": "GLFW backend not compiled — rebuild with -DIMGUI_BACKEND_GLFW=ON",
    },
    {
        "key": "opengl2",
        "header": "imgui_impl_opengl2.h",
        "define": "IMGUI_RENDERER_OPENGL2",
        "js_name": "ImplOpenGL2",
        "c_prefix": "cImGui_ImplOpenGL2_",
        "error_msg": "OpenGL2 renderer not compiled — rebuild with -DIMGUI_RENDERER_OPENGL2=ON",
    },
    {
        "key": "opengl3",
        "header": "imgui_impl_opengl3.h",
        "define": "IMGUI_RENDERER_OPENGL3",
        "js_name": "ImplOpenGL3",
        "c_prefix": "cImGui_ImplOpenGL3_",
        "error_msg": "OpenGL3 renderer not compiled — rebuild with -DIMGUI_RENDERER_OPENGL3=ON",
    },
    {
        "key": "sdl2",
        "header": "imgui_impl_sdl2.h",
        "define": "IMGUI_BACKEND_SDL2",
        "js_name": "ImplSDL2",
        "c_prefix": "cImGui_ImplSDL2_",
        "error_msg": "SDL2 backend not compiled — rebuild with -DIMGUI_BACKEND_SDL2=ON",
    },
    {
        "key": "sdl3",
        "header": "imgui_impl_sdl3.h",
        "define": "IMGUI_BACKEND_SDL3",
        "js_name": "ImplSDL3",
        "c_prefix": "cImGui_ImplSDL3_",
        "error_msg": "SDL3 backend not compiled — rebuild with -DIMGUI_BACKEND_SDL3=ON",
    },
]


# ---------------------------------------------------------------------------
# Argument / return-type resolution
# ---------------------------------------------------------------------------

def _to_camel(name: str) -> str:
    """'InitForOpenGL' → 'initForOpenGL'."""
    return name[0].lower() + name[1:] if name else name


def _has_double_pointer(arg: dict) -> bool:
    """Return True when the argument type is a double pointer (T**)."""
    desc = arg["type"]["description"]
    if desc["kind"] == "Pointer":
        inner = desc.get("inner_type", {})
        return inner.get("kind") == "Pointer"
    return False


def _is_emscripten_only(func: dict) -> bool:
    conds = func.get("conditionals", [])
    return any(
        c.get("condition") == "ifdef" and c.get("expression") == "__EMSCRIPTEN__"
        for c in conds
    )


def _resolve_arg(arg: dict, idx: int) -> dict | None:
    """Resolve a single function argument to C++ generation info.

    Returns a dict:
        pre_lines   — list of C++ lines declaring/converting the variable
        pass_expr   — expression passed to the C wrapper function
        ts_type     — TypeScript type string
        need_string — True when <string> include is needed
        need_draw_data  — True when draw_data.h include is needed
        need_texture_data — True when texture_data.h include is needed

    Returns None if the argument cannot be handled (caller should skip the func).
    """
    name = arg["name"]
    type_desc = arg["type"]
    decl = type_desc["declaration"]
    desc = type_desc["description"]
    kind = desc["kind"]

    if kind == "Builtin":
        bt = desc["builtin_type"]
        if bt == "bool":
            return {"pre_lines": [f"  bool {name} = info[{idx}].As<Napi::Boolean>().Value();"],
                    "pass_expr": name, "ts_type": "boolean"}
        if bt in ("int", "signed int", "signed_int"):
            return {"pre_lines": [f"  int {name} = info[{idx}].As<Napi::Number>().Int32Value();"],
                    "pass_expr": name, "ts_type": "number"}
        if bt in ("unsigned int", "unsigned_int"):
            return {"pre_lines": [f"  unsigned int {name} = static_cast<unsigned int>(info[{idx}].As<Napi::Number>().Uint32Value());"],
                    "pass_expr": name, "ts_type": "number"}
        if bt == "float":
            return {"pre_lines": [f"  float {name} = static_cast<float>(info[{idx}].As<Napi::Number>().DoubleValue());"],
                    "pass_expr": name, "ts_type": "number"}
        if bt == "double":
            return {"pre_lines": [f"  double {name} = info[{idx}].As<Napi::Number>().DoubleValue();"],
                    "pass_expr": name, "ts_type": "number"}
        return None  # unsupported builtin

    if kind == "Pointer":
        inner = desc.get("inner_type", {})
        inner_kind = inner.get("kind")

        # Double-pointer — skip the whole function
        if inner_kind == "Pointer":
            return None

        if inner_kind == "Builtin":
            bt = inner.get("builtin_type", "")
            storage = inner.get("storage_classes", [])

            if bt == "char" and "const" in storage:
                # const char* — string argument, nullptr when null/undefined passed
                return {
                    "pre_lines": [
                        f"  std::string {name}_s = (info[{idx}].IsNull() || info[{idx}].IsUndefined()) ? std::string() : info[{idx}].As<Napi::String>().Utf8Value();",
                        f"  const char* {name} = (info[{idx}].IsNull() || info[{idx}].IsUndefined()) ? nullptr : {name}_s.c_str();",
                    ],
                    "pass_expr": name,
                    "ts_type": "string | null",
                    "need_string": True,
                }

            if bt == "void":
                # void* — opaque pointer
                return {
                    "pre_lines": [f"  void* {name} = _ptr_from_js(info[{idx}]);"],
                    "pass_expr": name,
                    "ts_type": "number | bigint",
                }
            return None  # other builtin pointers not expected

        if inner_kind == "User":
            user = inner.get("name", "")

            if user == "ImDrawData":
                return {
                    "pre_lines": [
                        f"  ImDrawData* {name} = nullptr;",
                        f"  if (info[{idx}].IsObject()) {{",
                        f"    {name} = DrawData::Unwrap(info[{idx}].As<Napi::Object>())->Raw();",
                        f"  }} else {{",
                        f"    {name} = reinterpret_cast<ImDrawData*>(_ptr_from_js(info[{idx}]));",
                        f"  }}",
                    ],
                    "pass_expr": name,
                    "ts_type": "DrawData",
                    "need_draw_data": True,
                }

            if user == "ImTextureData":
                return {
                    "pre_lines": [
                        f"  ImTextureData* {name} = nullptr;",
                        f"  if (info[{idx}].IsObject()) {{",
                        f"    {name} = TextureData::Unwrap(info[{idx}].As<Napi::Object>())->Raw();",
                        f"  }} else {{",
                        f"    {name} = reinterpret_cast<ImTextureData*>(_ptr_from_js(info[{idx}]));",
                        f"  }}",
                    ],
                    "pass_expr": name,
                    "ts_type": "TextureData",
                    "need_texture_data": True,
                }

            # Other user pointer types (GLFWwindow*, SDL_Window*, SDL_Event*, etc.)
            # Accept a JS number or BigInt whose numeric value IS the pointer address.
            # NOTE: const T* and T* both map here; the const qualifier is preserved
            # in the cast expression where needed.
            is_const = "const" in decl.split("*")[0]
            cast_type = f"const {user}*" if is_const else f"{user}*"
            return {
                "pre_lines": [
                    f"  {cast_type} {name} = reinterpret_cast<{cast_type}>(_ptr_from_js(info[{idx}]));",
                ],
                "pass_expr": name,
                "ts_type": "number | bigint",
            }

        return None  # unknown pointer inner kind

    if kind == "User":
        # Enum types (e.g. ImGui_ImplSDL2_GamepadMode)
        user = desc.get("name", "")
        return {
            "pre_lines": [f"  {user} {name} = static_cast<{user}>(info[{idx}].As<Napi::Number>().Int32Value());"],
            "pass_expr": name,
            "ts_type": "number",
        }

    return None


def _resolve_ret(ret_type: dict) -> dict | None:
    """Build return info for a function.

    Returns dict with:
        pre       — statement(s) before the call  (may be empty)
        call_wrap — how to wrap the C call: "result = {call}" or just "{call}"
        ret_stmt  — return statement body
        ts_type   — TypeScript return type

    Returns None if return cannot be handled.
    """
    decl = ret_type["declaration"]
    desc = ret_type["description"]
    kind = desc["kind"]

    if kind == "Builtin":
        bt = desc["builtin_type"]
        if bt == "void":
            return {"call_wrap": "{call};", "ret_stmt": "return env.Undefined();", "ts_type": "void"}
        if bt == "bool":
            return {"call_wrap": "bool result = {call};", "ret_stmt": "return Napi::Boolean::New(env, result);", "ts_type": "boolean"}
        if bt in ("int", "signed int"):
            return {"call_wrap": "int result = {call};", "ret_stmt": "return Napi::Number::New(env, result);", "ts_type": "number"}
        if bt in ("float",):
            return {"call_wrap": "float result = {call};", "ret_stmt": "return Napi::Number::New(env, static_cast<double>(result));", "ts_type": "number"}
        if bt == "double":
            return {"call_wrap": "double result = {call};", "ret_stmt": "return Napi::Number::New(env, result);", "ts_type": "number"}
        return None

    return None  # pointer/user returns not expected in backends


# ---------------------------------------------------------------------------
# Code generators
# ---------------------------------------------------------------------------

_PTR_HELPER = """\
static inline void* _ptr_from_js(const Napi::Value& v) {
  if (v.IsBigInt()) {
    bool lossless;
    return reinterpret_cast<void*>(static_cast<uintptr_t>(v.As<Napi::BigInt>().Uint64Value(&lossless)));
  }
  return reinterpret_cast<void*>(static_cast<uintptr_t>(static_cast<uint64_t>(v.As<Napi::Number>().Int64Value())));
}"""


def _build_function(func: dict, c_prefix: str, backend: dict) -> dict | None:
    """Build code for a single backend function.

    Returns dict with:
        js_name         — camelCase JS method name
        real_impl       — C++ body of the real implementation (inside #ifdef)
        stub_impl       — C++ body of the not-compiled stub
        ts_sig          — TypeScript method signature line
        need_string     — bool
        need_draw_data  — bool
        need_texture_data — bool
    Returns None if the function should be skipped.
    """
    c_name = func["name"]
    if not c_name.startswith(c_prefix):
        return None  # does not belong to this backend

    if _is_emscripten_only(func):
        return None  # skip Emscripten-only functions

    # Build JS method name from suffix after c_prefix
    suffix = c_name[len(c_prefix):]
    js_name = _to_camel(suffix)

    # Resolve arguments
    args_info = []
    need_string = False
    need_draw_data = False
    need_texture_data = False

    for i, arg in enumerate(func.get("arguments", [])):
        if _has_double_pointer(arg):
            return None  # skip functions with double-pointer args
        info = _resolve_arg(arg, i)
        if info is None:
            return None  # unsupported arg — skip
        args_info.append(info)
        if info.get("need_string"):
            need_string = True
        if info.get("need_draw_data"):
            need_draw_data = True
        if info.get("need_texture_data"):
            need_texture_data = True

    # Resolve return type
    ret_info = _resolve_ret(func["return_type"])
    if ret_info is None:
        return None  # unsupported return type

    # Build the real implementation body
    body_lines = ["  Napi::Env env = info.Env();"]
    for ai in args_info:
        body_lines.extend(ai["pre_lines"])

    call_str = f"{c_name}({', '.join(ai['pass_expr'] for ai in args_info)})"
    body_lines.append("  " + ret_info["call_wrap"].replace("{call}", call_str))
    body_lines.append("  " + ret_info["ret_stmt"])

    real_body = "\n".join(body_lines)

    # Build the stub body
    stub_body = (
        f'  Napi::Error::New(info.Env(), "{backend["error_msg"]}").ThrowAsJavaScriptException();\n'
        f"  return info.Env().Undefined();"
    )

    # TypeScript signature
    ts_param_names = make_unique_ts_identifiers([
        arg["name"]
        for arg in func.get("arguments", [])
    ])
    ts_param_pairs = []
    for (arg_name, ai) in zip(ts_param_names, args_info):
        ts_param_pairs.append(f"{arg_name}: {ai['ts_type']}")
    ts_sig = f"  {js_name}({', '.join(ts_param_pairs)}): {ret_info['ts_type']};"

    return {
        "js_name": js_name,
        "c_name": c_name,
        "real_impl": real_body,
        "stub_impl": stub_body,
        "ts_sig": ts_sig,
        "need_string": need_string,
        "need_draw_data": need_draw_data,
        "need_texture_data": need_texture_data,
        "ret_ts": ret_info["ts_type"],
    }


def _build_backend_files(backend: dict, functions: list[dict]) -> tuple[str, str, str]:
    """Build .h, .cpp, and .d.ts content for a single backend.

    Returns (header_src, cpp_src, dts_src).
    """
    key = backend["key"]
    define = backend["define"]
    js_name = backend["js_name"]
    c_prefix = backend["c_prefix"]

    # Collect resolved function info
    funcs: list[dict] = []
    for func in functions:
        result = _build_function(func, c_prefix, backend)
        if result is not None:
            funcs.append(result)

    if not funcs:
        print(f"  [backend] {key}: no bindable functions found (check c_prefix or function definitions)")

    need_string = any(f["need_string"] for f in funcs)
    need_draw_data = any(f["need_draw_data"] for f in funcs)
    need_texture_data = any(f["need_texture_data"] for f in funcs)

    # ── Header (.h) ─────────────────────────────────────────────────────────
    header = (
        f"#pragma once\n"
        f"#include <napi.h>\n"
        f"\n"
        f"// Exposes the ImGui {js_name} backend as a Napi::Object.\n"
        f"// Functions that were not compiled throw a runtime error.\n"
        f"Napi::Object {js_name}_Register(Napi::Env env);\n"
    )

    # ── C++ (.cpp) ──────────────────────────────────────────────────────────
    cpp_lines: list[str] = []
    cpp_lines.append(f'#include "{key}_backend.h"')
    cpp_lines.append("#include <napi.h>")
    cpp_lines.append("")

    # Real-implementation section
    cpp_lines.append(f"#ifdef {define}")
    cpp_lines.append("")
    if need_string:
        cpp_lines.append("#include <string>")
    cpp_lines.append(f'#include "dcimgui_impl_{key}.h"')
    if need_draw_data:
        cpp_lines.append('#include "draw_data.h"')
    if need_texture_data:
        cpp_lines.append('#include "texture_data.h"')
    cpp_lines.append("")
    cpp_lines.append(_PTR_HELPER)
    cpp_lines.append("")

    for f in funcs:
        cpp_lines.append(f"static Napi::Value {js_name}_{f['js_name']}(const Napi::CallbackInfo& info) {{")
        cpp_lines.append(f["real_impl"])
        cpp_lines.append("}")
        cpp_lines.append("")

    cpp_lines.append(f"#else  // {define} not defined — stubs that throw at runtime")
    cpp_lines.append("")

    for f in funcs:
        cpp_lines.append(f"static Napi::Value {js_name}_{f['js_name']}(const Napi::CallbackInfo& info) {{")
        cpp_lines.append(f["stub_impl"])
        cpp_lines.append("}")
        cpp_lines.append("")

    cpp_lines.append(f"#endif  // {define}")
    cpp_lines.append("")

    # Registration function
    cpp_lines.append(f"Napi::Object {js_name}_Register(Napi::Env env) {{")
    cpp_lines.append("  auto obj = Napi::Object::New(env);")
    for f in funcs:
        cpp_lines.append(
            f'  obj.Set("{f["js_name"]}", Napi::Function::New(env, {js_name}_{f["js_name"]}, "{f["js_name"]}"));'
        )
    cpp_lines.append("  return obj;")
    cpp_lines.append("}")
    cpp_lines.append("")

    cpp_src = "\n".join(cpp_lines)

    # ── TypeScript declaration ──────────────────────────────────────────────
    dts_lines = [f"export interface {js_name} {{"]
    for f in funcs:
        dts_lines.append(f["ts_sig"])
    dts_lines.append("}")
    dts_lines.append(f"export const {js_name}: {js_name};")
    dts_lines.append("")

    dts_src = "\n".join(dts_lines)

    return header, cpp_src, dts_src


def _build_backends_init(backends_info: list[dict]) -> tuple[str, str]:
    """Build backends_init.h and backends_init.cpp."""
    js_names = [b["js_name"] for b in backends_info]
    keys = [b["key"] for b in backends_info]

    header = (
        "#pragma once\n"
        "#include <napi.h>\n"
        "\n"
        "// Register all backend namespace objects onto exports.\n"
        "// Called once from module.cpp Init().\n"
        "void InitBackends(Napi::Env env, Napi::Object exports);\n"
    )

    includes = "".join(f'#include "{k}_backend.h"\n' for k in keys)
    set_lines = "\n".join(
        f'  exports.Set("{jn}", {jn}_Register(env));'
        for jn in js_names
    )
    if "ImplGlfw" in js_names:
        # Alias: users can access GLFW backend as ImplGlfw and ImplGlfw3.
        set_lines += '\n  exports.Set("ImplGlfw3", exports.Get("ImplGlfw"));'
    cpp = (
        '#include "backends_init.h"\n'
        f"{includes}"
        "\n"
        "void InitBackends(Napi::Env env, Napi::Object exports) {\n"
        f"{set_lines}\n"
        "}\n"
    )

    return header, cpp


# ---------------------------------------------------------------------------
# dear_bindings invocation
# ---------------------------------------------------------------------------

def _run_dear_bindings(header: str, out_stem: Path) -> Path | None:
    """Run dear_bindings for one backend header. Returns path to .json output or None."""
    header_path = BACKENDS_DIR / header
    if not header_path.exists():
        print(f"  [backend] WARNING: backend header not found: {header_path}", file=sys.stderr)
        return None

    cmd = [
        sys.executable,
        str(DEAR_BINDINGS_PY),
        "--backend",
        "--imgui-include-dir", str(IMGUI_DIR) + "/",
        "--backend-include-dir", str(BACKENDS_DIR) + "/",
        "-o", str(out_stem),
        str(header_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [backend] ERROR running dear_bindings for {header}:\n{result.stderr}", file=sys.stderr)
        return None

    # Post-process: fix dear_bindings namespace bugs in generated .h and .cpp.
    for suffix in (".h", ".cpp"):
        p = out_stem.with_suffix(suffix)
        if not p.exists():
            continue
        txt = p.read_text()
        # Fix bare ImTextureData* → cimgui::ImTextureData* (.cpp only — header
        # doesn't live inside a namespace)
        if suffix == ".cpp":
            txt = re.sub(
                r'(?<!\w)(ImTextureData\s*\*)',
                r'cimgui::ImTextureData*',
                txt,
            )
            # Fix function body calls: when a cimgui:: function passes
            # cimgui::ImTextureData* to a ::ImGui_Impl* function, a
            # reinterpret_cast is needed.
            # Pattern: ::ImGui_Impl*_UpdateTexture(tex)  →  ...( reinterpret_cast<::ImTextureData*>(tex) )
            txt = re.sub(
                r'(::ImGui_Impl\w+_UpdateTexture)\((\w+)\)',
                r'\1(reinterpret_cast<::ImTextureData*>(\2))',
                txt,
            )
        # Fix "struct _SDL_GameController" typedef conflict — remove the
        # erroneous "struct" keyword when used with the typedef name.
        txt = txt.replace("struct _SDL_GameController**", "_SDL_GameController**")
        txt = txt.replace("struct cimgui::_SDL_GameController**", "cimgui::_SDL_GameController**")
        txt = txt.replace("struct ::_SDL_GameController**", "::_SDL_GameController**")
        p.write_text(txt)

    return out_stem.with_suffix(".json")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_backends() -> None:
    """Generate dear_bindings wrappers and NAPI wrappers for all backends."""
    GEN_BACKENDS_DIR.mkdir(parents=True, exist_ok=True)
    GEN_BACKEND_NAPI_DIR.mkdir(parents=True, exist_ok=True)

    all_dts: list[str] = []
    init_info: list[dict] = []

    for backend in BACKENDS:
        key = backend["key"]
        header = backend["header"]
        js_name = backend["js_name"]

        print(f"  [backend] {key} → {js_name}")

        # 1. Run dear_bindings
        out_stem = GEN_BACKENDS_DIR / f"dcimgui_impl_{key}"
        json_path = _run_dear_bindings(header, out_stem)
        if json_path is None:
            continue

        # 2. Parse JSON metadata
        try:
            data = json.loads(json_path.read_text())
        except Exception as e:
            print(f"  [backend] ERROR reading JSON for {key}: {e}", file=sys.stderr)
            continue

        functions = data.get("functions", [])
        print(f"    dear_bindings: {len(functions)} functions found")

        # 3. Generate NAPI wrappers
        header_src, cpp_src, dts_src = _build_backend_files(backend, functions)

        h_path = GEN_BACKEND_NAPI_DIR / f"{key}_backend.h"
        cpp_path = GEN_BACKEND_NAPI_DIR / f"{key}_backend.cpp"

        h_path.write_text(header_src)
        cpp_path.write_text(cpp_src)

        bound_count = cpp_src.count("static Napi::Value") // 2  # real + stub
        print(f"    bound: {bound_count} functions")

        all_dts.append(dts_src)
        init_info.append(backend)

    # 4. Write backends_init.h/.cpp
    if init_info:
        init_h, init_cpp = _build_backends_init(init_info)
        (GEN_BACKEND_NAPI_DIR / "backends_init.h").write_text(init_h)
        (GEN_BACKEND_NAPI_DIR / "backends_init.cpp").write_text(init_cpp)

    # 5. Write combined backends.d.ts
    dts_path = ROOT_DIR / "lib" / "gen" / "dts" / "backends.d.ts"
    has_glfw = any(b.get("js_name") == "ImplGlfw" for b in init_info)
    glfw_alias_dts = ""
    if has_glfw:
        glfw_alias_dts = (
            "\n"
            "export type ImplGlfw3 = ImplGlfw;\n"
            "export const ImplGlfw3: ImplGlfw3;\n"
        )

    dts_path.write_text(
        '// Auto-generated — do not edit.\n'
        'import type { DrawData, TextureData } from "./structs";\n\n'
        + "\n".join(all_dts)
        + glfw_alias_dts
    )

    print(f"  [backend] Generated {len(init_info)} backend namespace(s)")
