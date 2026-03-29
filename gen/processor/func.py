"""
Generates NAPI C++ function wrappers and TypeScript declarations for ImGui C API
functions (those starting with ImGui_).

Emits:
  lib/gen/napi/funcs.cpp     — all function wrappers registered via InitFuncs()
  lib/gen/napi/funcs_init.h  — InitFuncs() declaration
  lib/gen/dts/funcs.d.ts     — TypeScript function signatures

Arguments handled:
  Builtin scalars (bool, int, float, double …)      → JS primitives
  const char*                                        → JS string
  Mutable bool*/int*/float*/double* (output params)  → BoolRef/IntRef/FloatRef/DoubleRef
  User enum/typedef-to-builtin                       → JS number
  User by-value struct (ImVec2 etc.)                 → Struct wrapper unwrap
  Pointer to by-ref struct (ImGuiStyle* etc.)        → Struct wrapper unwrap

Deferred (functions with any unresolvable arg/return are skipped):
  void* / const void*        — opaque data pointer
  Array args                 — fixed-size arrays
  Type args                  — function pointer callbacks
  Pointer to Pointer         — double pointers
  ImGuiContext* returns      — context management

Only ImGui_* prefixed functions are emitted; struct-method functions
(ImDrawList_*, ImGuiIO_*, etc.) are deferred to a later phase.
"""

from __future__ import annotations

from pathlib import Path

from config import GEN_DTS
from config import GEN_NAPI
from processor.resolve import _BUILTIN_ARG
from processor.resolve import _BUILTIN_RET
from processor.resolve import _MUTABLE_PTR_WRAPPERS
from processor.resolve import _default_value_cpp
from processor.resolve import _resolve_arg
from processor.resolve import _resolve_return
from processor.ts_names import make_unique_ts_identifiers


def _cpp_name_to_js_name(name: str) -> str:
    """Convert an ImGui_ C function name to a camelCase JS name.

    ImGui_Begin        → begin
    ImGui_GetIO        → getIO
    ImGui_NewFrame     → newFrame
    ImGui_SliderFloat  → sliderFloat
    """
    if name.startswith("ImGui_"):
        tail = name[len("ImGui_"):]
    else:
        return None  # non-ImGui_ functions deferred
    if not tail:
        return None
    return tail[0].lower() + tail[1:]



# ─── Function resolver ────────────────────────────────────────────────────────

def _resolve_function(
    func: dict,
    processed_enums: dict,
    processed_typedefs: dict,
    processed_structs: dict,
) -> dict | None:
    """Try to build a complete NAPI wrapper descriptor for one C function.

    Returns None if the function cannot be bound yet (unsupported types).
    """
    c_name = func["name"]

    # Only ImGui_ prefixed functions in this phase
    js_name = _cpp_name_to_js_name(c_name)
    if js_name is None:
        return None

    # Skip filtered functions
    if func.get("is_internal"): return None
    if func.get("is_imstr_helper"): return None
    if func.get("is_manual_helper"): return None
    # Note: is_default_argument_helper=True means it's the convenient no-default-args
    # form (e.g. ImGui_Button vs ImGui_ButtonEx). Include both.

    # Resolve return type
    ret = _resolve_return(
        func["return_type"],
        processed_enums, processed_typedefs, processed_structs,
    )
    if ret is None:
        print(f"  [func] Skip {c_name}: unsupported return type {func['return_type']['declaration']!r}")
        return None

    # Resolve each argument
    resolved_args = []
    all_includes = set(ret["extra_includes"])
    _absorb_next_size   = False   # True when previous arg absorbs the next size_t
    _absorbed_size_expr = ""      # Pass expr to inject for the absorbed size_t

    for arg in func.get("arguments", []):
        if arg.get("is_varargs"):
            print(f"  [func] Skip {c_name}: varargs")
            return None

        # If the previous binding consumes this arg (size_t after char* buf)
        if _absorb_next_size:
            _absorb_next_size = False
            d = arg["type"].get("description", {})
            if d.get("kind") == "User" and d.get("name") == "size_t":
                resolved_args.append({
                    "pre_lines": [],
                    "pass_expr": _absorbed_size_expr,
                    "ts_type": None,
                    "is_optional": False,
                    "extra_includes": [],
                    "_absorbed": True,
                })
                continue  # don't consume a JS slot
            # Not size_t — fall through and resolve normally

        js_idx = sum(1 for r in resolved_args if not r.get("_absorbed"))
        resolved = _resolve_arg(
            arg, js_idx,
            processed_enums, processed_typedefs, processed_structs,
        )
        if resolved is None:
            t = arg["type"].get("declaration", "?")
            print(f"  [func] Skip {c_name}: unsupported arg '{arg['name']}' ({t})")
            return None

        if resolved.get("absorbs_next_size"):
            _absorb_next_size   = True
            _absorbed_size_expr = resolved.pop("absorbed_size_expr")
            resolved.pop("absorbs_next_size", None)

        resolved_args.append(resolved)
        for inc in resolved["extra_includes"]:
            all_includes.add(inc)

    return {
        "c_name": c_name,
        "js_name": js_name,
        "ret": ret,
        "args": resolved_args,
        "includes": sorted(all_includes),
    }


# ─── Code builders ────────────────────────────────────────────────────────────

def _build_wrapper_body(func_info: dict) -> str:
    """Build the body of one Napi::Function::New lambda."""
    ret   = func_info["ret"]
    args  = func_info["args"]
    c_name = func_info["c_name"]

    lines = []
    lines.append("    Napi::Env env = info.Env();")

    for resolved in args:
        for line in resolved["pre_lines"]:
            lines.append("  " + line)

    call_args = ", ".join(a["pass_expr"] for a in args)
    call = f"{c_name}({call_args})"

    if ret["call_prefix"]:
        lines.append(f"  {ret['call_prefix'].strip()}{call};")
    else:
        lines.append(f"  {call};")

    lines.append(f"  {ret['return_stmt'].strip()}")

    return "\n".join("  " + l for l in lines)


def _build_cpp(func_infos: list[dict]) -> str:
    """Build the complete funcs.cpp content."""

    # Collect all includes
    all_includes: set[str] = set()
    all_includes.add("vec4.h")  # needed by synthetic textColored wrapper
    all_includes.add("vec2.h")  # needed by setNextWindowSizeConstraints / inputTextMultilineEx
    # Always include callback + string_list for synthetic wrappers
    all_includes.add("../../ref/callback.h")
    all_includes.add("../../ref/string_list.h")
    # Callback data wrappers used by inputText* synthetics
    all_includes.add("input_text_callback_data.h")
    all_includes.add("size_callback_data.h")
    for fi in func_infos:
        for inc in fi["includes"]:
            all_includes.add(inc)

    # Separate ref includes from struct includes (for ordering)
    ref_includes = sorted(i for i in all_includes if i.startswith("../../ref/"))
    struct_includes = sorted(i for i in all_includes if not i.startswith("../../ref/"))

    inc_block = ""
    for inc in ref_includes:
        inc_block += f'#include "{inc}"\n'
    for inc in struct_includes:
        inc_block += f'#include "{inc}"\n'

    # Build function registrations
    registrations = []
    for fi in func_infos:
        body = _build_wrapper_body(fi)
        reg = (
            f'  exports.Set("{fi["js_name"]}", Napi::Function::New(env,\n'
            f'    [](const Napi::CallbackInfo& info) -> Napi::Value {{\n'
            f'{body}\n'
            f'    }}));\n'
        )
        registrations.append(reg)

    regs_block = "\n".join(registrations)

    return (
        f'#include "funcs_init.h"\n'
        f'#include <string>\n'
        f'#include <cfloat>\n'
        f'#include "dcimgui.h"\n'
        f'{inc_block}'
        f'\n'
        f'{_build_synthetic_text_cpp()}'
        f'\n'
        f'void InitFuncs(Napi::Env env, Napi::Object exports) {{\n'
        f'{regs_block}'
        f'  _InitSyntheticFuncs(env, exports);\n'
        f'}}\n'
    )


def _build_init_header() -> str:
    return (
        "#pragma once\n"
        "#include <napi.h>\n"
        "\n"
        "// Register all generated ImGui function wrappers on exports.\n"
        "// Called once from module.cpp Init().\n"
        "void InitFuncs(Napi::Env env, Napi::Object exports);\n"
    )


# ─── Synthetic text/tooltip wrappers ─────────────────────────────────────────
# ImGui's text functions use varargs (ImGui_Text(fmt,...)) which we can't bind
# generically.  These synthetic wrappers accept a pre-formatted string and call
# through to the appropriate C function internally.

_SYNTHETIC_TEXT_DTS = """\
export declare function text(text: string): void;
export declare function textColored(col: Vec4, text: string): void;
export declare function textDisabled(text: string): void;
export declare function textWrapped(text: string): void;
export declare function labelText(label: string, text: string): void;
export declare function bulletText(text: string): void;
export declare function setTooltip(text: string): void;
export declare function setItemTooltip(text: string): void;
export declare function treeNodeStr(label: string): boolean;
export declare function treeNodeExStr(label: string, flags?: TreeNodeFlags): boolean;
export declare function debugLog(text: string): void;
export declare function logText(text: string): void;
/** Create an ImGui context. The returned external value is an opaque handle. */
export declare function createContext(): unknown;
export declare function destroyContext(ctx?: unknown): void;
export declare function getCurrentContext(): unknown;
export declare function setCurrentContext(ctx: unknown): void;
export declare function plotLines(label: string, values: Float32Array, valuesOffset?: number, overlayText?: string | null, scaleMin?: number, scaleMax?: number): void;
export declare function plotHistogram(label: string, values: Float32Array, valuesOffset?: number, overlayText?: string | null, scaleMin?: number, scaleMax?: number): void;
export declare function saveIniSettingsToMemory(): string;
export declare function combo(label: string, currentItem: IntRef, items: StringListRef, popupMaxHeightInItems?: number): boolean;
export declare function comboGetter(label: string, currentItem: IntRef, getter: CallbackRef<(idx: number) => string>, itemsCount: number, popupMaxHeightInItems?: number): boolean;
export declare function listBox(label: string, currentItem: IntRef, items: StringListRef, heightInItems?: number): boolean;
export declare function listBoxGetter(label: string, currentItem: IntRef, getter: CallbackRef<(idx: number) => string>, itemsCount: number, heightInItems?: number): boolean;
export declare function setNextWindowSizeConstraints(sizeMin: Vec2, sizeMax: Vec2, callback?: SizeCallback | null): void;
export declare function inputTextEx(label: string, buf: StringRef, flags?: InputTextFlags, callback?: InputTextCallback | null): boolean;
export declare function inputTextMultilineEx(label: string, buf: StringRef, size?: Vec2 | null, flags?: InputTextFlags, callback?: InputTextCallback | null): boolean;
export declare function inputTextWithHintEx(label: string, hint: string, buf: StringRef, flags?: InputTextFlags, callback?: InputTextCallback | null): boolean;
"""


def _build_synthetic_text_cpp() -> str:
    """Extra registrations appended after the generated InitFuncs body.

    These reopen the same translation unit — they're injected as a second
    registration function called _InitSyntheticFuncs() which is invoked from
    the include-generated funcs_init.h trampoline below.  Actually we just
    append them directly into InitFuncs via a helper string that the caller
    splices into the final file.
    """
    # We return the raw registrations so _build_cpp can splice them in.
    # Caller will append these lines inside the InitFuncs() body.
    return """\

// ── Synthetic text/tooltip wrappers ──────────────────────────────────────────
// Vararg ImGui text functions bound as single-string helpers.

static void _InitSyntheticFuncs(Napi::Env env, Napi::Object exports) {
  exports.Set("text", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_TextUnformatted(_s.c_str());
    return env.Undefined();
  }));
  exports.Set("textColored", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    Vec4* _col = Vec4::Unwrap(info[0].As<Napi::Object>());
    std::string _s = info[1].As<Napi::String>().Utf8Value();
    ImGui_TextColored(_col->Raw(), "%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("textDisabled", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_TextDisabled("%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("textWrapped", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_TextWrapped("%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("labelText", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    std::string _s = info[1].As<Napi::String>().Utf8Value();
    ImGui_LabelText(_label.c_str(), "%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("bulletText", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_BulletText("%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("setTooltip", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_SetTooltip("%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("setItemTooltip", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_SetItemTooltip("%s", _s.c_str());
    return env.Undefined();
  }));
  exports.Set("treeNodeStr", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    return Napi::Boolean::New(env, ImGui_TreeNode(_s.c_str()));
  }));
  exports.Set("treeNodeExStr", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGuiTreeNodeFlags _flags = (info.Length() > 1 && !info[1].IsUndefined())
      ? static_cast<ImGuiTreeNodeFlags>(info[1].As<Napi::Number>().Int32Value()) : 0;
    return Napi::Boolean::New(env, ImGui_TreeNodeEx(_s.c_str(), _flags));
  }));
  exports.Set("logText", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_LogText("%s", _s.c_str());
    return env.Undefined();
  }));
  // ── Context management ────────────────────────────────────────────────────
  exports.Set("createContext", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    ImGuiContext* ctx = ImGui_CreateContext(nullptr);
    return Napi::External<ImGuiContext>::New(env, ctx);
  }));
  exports.Set("destroyContext", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    ImGuiContext* ctx = nullptr;
    if (info.Length() > 0 && !info[0].IsNull() && !info[0].IsUndefined()) {
      ctx = info[0].As<Napi::External<ImGuiContext>>().Data();
    }
    ImGui_DestroyContext(ctx);
    return env.Undefined();
  }));
  exports.Set("getCurrentContext", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    ImGuiContext* ctx = ImGui_GetCurrentContext();
    if (!ctx) return env.Null();
    return Napi::External<ImGuiContext>::New(env, ctx);
  }));
  exports.Set("setCurrentContext", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    ImGuiContext* ctx = info[0].As<Napi::External<ImGuiContext>>().Data();
    ImGui_SetCurrentContext(ctx);
    return env.Undefined();
  }));
  // ── Plot helpers ──────────────────────────────────────────────────────────
  exports.Set("plotLines", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    auto _ta = info[1].As<Napi::Float32Array>();
    const float* _values = _ta.Data();
    int _count = static_cast<int>(_ta.ElementLength());
    int _offset = (info.Length() > 2 && !info[2].IsUndefined()) ? info[2].As<Napi::Number>().Int32Value() : 0;
    std::string _overlay_str;
    const char* _overlay = nullptr;
    if (info.Length() > 3 && !info[3].IsNull() && !info[3].IsUndefined()) {
      _overlay_str = info[3].As<Napi::String>().Utf8Value();
      _overlay = _overlay_str.c_str();
    }
    float _scale_min = (info.Length() > 4 && !info[4].IsUndefined()) ? info[4].As<Napi::Number>().FloatValue() : FLT_MAX;
    float _scale_max = (info.Length() > 5 && !info[5].IsUndefined()) ? info[5].As<Napi::Number>().FloatValue() : FLT_MAX;
    ImGui_PlotLinesEx(_label.c_str(), _values, _count, _offset, _overlay, _scale_min, _scale_max, ImVec2{}, sizeof(float));
    return env.Undefined();
  }));
  exports.Set("plotHistogram", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    auto _ta = info[1].As<Napi::Float32Array>();
    const float* _values = _ta.Data();
    int _count = static_cast<int>(_ta.ElementLength());
    int _offset = (info.Length() > 2 && !info[2].IsUndefined()) ? info[2].As<Napi::Number>().Int32Value() : 0;
    std::string _overlay_str;
    const char* _overlay = nullptr;
    if (info.Length() > 3 && !info[3].IsNull() && !info[3].IsUndefined()) {
      _overlay_str = info[3].As<Napi::String>().Utf8Value();
      _overlay = _overlay_str.c_str();
    }
    float _scale_min = (info.Length() > 4 && !info[4].IsUndefined()) ? info[4].As<Napi::Number>().FloatValue() : FLT_MAX;
    float _scale_max = (info.Length() > 5 && !info[5].IsUndefined()) ? info[5].As<Napi::Number>().FloatValue() : FLT_MAX;
    ImGui_PlotHistogramEx(_label.c_str(), _values, _count, _offset, _overlay, _scale_min, _scale_max, ImVec2{}, sizeof(float));
    return env.Undefined();
  }));
  exports.Set("saveIniSettingsToMemory", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    const char* ini = ImGui_SaveIniSettingsToMemory(nullptr);
    return Napi::String::New(env, ini ? ini : "");
  }));
  // ── debugLog ──────────────────────────────────────────────────────────────
  exports.Set("debugLog", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _s = info[0].As<Napi::String>().Utf8Value();
    ImGui_DebugLog("%s", _s.c_str());
    return env.Undefined();
  }));
  // ── combo ─────────────────────────────────────────────────────────────────
  exports.Set("combo", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    IntRef* _cur = IntRef::Unwrap(info[1].As<Napi::Object>());
    StringListRef* _items = StringListRef::Unwrap(info[2].As<Napi::Object>());
    int _popup = (info.Length() > 3 && !info[3].IsUndefined()) ? info[3].As<Napi::Number>().Int32Value() : -1;
    bool _r = ImGui_ComboCharEx(_label.c_str(), _cur->Ptr(), _items->Data(), _items->Count(), _popup);
    return Napi::Boolean::New(env, _r);
  }));
  // ── comboGetter ───────────────────────────────────────────────────────────
  exports.Set("comboGetter", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    IntRef* _cur = IntRef::Unwrap(info[1].As<Napi::Object>());
    CallbackRef* _cb = CallbackRef::Unwrap(info[2].As<Napi::Object>());
    int _count = info[3].As<Napi::Number>().Int32Value();
    int _popup = (info.Length() > 4 && !info[4].IsUndefined()) ? info[4].As<Napi::Number>().Int32Value() : -1;
    auto _getter = [](void* user_data, int idx) -> const char* {
      CallbackRef* ref = static_cast<CallbackRef*>(user_data);
      Napi::HandleScope scope(ref->Env());
      Napi::Value result = ref->GetCallback().Call({Napi::Number::New(ref->Env(), idx)});
      if (result.IsString()) {
        // NOTE: returned string is temporary; ImGui copies it during the frame
        static thread_local std::string _combo_item;
        _combo_item = result.As<Napi::String>().Utf8Value();
        return _combo_item.c_str();
      }
      return "";
    };
    bool _r = ImGui_ComboCallbackEx(_label.c_str(), _cur->Ptr(), _getter, _cb, _count, _popup);
    return Napi::Boolean::New(env, _r);
  }));
  // ── listBox ───────────────────────────────────────────────────────────────
  exports.Set("listBox", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    IntRef* _cur = IntRef::Unwrap(info[1].As<Napi::Object>());
    StringListRef* _items = StringListRef::Unwrap(info[2].As<Napi::Object>());
    int _h = (info.Length() > 3 && !info[3].IsUndefined()) ? info[3].As<Napi::Number>().Int32Value() : -1;
    bool _r = ImGui_ListBox(_label.c_str(), _cur->Ptr(), _items->Data(), _items->Count(), _h);
    return Napi::Boolean::New(env, _r);
  }));
  // ── listBoxGetter ─────────────────────────────────────────────────────────
  exports.Set("listBoxGetter", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    IntRef* _cur = IntRef::Unwrap(info[1].As<Napi::Object>());
    CallbackRef* _cb = CallbackRef::Unwrap(info[2].As<Napi::Object>());
    int _count = info[3].As<Napi::Number>().Int32Value();
    int _h = (info.Length() > 4 && !info[4].IsUndefined()) ? info[4].As<Napi::Number>().Int32Value() : -1;
    auto _getter = [](void* user_data, int idx) -> const char* {
      CallbackRef* ref = static_cast<CallbackRef*>(user_data);
      Napi::HandleScope scope(ref->Env());
      Napi::Value result = ref->GetCallback().Call({Napi::Number::New(ref->Env(), idx)});
      if (result.IsString()) {
        static thread_local std::string _listbox_item;
        _listbox_item = result.As<Napi::String>().Utf8Value();
        return _listbox_item.c_str();
      }
      return "";
    };
    bool _r = ImGui_ListBoxCallbackEx(_label.c_str(), _cur->Ptr(), _getter, _cb, _count, _h);
    return Napi::Boolean::New(env, _r);
  }));
  // ── setNextWindowSizeConstraints ──────────────────────────────────────────
  exports.Set("setNextWindowSizeConstraints", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    Vec2* _min = Vec2::Unwrap(info[0].As<Napi::Object>());
    Vec2* _max = Vec2::Unwrap(info[1].As<Napi::Object>());
    CallbackRef* _cb = (info.Length() > 2 && !info[2].IsNull() && !info[2].IsUndefined())
        ? CallbackRef::Unwrap(info[2].As<Napi::Object>()) : nullptr;
    auto _custom_cb = [](ImGuiSizeCallbackData* data) {
      CallbackRef* ref = static_cast<CallbackRef*>(data->UserData);
      Napi::HandleScope scope(ref->Env());
      Napi::Object wrapper = SizeCallbackData::NewInstance(ref->Env(), data);
      ref->GetCallback().Call({wrapper});
    };
    ImGui_SetNextWindowSizeConstraints(_min->Raw(), _max->Raw(),
        _cb ? _custom_cb : nullptr, _cb);
    return env.Undefined();
  }));
  // ── inputTextEx ───────────────────────────────────────────────────────────
  exports.Set("inputTextEx", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    StringRef* _buf = StringRef::Unwrap(info[1].As<Napi::Object>());
    ImGuiInputTextFlags _flags = (info.Length() > 2 && !info[2].IsUndefined())
        ? static_cast<ImGuiInputTextFlags>(info[2].As<Napi::Number>().Int32Value()) : 0;
    CallbackRef* _cb = (info.Length() > 3 && !info[3].IsNull() && !info[3].IsUndefined())
        ? CallbackRef::Unwrap(info[3].As<Napi::Object>()) : nullptr;
    auto _input_cb = [](ImGuiInputTextCallbackData* data) -> int {
      CallbackRef* ref = static_cast<CallbackRef*>(data->UserData);
      Napi::HandleScope scope(ref->Env());
      Napi::Object wrapper = InputTextCallbackData::NewInstance(ref->Env(), data);
      Napi::Value result = ref->GetCallback().Call({wrapper});
      if (result.IsNumber()) {
        return result.As<Napi::Number>().Int32Value();
      }
      return 0;
    };
    bool _r = ImGui_InputTextEx(_label.c_str(), _buf->Data(), _buf->Capacity(),
        _flags, _cb ? _input_cb : nullptr, _cb);
    return Napi::Boolean::New(env, _r);
  }));
  // ── inputTextMultilineEx ──────────────────────────────────────────────────
  exports.Set("inputTextMultilineEx", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    StringRef* _buf = StringRef::Unwrap(info[1].As<Napi::Object>());
    ImVec2 _size = ImVec2{};
    if (info.Length() > 2 && !info[2].IsNull() && !info[2].IsUndefined()) {
      Vec2* _sv = Vec2::Unwrap(info[2].As<Napi::Object>());
      _size = _sv->Raw();
    }
    ImGuiInputTextFlags _flags = (info.Length() > 3 && !info[3].IsUndefined())
        ? static_cast<ImGuiInputTextFlags>(info[3].As<Napi::Number>().Int32Value()) : 0;
    CallbackRef* _cb = (info.Length() > 4 && !info[4].IsNull() && !info[4].IsUndefined())
        ? CallbackRef::Unwrap(info[4].As<Napi::Object>()) : nullptr;
    auto _input_cb = [](ImGuiInputTextCallbackData* data) -> int {
      CallbackRef* ref = static_cast<CallbackRef*>(data->UserData);
      Napi::HandleScope scope(ref->Env());
      Napi::Object wrapper = InputTextCallbackData::NewInstance(ref->Env(), data);
      Napi::Value result = ref->GetCallback().Call({wrapper});
      if (result.IsNumber()) {
        return result.As<Napi::Number>().Int32Value();
      }
      return 0;
    };
    bool _r = ImGui_InputTextMultilineEx(_label.c_str(), _buf->Data(), _buf->Capacity(),
        _size, _flags, _cb ? _input_cb : nullptr, _cb);
    return Napi::Boolean::New(env, _r);
  }));
  // ── inputTextWithHintEx ───────────────────────────────────────────────────
  exports.Set("inputTextWithHintEx", Napi::Function::New(env, [](const Napi::CallbackInfo& info) -> Napi::Value {
    Napi::Env env = info.Env();
    std::string _label = info[0].As<Napi::String>().Utf8Value();
    std::string _hint = info[1].As<Napi::String>().Utf8Value();
    StringRef* _buf = StringRef::Unwrap(info[2].As<Napi::Object>());
    ImGuiInputTextFlags _flags = (info.Length() > 3 && !info[3].IsUndefined())
        ? static_cast<ImGuiInputTextFlags>(info[3].As<Napi::Number>().Int32Value()) : 0;
    CallbackRef* _cb = (info.Length() > 4 && !info[4].IsNull() && !info[4].IsUndefined())
        ? CallbackRef::Unwrap(info[4].As<Napi::Object>()) : nullptr;
    auto _input_cb = [](ImGuiInputTextCallbackData* data) -> int {
      CallbackRef* ref = static_cast<CallbackRef*>(data->UserData);
      Napi::HandleScope scope(ref->Env());
      Napi::Object wrapper = InputTextCallbackData::NewInstance(ref->Env(), data);
      Napi::Value result = ref->GetCallback().Call({wrapper});
      if (result.IsNumber()) {
        return result.As<Napi::Number>().Int32Value();
      }
      return 0;
    };
    bool _r = ImGui_InputTextWithHintEx(_label.c_str(), _hint.c_str(),
        _buf->Data(), _buf->Capacity(), _flags, _cb ? _input_cb : nullptr, _cb);
    return Napi::Boolean::New(env, _r);
  }));
}
"""


def _format_type_import(names: set[str], module_path: str) -> str:
  if not names:
    return ""
  sorted_names = sorted(names)
  return f"import type {{ {', '.join(sorted_names)} }} from \"{module_path}\";\n"


def _build_dts(
  func_infos: list[dict],
  struct_type_names: set[str],
  enum_type_names: set[str],
  typedef_type_names: set[str],
) -> str:
  """Build funcs.d.ts content."""
  lines = ["// Auto-generated — do not edit."]
  lines.append(_format_type_import(struct_type_names, "./structs").rstrip())
  lines.append(_format_type_import(enum_type_names, "./enums").rstrip())
  lines.append(_format_type_import(typedef_type_names, "./typedefs").rstrip())
  lines.append(
    'import type { BoolRef, CallbackRef, DoubleRef, FloatRef, IntRef, StringListRef, StringRef } from "../../dts/ref";'
  )
  lines.append("")

  for fi in func_infos:
    visible_args = [
      a for a in fi["args"]
      if not a.get("_absorbed") and a.get("ts_type") is not None
    ]
    param_names = make_unique_ts_identifiers([
      a.get("_name", "arg") for a in visible_args
    ])

    seen_optional = False
    ts_param_tokens = []
    for name, arg in zip(param_names, visible_args):
      is_optional = arg["is_optional"] or seen_optional
      if is_optional:
        seen_optional = True
      ts_param_tokens.append(
        f"{name}{'?' if is_optional else ''}: {arg['ts_type']}"
      )

    ts_params = ", ".join(
      ts_param_tokens
    )
    ts_ret = fi["ret"]["ts_type"]
    lines.append(f"export declare function {fi['js_name']}({ts_params}): {ts_ret};")

  return "\n".join(lines).rstrip() + "\n"


# ─── Main entry point ─────────────────────────────────────────────────────────

def process_functions(
    bindings: dict,
    processed_enums: dict,
    processed_typedefs: dict,
    processed_structs: dict,
) -> None:
    """Generate function wrappers and emit output files."""

    funcs_json = bindings.get("functions", [])

    func_infos = []
    skip_count = 0

    for func in funcs_json:
        info = _resolve_function(func, processed_enums, processed_typedefs, processed_structs)
        if info is None:
            skip_count += 1
            continue
        # Attach argument names for DTS output (skip absorbed entries which have no
        # corresponding JS parameter).
        raw_args = [a for a in func.get("arguments", []) if not a.get("is_instance_pointer")]
        raw_non_absorbed_iter = iter(raw_args)
        for resolved in info["args"]:
            if resolved.get("_absorbed"):
                resolved["_name"] = "_size"  # internal; won't appear in TS
                continue
            raw = next(raw_non_absorbed_iter, None)
            resolved["_name"] = raw["name"] if raw else "arg"
        func_infos.append(info)

    bound = len(func_infos)
    print(f"  [func] Bound {bound} functions, skipped {skip_count}")

    # Write output files
    cpp_path  = GEN_NAPI / "funcs.cpp"
    hdr_path  = GEN_NAPI / "funcs_init.h"
    dts_path  = GEN_DTS  / "funcs.d.ts"

    cpp_path.write_text(_build_cpp(func_infos))
    hdr_path.write_text(_build_init_header())
    struct_type_names = {
      s["cpp_class_name"]
      for s in processed_structs.values()
      if s.get("cpp_class_name")
    }
    enum_type_names = {
      enum_name
      for enum_name in processed_enums.values()
      if enum_name
    }
    typedef_type_names = {
      td["name"]
      for name, td in processed_typedefs.items()
      if td.get("name")
      and name not in processed_enums
      and f"{name}_" not in processed_enums
    }

    dts_path.write_text(
      _build_dts(func_infos, struct_type_names, enum_type_names, typedef_type_names)
      + _SYNTHETIC_TEXT_DTS
    )

    print(f"  [func] Wrote funcs.cpp, funcs_init.h, funcs.d.ts")
