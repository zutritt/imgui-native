"""
Shared argument and return-type resolution utilities.

Used by both func.py (free ImGui_ functions) and struct.py (struct instance
methods) so the type-mapping logic lives in exactly one place.
"""

from __future__ import annotations


# ─── Builtin scalars: (c_type, extract_expr, ts_type) ────────────────────────
#
# {v} = Napi::Value expression to read from
# {r} = C++ result variable name (for return)

_BUILTIN_ARG = {
    #           c_type         extract snippet               ts_type
    "bool":          ("bool",          "{v}.As<Napi::Boolean>().Value()",           "boolean"),
    "float":         ("float",         "{v}.As<Napi::Number>().FloatValue()",        "number"),
    "double":        ("double",        "{v}.As<Napi::Number>().DoubleValue()",       "number"),
    "int":           ("int",           "{v}.As<Napi::Number>().Int32Value()",        "number"),
    "unsigned_int":  ("unsigned int",  "{v}.As<Napi::Number>().Uint32Value()",       "number"),
    "unsigned_short":("unsigned short","{v}.As<Napi::Number>().Uint32Value()",       "number"),
    "short":         ("short",         "{v}.As<Napi::Number>().Int32Value()",        "number"),
    "unsigned_char": ("unsigned char", "{v}.As<Napi::Number>().Uint32Value()",       "number"),
    "char":          ("char",          "static_cast<char>({v}.As<Napi::Number>().Int32Value())", "number"),
}

_BUILTIN_RET = {
    #           napi_wrap expr                           ts_type
    "bool":               ("Napi::Boolean::New(env, {r})",                              "boolean"),
    "float":              ("Napi::Number::New(env, {r})",                               "number"),
    "double":             ("Napi::Number::New(env, {r})",                               "number"),
    "int":                ("Napi::Number::New(env, {r})",                               "number"),
    "unsigned_int":       ("Napi::Number::New(env, {r})",                               "number"),
    "unsigned_short":     ("Napi::Number::New(env, static_cast<uint32_t>({r}))",        "number"),
    "short":              ("Napi::Number::New(env, static_cast<int32_t>({r}))",         "number"),
    "unsigned_char":      ("Napi::Number::New(env, static_cast<uint32_t>({r}))",        "number"),
    "char":               ("Napi::Number::New(env, static_cast<int32_t>({r}))",         "number"),
    "long_long":          ("Napi::BigInt::New(env, static_cast<int64_t>({r}))",         "bigint"),
    "unsigned_long_long": ("Napi::BigInt::New(env, static_cast<uint64_t>({r}))",        "bigint"),
}

# Mutable pointer output-param builtins → ref wrapper class names
# Tuple: (wrapper_cls, c_type, header, pass_expr_override_or_None)
_MUTABLE_PTR_WRAPPERS = {
    "bool":          ("BoolRef",   "bool",         "../../ref/bool.h",   None),
    "int":           ("IntRef",    "int32_t",      "../../ref/int.h",    None),
    "float":         ("FloatRef",  "float",        "../../ref/float.h",  None),
    "double":        ("DoubleRef", "double",       "../../ref/double.h", None),
    # unsigned int* — share IntRef but reinterpret the pointer
    "unsigned_int":  ("IntRef",    "int32_t",      "../../ref/int.h",    "reinterpret_cast<unsigned int*>({var}->Ptr())"),
}


def _default_value_cpp(default_val: str, builtin_type: str) -> str:
    """Convert a JSON default_value string to a safe C++ literal."""
    if default_val in ("NULL", "nullptr"):
        return "0"
    if default_val == "true":
        return "true"
    if default_val == "false":
        return "false"
    # Numeric literals (e.g. "0", "1", "-1", "0.0f")
    return default_val


def _enum_ts_type(target: str, processed_enums: dict) -> str | None:
    """Return the generated TS enum type name for a C enum/enum-typedef target."""
    if target in processed_enums:
        return processed_enums[target]
    underscored = f"{target}_"
    if underscored in processed_enums:
        return processed_enums[underscored]
    return None


def _resolve_arg(
    arg: dict,
    idx: int,
    processed_enums: dict,
    processed_typedefs: dict,
    processed_structs: dict,
) -> dict | None:
    """Resolve one function argument to its C++ extraction code.

    Returns None when the argument type is not yet supported (caller should
    skip the whole function).

    Result keys:
      pre_lines     list[str]  — C++ declarations before the call (may be empty)
      pass_expr     str        — expression passed to the C function
      ts_type       str        — TypeScript type
      is_optional   bool       — True if arg has a default value in C++
      extra_includes list[str] — header files needed
    """
    name = arg["name"]
    has_default = "default_value" in arg
    default_val  = arg.get("default_value", "")
    desc = arg["type"]["description"]
    kind = desc["kind"]
    idx_expr = f"info[{idx}]"
    var = f"_{name}"

    # ── Builtin scalars ──────────────────────────────────────────────────────
    if kind == "Builtin":
        bt = desc.get("builtin_type")
        if bt == "void":
            return None  # void arg makes no sense
        # BigInt (int64_t / uint64_t) — needs lossless bool helper
        if bt in ("long_long", "unsigned_long_long"):
            cpp_type = "int64_t" if bt == "long_long" else "uint64_t"
            method    = "Int64Value" if bt == "long_long" else "Uint64Value"
            if has_default:
                cpp_default = default_val if default_val not in ("NULL", "nullptr") else "0"
                pre = [
                    f"  bool _ll_ok_{name};",
                    f"  {cpp_type} {var} = (info.Length() > {idx} && !{idx_expr}.IsUndefined()) "
                    f"? {idx_expr}.As<Napi::BigInt>().{method}(&_ll_ok_{name}) "
                    f": static_cast<{cpp_type}>({cpp_default});",
                ]
            else:
                pre = [
                    f"  bool _ll_ok_{name};",
                    f"  {cpp_type} {var} = {idx_expr}.As<Napi::BigInt>().{method}(&_ll_ok_{name});",
                ]
            return {
                "pre_lines": pre,
                "pass_expr": var,
                "ts_type": "bigint",
                "is_optional": has_default,
                "extra_includes": [],
            }
        entry = _BUILTIN_ARG.get(bt)
        if entry is None:
            return None
        c_type, extract, ts = entry
        if has_default:
            cpp_default = _default_value_cpp(default_val, bt)
            pre = [
                f"  {c_type} {var} = (info.Length() > {idx} && !{idx_expr}.IsUndefined()) "
                f"? {extract.replace('{v}', idx_expr)} : {cpp_default};"
            ]
        else:
            pre = [f"  {c_type} {var} = {extract.replace('{v}', idx_expr)};"]
        return {
            "pre_lines": pre,
            "pass_expr": var,
            "ts_type": ts,
            "is_optional": has_default,
            "extra_includes": [],
        }

    # ── User: enum, typedef, or struct ───────────────────────────────────────
    if kind == "User":
        target = desc["name"]

        # size_t is a C stdlib type not present in the imgui typedef table;
        # treat as an unsigned number (safe up to 2^32 via Uint32Value).
        if target == "size_t":
            pre = [f"  size_t {var} = static_cast<size_t>({idx_expr}.As<Napi::Number>().Uint32Value());"]
            return {
                "pre_lines": pre,
                "pass_expr": var,
                "ts_type": "number",
                "is_optional": has_default,
                "extra_includes": [],
            }

        # Enum (bare value, not pointer)
        enum_ts_type = _enum_ts_type(target, processed_enums)
        if enum_ts_type is not None:
            if has_default:
                cpp_default = default_val if default_val != "NULL" else "0"
                pre = [
                    f"  {target} {var} = (info.Length() > {idx} && !{idx_expr}.IsUndefined()) "
                    f"? static_cast<{target}>({idx_expr}.As<Napi::Number>().Int32Value()) "
                    f": static_cast<{target}>({cpp_default});"
                ]
            else:
                pre = [
                    f"  {target} {var} = static_cast<{target}>({idx_expr}.As<Napi::Number>().Int32Value());"
                ]
            return {
                "pre_lines": pre,
                "pass_expr": var,
                "ts_type": enum_ts_type,
                "is_optional": has_default,
                "extra_includes": [],
            }

        # Typedef → builtin
        if target in processed_typedefs:
            td = processed_typedefs[target]
            bt = td.get("builtin_type", "")
            # BigInt typedefs (ImS64, ImU64, ImGuiSelectionUserData, etc.)
            if bt in ("long_long", "unsigned_long_long"):
                cpp_type = "int64_t" if bt == "long_long" else "uint64_t"
                method    = "Int64Value" if bt == "long_long" else "Uint64Value"
                if has_default:
                    cpp_default = default_val if default_val not in ("NULL", "nullptr") else "0"
                    pre = [
                        f"  bool _ll_ok_{name};",
                        f"  {target} {var} = (info.Length() > {idx} && !{idx_expr}.IsUndefined()) "
                        f"? static_cast<{target}>({idx_expr}.As<Napi::BigInt>().{method}(&_ll_ok_{name})) "
                        f": static_cast<{target}>({cpp_default});",
                    ]
                else:
                    pre = [
                        f"  bool _ll_ok_{name};",
                        f"  {target} {var} = static_cast<{target}>({idx_expr}.As<Napi::BigInt>().{method}(&_ll_ok_{name}));",
                    ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "bigint",
                    "is_optional": has_default,
                    "extra_includes": [],
                }
            entry = _BUILTIN_ARG.get(bt)
            if entry is None:
                return None
            c_type, extract, ts = entry
            if has_default:
                cpp_default = _default_value_cpp(default_val, bt)
                pre = [
                    f"  {target} {var} = (info.Length() > {idx} && !{idx_expr}.IsUndefined()) "
                    f"? static_cast<{target}>({extract.replace('{v}', idx_expr)}) : static_cast<{target}>({cpp_default});"
                ]
            else:
                pre = [
                    f"  {target} {var} = static_cast<{target}>({extract.replace('{v}', idx_expr)});"
                ]
            return {
                "pre_lines": pre,
                "pass_expr": var,
                "ts_type": ts,
                "is_optional": has_default,
                "extra_includes": [],
            }

        # Struct (by value — only valid for by-value wrappers like ImVec2)
        if target in processed_structs:
            s = processed_structs[target]
            if s.get("is_by_ref"):
                # By-ref structs should not appear as by-value args. Skip.
                return None
            wrapper = s["cpp_class_name"]
            file_base = s["file_base"]
            c_struct = s["c_struct_name"]
            pre = [
                f"  {wrapper}* _ref_{name} = (!{idx_expr}.IsUndefined() && {idx_expr}.IsObject()) ? {wrapper}::Unwrap({idx_expr}.As<Napi::Object>()) : nullptr;",
                f"  {c_struct} {var} = _ref_{name} ? _ref_{name}->Raw() : {c_struct}{{}};",
            ]
            return {
                "pre_lines": pre,
                "pass_expr": var,
                "ts_type": wrapper,
                "is_optional": has_default,
                "extra_includes": [f"{file_base}.h"],
            }

        return None  # Unknown user type

    # ── Pointer ──────────────────────────────────────────────────────────────
    if kind == "Pointer":
        inner = desc.get("inner_type", {})
        iname = inner.get("name", "")
        ikind = inner.get("kind", "")
        iscs  = inner.get("storage_classes", [])

        # Pointer-to-pointer: skip
        if ikind == "Pointer":
            return None

        # const char* → string input
        if ikind == "Builtin" and inner.get("builtin_type") == "char" and "const" in iscs:
            if has_default and default_val == "NULL":
                # Optional nullable string
                pre = [
                    f"  const char* {var} = nullptr;",
                    f"  std::string _str_{name};",
                    f"  if (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) {{",
                    f"    _str_{name} = {idx_expr}.As<Napi::String>().Utf8Value();",
                    f"    {var} = _str_{name}.c_str();",
                    f"  }}",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "string | null",
                    "is_optional": True,
                    "extra_includes": [],
                }
            else:
                pre = [
                    f"  std::string _str_{name} = {idx_expr}.As<Napi::String>().Utf8Value();",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": f"_str_{name}.c_str()",
                    "ts_type": "string",
                    "is_optional": False,
                    "extra_includes": [],
                }

        # Mutable char* (non-const) — writable string buffer via StringRef.
        # The following size_t arg (buf_size) is automatically absorbed: the
        # caller loop injects StringRef::Capacity() for it and removes it from
        # the visible JS parameter list.
        if ikind == "Builtin" and inner.get("builtin_type") == "char" and "const" not in iscs:
            pre = [
                f"  StringRef* {var} = StringRef::Unwrap({idx_expr}.As<Napi::Object>());",
            ]
            return {
                "pre_lines": pre,
                "pass_expr": f"{var}->Data()",
                "ts_type": "StringRef",
                "is_optional": False,
                "extra_includes": ["../../ref/string.h"],
                "absorbs_next_size": True,
                "absorbed_size_expr": f"{var}->Capacity()",
            }

        # void* or const void* → Napi::External<void> (opaque handle)
        if ikind == "Builtin" and inner.get("builtin_type") == "void":
            nullable = has_default and default_val in ("NULL", "nullptr")
            if nullable:
                pre = [
                    f"  void* {var} = nullptr;",
                    f"  if (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) {{" ,
                    f"    {var} = {idx_expr}.As<Napi::External<void>>().Data();",
                    f"  }}",
                ]
                ts = "unknown | null"
            else:
                pre = [f"  void* {var} = {idx_expr}.IsNull() || {idx_expr}.IsUndefined() ? nullptr : {idx_expr}.As<Napi::External<void>>().Data();"]
                ts = "unknown"
            return {
                "pre_lines": pre,
                "pass_expr": var,   # C++ void* implicitly converts to const void*
                "ts_type": ts,
                "is_optional": nullable,
                "extra_includes": [],
            }

        # Mutable builtin* → ref wrapper (output parameter)
        if ikind == "Builtin" and "const" not in iscs:
            bt = inner.get("builtin_type", "")
            wrapper_info = _MUTABLE_PTR_WRAPPERS.get(bt)
            if wrapper_info is None:
                return None
            wrapper_cls, _, hdr, pass_expr_tpl = wrapper_info
            nullable = has_default and default_val == "NULL"
            if nullable:
                pre = [
                    f"  {wrapper_cls}* {var} = (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) "
                    f"? {wrapper_cls}::Unwrap({idx_expr}.As<Napi::Object>()) : nullptr;"
                ]
                ts = f"{wrapper_cls} | null"
            else:
                pre = [
                    f"  {wrapper_cls}* {var} = {wrapper_cls}::Unwrap({idx_expr}.As<Napi::Object>());"
                ]
                ts = wrapper_cls
            if pass_expr_tpl is not None:
                pass_expr = pass_expr_tpl.replace("{var}", var) if "{var}" in pass_expr_tpl else pass_expr_tpl
                pass_expr = f"{var} ? {pass_expr} : nullptr"
            else:
                pass_expr = f"{var} ? {var}->Ptr() : nullptr"
            return {
                "pre_lines": pre,
                "pass_expr": pass_expr,
                "ts_type": ts,
                "is_optional": nullable,
                "extra_includes": [hdr],
            }

        # const builtin* (read-only data pointer)
        # If nullable (default=NULL), accept an optional TypedArray | null
        if ikind == "Builtin" and "const" in iscs:
            ibt = inner.get("builtin_type", "")
            nullable = has_default and default_val in ("NULL", "nullptr")
            if nullable and ibt == "float":
                pre = [
                    f"  float* {var} = nullptr;",
                    f"  Napi::Float32Array _ta_{name};",
                    f"  if (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) {{",
                    f"    if (!{idx_expr}.IsTypedArray()) {{ Napi::TypeError::New(env, \"Expected Float32Array\").ThrowAsJavaScriptException(); return env.Null(); }}",
                    f"    _ta_{name} = {idx_expr}.As<Napi::Float32Array>();",
                    f"    {var} = _ta_{name}.Data();",
                    f"  }}",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Float32Array | null",
                    "is_optional": True,
                    "extra_includes": [],
                }
            if nullable and ibt in ("int", "short"):
                pre = [
                    f"  int* {var} = nullptr;",
                    f"  Napi::Int32Array _ta_{name};",
                    f"  if (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) {{",
                    f"    if (!{idx_expr}.IsTypedArray()) {{ Napi::TypeError::New(env, \"Expected Int32Array\").ThrowAsJavaScriptException(); return env.Null(); }}",
                    f"    _ta_{name} = {idx_expr}.As<Napi::Int32Array>();",
                    f"    {var} = reinterpret_cast<int*>(_ta_{name}.Data());",
                    f"  }}",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Int32Array | null",
                    "is_optional": True,
                    "extra_includes": [],
                }
            # Non-nullable const float* → Float32Array
            if not nullable and ibt == "float":
                pre = [
                    f"  auto _ta_{name} = {idx_expr}.As<Napi::Float32Array>();",
                    f"  const float* {var} = _ta_{name}.Data();",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Float32Array",
                    "is_optional": False,
                    "extra_includes": [],
                }
            # Non-nullable const int*/short* → Int32Array
            if not nullable and ibt in ("int", "short"):
                pre = [
                    f"  auto _ta_{name} = {idx_expr}.As<Napi::Int32Array>();",
                    f"  const int* {var} = reinterpret_cast<const int*>(_ta_{name}.Data());",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Int32Array",
                    "is_optional": False,
                    "extra_includes": [],
                }
            return None

        # Pointer to User struct (by-ref or by-value wrapper)
        if ikind == "User":
            if iname in processed_structs:
                s = processed_structs[iname]
                wrapper = s["cpp_class_name"]
                file_base = s["file_base"]
                is_by_ref = s.get("is_by_ref", False)
                nullable = has_default and default_val in ("NULL", "nullptr")
                if nullable:
                    pre = [
                        f"  {wrapper}* {var} = (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) "
                        f"? {wrapper}::Unwrap({idx_expr}.As<Napi::Object>()) : nullptr;"
                    ]
                    ts = f"{wrapper} | null"
                else:
                    pre = [
                        f"  {wrapper}* {var} = {wrapper}::Unwrap({idx_expr}.As<Napi::Object>());"
                    ]
                    ts = wrapper
                # By-ref: Raw() returns T* (pointer). By-value: Raw() returns T& (ref),
                # so take its address to get the required pointer.
                raw_expr = f"{var}->Raw()" if is_by_ref else f"&{var}->Raw()"
                return {
                    "pre_lines": pre,
                    "pass_expr": f"{var} ? {raw_expr} : nullptr",
                    "ts_type": ts,
                    "is_optional": nullable,
                    "extra_includes": [f"{file_base}.h"],
                }
            # Pointer to unknown User type — check if it's a typedef to a builtin (e.g. const ImWchar*)
            if iname in processed_typedefs:
                td = processed_typedefs[iname]
                bt = td.get("builtin_type", "")
                # const ImWchar* and similar → External<void> (opaque passthrough)
                if bt in ("unsigned_short", "unsigned_int", "unsigned_char"):
                    nullable = has_default and default_val in ("NULL", "nullptr")
                    if nullable:
                        pre = [
                            f"  void* {var} = nullptr;",
                            f"  if (info.Length() > {idx} && !{idx_expr}.IsNull() && !{idx_expr}.IsUndefined()) {{",
                            f"    {var} = {idx_expr}.As<Napi::External<void>>().Data();",
                            f"  }}",
                        ]
                        ts = "unknown | null"
                    else:
                        pre = [f"  void* {var} = {idx_expr}.As<Napi::External<void>>().Data();"]
                        ts = "unknown"
                    return {
                        "pre_lines": pre,
                        "pass_expr": f"static_cast<const {iname}*>({var})",
                        "ts_type": ts,
                        "is_optional": nullable,
                        "extra_includes": [],
                    }
            # Truly unknown User pointer → skip
            return None

    # ── Array: float[N] / int[N] — accept TypedArray (zero-index, mutable) ─────
    if kind == "Array":
        inner = desc.get("inner_type", {})
        ikind = inner.get("kind", "")
        if ikind == "Builtin":
            ibt = inner.get("builtin_type", "")
            if ibt == "float":
                pre = [
                    f"  if (!{idx_expr}.IsTypedArray()) {{ Napi::TypeError::New(env, \"Expected Float32Array\").ThrowAsJavaScriptException(); return env.Null(); }}",
                    f"  auto _ta_{name} = {idx_expr}.As<Napi::Float32Array>();",
                    f"  float* {var} = _ta_{name}.Data();",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Float32Array",
                    "is_optional": False,
                    "extra_includes": [],
                }
            if ibt in ("int", "short"):
                pre = [
                    f"  if (!{idx_expr}.IsTypedArray()) {{ Napi::TypeError::New(env, \"Expected Int32Array\").ThrowAsJavaScriptException(); return env.Null(); }}",
                    f"  auto _ta_{name} = {idx_expr}.As<Napi::Int32Array>();",
                    f"  int* {var} = reinterpret_cast<int*>(_ta_{name}.Data());",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Int32Array",
                    "is_optional": False,
                    "extra_includes": [],
                }
            if ibt in ("unsigned_int", "unsigned_short", "unsigned_char"):
                pre = [
                    f"  if (!{idx_expr}.IsTypedArray()) {{ Napi::TypeError::New(env, \"Expected Uint32Array\").ThrowAsJavaScriptException(); return env.Null(); }}",
                    f"  auto _ta_{name} = {idx_expr}.As<Napi::Uint32Array>();",
                    f"  unsigned int* {var} = reinterpret_cast<unsigned int*>(_ta_{name}.Data());",
                ]
                return {
                    "pre_lines": pre,
                    "pass_expr": var,
                    "ts_type": "Uint32Array",
                    "is_optional": False,
                    "extra_includes": [],
                }
        return None  # Unsupported array inner type

    # Type (function ptr) → skip
    return None


def _resolve_return(
    return_type: dict,
    processed_enums: dict,
    processed_typedefs: dict,
    processed_structs: dict,
) -> dict | None:
    """Resolve the C++ return type to NAPI wrapping code.

    Returns None if the return type is not yet supported.

    Result keys:
      call_prefix   str        — C++ lhs before the function call  ("" for void)
      return_stmt   str        — return statement (complete line)
      ts_type       str        — TypeScript return type
      extra_includes list[str] — header files needed
    """
    desc = return_type["description"]
    kind = desc["kind"]

    # ── void ─────────────────────────────────────────────────────────────────
    if kind == "Builtin":
        bt = desc.get("builtin_type")
        if bt == "void":
            return {
                "call_prefix": "",
                "return_stmt": "  return env.Undefined();",
                "ts_type": "void",
                "extra_includes": [],
            }
        entry = _BUILTIN_RET.get(bt)
        if entry is None:
            return None
        napi_wrap, ts = entry
        return {
            "call_prefix": f"  {return_type['declaration']} _result = ",
            "return_stmt": f"  return {napi_wrap.replace('{r}', '_result')};",
            "ts_type": ts,
            "extra_includes": [],
        }

    # ── User (typedef or enum → number, ImVec2 → Vec2, etc.) ─────────────────
    if kind == "User":
        target = desc["name"]

        enum_ts_type = _enum_ts_type(target, processed_enums)
        if enum_ts_type is not None:
            return {
                "call_prefix": f"  {target} _result = ",
                "return_stmt":  "  return Napi::Number::New(env, static_cast<int32_t>(_result));",
                "ts_type": enum_ts_type,
                "extra_includes": [],
            }

        if target in processed_typedefs:
            td = processed_typedefs[target]
            bt = td.get("builtin_type", "")
            entry = _BUILTIN_RET.get(bt)
            if entry is None:
                return None
            napi_wrap, ts = entry
            return {
                "call_prefix": f"  {target} _result = ",
                "return_stmt": f"  return {napi_wrap.replace('{r}', '_result')};",
                "ts_type": ts,
                "extra_includes": [],
            }

        if target in processed_structs:
            s = processed_structs[target]
            if s.get("is_by_ref"):
                return None  # by-ref structs not returned by value
            wrapper = s["cpp_class_name"]
            file_base = s["file_base"]
            c_struct = s["c_struct_name"]
            return {
                "call_prefix": f"  {c_struct} _result = ",
                "return_stmt": f"  return {wrapper}::NewInstance(env, _result);",
                "ts_type": wrapper,
                "extra_includes": [f"{file_base}.h"],
            }

        return None

    # ── Pointer returns ──────────────────────────────────────────────────────
    if kind == "Pointer":
        inner = desc.get("inner_type", {})
        ikind = inner.get("kind", "")
        iname = inner.get("name", "")
        iscs  = inner.get("storage_classes", [])

        # const char* → JS string
        if ikind == "Builtin" and inner.get("builtin_type") == "char" and "const" in iscs:
            return {
                "call_prefix": "  const char* _result = ",
                "return_stmt": "  return _result ? Napi::String::New(env, _result) : env.Null();",
                "ts_type": "string | null",
                "extra_includes": [],
            }

        # Pointer to a known struct → wrapped reference
        if ikind == "User" and iname in processed_structs:
            s = processed_structs[iname]
            wrapper = s["cpp_class_name"]
            file_base = s["file_base"]
            c_struct = s["c_struct_name"]
            is_const = "const" in iscs
            c_decl = return_type["declaration"]  # e.g. "const ImGuiPayload*"
            if s.get("is_by_ref"):
                # Borrowed pointer: pass directly to NewInstance (const_cast if needed)
                unwrap = f"const_cast<{c_struct}*>(_result)" if is_const else "_result"
                return {
                    "call_prefix": f"  {c_decl} _result = ",
                    "return_stmt": f"  return _result ? {wrapper}::NewInstance(env, {unwrap}) : env.Null();",
                    "ts_type": f"{wrapper} | null",
                    "extra_includes": [f"{file_base}.h"],
                }
            else:
                # By-value struct: copy via dereference
                return {
                    "call_prefix": f"  {c_decl} _result = ",
                    "return_stmt": f"  return _result ? {wrapper}::NewInstance(env, *_result) : env.Null();",
                    "ts_type": f"{wrapper} | null",
                    "extra_includes": [f"{file_base}.h"],
                }

        # void* → External<void>
        if ikind == "Builtin" and inner.get("builtin_type") == "void":
            c_decl = return_type["declaration"]
            return {
                "call_prefix": f"  {c_decl} _result = ",
                "return_stmt": "  return _result ? Napi::External<void>::New(env, const_cast<void*>(_result)) : env.Null();",
                "ts_type": "unknown | null",
                "extra_includes": [],
            }

        # const ImWchar* → External<void> (opaque glyph range data)
        if ikind == "User" and iname in processed_typedefs:
            td = processed_typedefs[iname]
            bt = td.get("builtin_type", "")
            if bt in ("unsigned_short", "unsigned_int"):
                c_decl = return_type["declaration"]
                return {
                    "call_prefix": f"  {c_decl} _result = ",
                    "return_stmt": f"  return _result ? Napi::External<void>::New(env, const_cast<void*>(static_cast<const void*>(_result))) : env.Null();",
                    "ts_type": "unknown | null",
                    "extra_includes": [],
                }

        # Unrecognised pointer → skip
        return None

    return None
