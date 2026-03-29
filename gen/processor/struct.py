"""
Generates NAPI C++ wrapper classes and TypeScript declarations for ImGui structs.

Phase 1: by-value structs (ImVec2, ImVec4, ImTextureRef, ImColor).
  - Wrapper owns the C struct by value; constructor accepts scalar fields.

Phase 2: by-reference structs (everything else).
  - Wrapper holds a borrowed T* set by NewInstance; no C++ constructor args.
  - Pointer / array / function-pointer fields are skipped in this phase.

Per struct this emits:
  lib/gen/napi/<file>.h    — NAPI wrapper class declaration
  lib/gen/napi/<file>.cpp  — NAPI wrapper class implementation

And one combined file for TypeScript consumers:
  lib/gen/dts/structs.d.ts

Also emits an init shim:
  lib/gen/napi/structs_init.h
  lib/gen/napi/structs_init.cpp
These let module.cpp call a single InitStructs() rather than knowing about
every individual wrapper.
"""

import re
from config import GEN_DTS, GEN_NAPI
from processor.resolve import _resolve_arg, _resolve_return
from processor.ts_names import make_unique_ts_identifiers

# ─────────────────────────────────────────────────────────────────────────────
# Builtin type → NAPI conversion table
#
# Each entry: (getter_body_template, setter_body_template, ts_type)
#
# {ref}   is substituted with the field-access prefix ("this->value." for
#         by-value structs, "this->ptr->" for by-reference structs).
# {field} is substituted with the actual C++ field name.
# Getter bodies are complete return statements.
# Setter bodies may be multiple statements (for BigInt which needs `lossless`).
# ─────────────────────────────────────────────────────────────────────────────

BUILTIN_TYPE_MAP = {
    "bool": (
        "return Napi::Boolean::New(env, {ref}{field});",
        "{ref}{field} = value.As<Napi::Boolean>().Value();",
        "boolean",
    ),
    "float": (
        "return Napi::Number::New(env, {ref}{field});",
        "{ref}{field} = value.As<Napi::Number>().FloatValue();",
        "number",
    ),
    "double": (
        "return Napi::Number::New(env, {ref}{field});",
        "{ref}{field} = value.As<Napi::Number>().DoubleValue();",
        "number",
    ),
    "int": (
        "return Napi::Number::New(env, {ref}{field});",
        "{ref}{field} = value.As<Napi::Number>().Int32Value();",
        "number",
    ),
    "unsigned_int": (
        "return Napi::Number::New(env, {ref}{field});",
        "{ref}{field} = value.As<Napi::Number>().Uint32Value();",
        "number",
    ),
    "unsigned_short": (
        "return Napi::Number::New(env, static_cast<uint32_t>({ref}{field}));",
        "{ref}{field} = static_cast<uint16_t>(value.As<Napi::Number>().Uint32Value());",
        "number",
    ),
    "short": (
        "return Napi::Number::New(env, static_cast<int32_t>({ref}{field}));",
        "{ref}{field} = static_cast<int16_t>(value.As<Napi::Number>().Int32Value());",
        "number",
    ),
    "unsigned_char": (
        "return Napi::Number::New(env, static_cast<uint32_t>({ref}{field}));",
        "{ref}{field} = static_cast<uint8_t>(value.As<Napi::Number>().Uint32Value());",
        "number",
    ),
    "char": (
        "return Napi::Number::New(env, static_cast<int32_t>({ref}{field}));",
        "{ref}{field} = static_cast<char>(value.As<Napi::Number>().Int32Value());",
        "number",
    ),
    "long_long": (
        "return Napi::BigInt::New(env, static_cast<int64_t>({ref}{field}));",
        # Single-line block so this stays valid regardless of call-site indentation.
        "{ bool lossless; {ref}{field} = static_cast<int64_t>(value.As<Napi::BigInt>().Int64Value(&lossless)); }",
        "bigint",
    ),
    "unsigned_long_long": (
        "return Napi::BigInt::New(env, static_cast<uint64_t>({ref}{field}));",
        "{ bool lossless; {ref}{field} = static_cast<uint64_t>(value.As<Napi::BigInt>().Uint64Value(&lossless)); }",
        "bigint",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Naming helpers
# ─────────────────────────────────────────────────────────────────────────────

def _strip_imgui_prefix(name: str) -> str:
    """Remove the ImGui/Im prefix for ergonomic JS-facing class names.

    ImGui follows the convention Name → ImGuiName or ImName.
    We remove those so users write `Vec2` instead of `ImVec2`.

    ImVector_ImFoo → FooArray  (generic container instantiation)
    """
    if name.startswith("ImVector_"):
        elem = name.removeprefix("ImVector_")
        if elem.startswith("ImGui"):
            elem = elem.removeprefix("ImGui")
        elif elem.startswith("Im"):
            elem = elem.removeprefix("Im")
        # Capitalise first letter in case elem was e.g. "char" or "float"
        elem = elem[0].upper() + elem[1:] if elem else elem
        return elem + "Array"
    if name.startswith("ImGui"):
        return name.removeprefix("ImGui")
    if name.startswith("Im"):
        return name.removeprefix("Im")
    return name


def _to_js_property_name(cpp_name: str) -> str:
    """Convert a C++ field name to a camelCase JS property name.

    ImGui uses a leading underscore to mark fields that are technically public
    but considered implementation details (e.g. _TexData, _TexID). We strip
    those underscores and lowercase the first character to produce valid
    camelCase identifiers.
    """
    cleaned = cpp_name.lstrip("_")
    if not cleaned:
        return cpp_name
    return cleaned[0].lower() + cleaned[1:]


def _to_file_base_name(class_name: str) -> str:
    """Convert a PascalCase class name to a snake_case file base name.

    E.g. "Vec2" → "vec2", "TextureRef" → "texture_ref".
    """
    return re.sub(r"(?<=[a-z])(?=[A-Z])", "_", class_name).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Field resolution
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_field(
    field: dict,
    processed_enums: dict,
    processed_typedefs: dict,
    processed_structs: dict,
    field_ref: str = "this->value.",
    count_values: dict | None = None,
) -> dict | None:
    """Map a JSON struct field to its NAPI binding descriptors.

    Returns a dict with everything the code generator needs to emit a
    getter/setter pair, or None when the field type is not yet supported.

    field_ref is the C++ expression that precedes the field name:
      "this->value."  for by-value wrappers
      "this->ptr->"   for by-reference wrappers

    Result keys:
      cpp_field_name  — original C++ field name (e.g. "x", "_TexID")
      js_name         — camelCase JS property name (e.g. "x", "texID")
      method_suffix   — PascalCase suffix for C++ method names (e.g. "X", "TexID")
      ts_type         — TypeScript type string (e.g. "number", "Vec4")
      getter_body     — C++ code for the body of the Napi::Value getter
      setter_body     — C++ code for the body of the void setter, or None if readonly
      extra_includes  — list of header files the generated .cpp needs (e.g. ["vec4.h"])
      is_scalar       — True when the field maps to a JS primitive (used for
                        deciding whether to expose it as a constructor argument)
      is_readonly     — True when only a getter should be emitted (no setter)
    """
    cpp_field_name = field["name"]
    js_name = _to_js_property_name(cpp_field_name)
    method_suffix = js_name[0].upper() + js_name[1:]
    type_description = field["type"]["description"]
    type_kind = type_description["kind"]

    if field.get("is_internal", False):
        return None

    # ── Builtin: maps directly to a JavaScript primitive ─────────────────────
    if type_kind == "Builtin":
        builtin_type = type_description["builtin_type"]
        mapping = BUILTIN_TYPE_MAP.get(builtin_type)
        if mapping is None:
            print(f"    Skipping '{cpp_field_name}': unmapped builtin type '{builtin_type}'")
            return None

        getter_template, setter_template, ts_type = mapping
        return {
            "cpp_field_name": cpp_field_name,
            "js_name": js_name,
            "method_suffix": method_suffix,
            "ts_type": ts_type,
            "getter_body": getter_template.replace("{ref}", field_ref).replace("{field}", cpp_field_name),
            "setter_body": setter_template.replace("{ref}", field_ref).replace("{field}", cpp_field_name),
            "extra_includes": [],
            "is_scalar": True,
            "is_readonly": False,
        }

    # ── User: a named type — could be enum, typedef chain, or another struct ─
    if type_kind == "User":
        target_name = type_description["name"]

        # Enum values are stored as integers in C++; expose as JS number.
        # ImGui defines enums as `ImGuiDir_` but references them as `ImGuiDir`,
        # so we check both forms.
        is_enum = target_name in processed_enums or f"{target_name}_" in processed_enums
        if is_enum:
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "number",
                "getter_body": f"return Napi::Number::New(env, {field_ref}{cpp_field_name});",
                # C++ enums are distinct types — an explicit cast is required.
                "setter_body": f"{field_ref}{cpp_field_name} = static_cast<{target_name}>(value.As<Napi::Number>().Int32Value());",
                "extra_includes": [],
                "is_scalar": True,
                "is_readonly": False,
            }

        # Typedef chain — resolve through to the underlying builtin type.
        # E.g. ImTextureID → ImU64 → unsigned_long_long → bigint.
        if target_name in processed_typedefs:
            typedef_info = processed_typedefs[target_name]
            builtin_type = typedef_info.get("builtin_type", "<unknown>")
            mapping = BUILTIN_TYPE_MAP.get(builtin_type)
            if mapping is None:
                print(f"    Skipping '{cpp_field_name}': typedef '{target_name}' "
                      f"resolves to unhandled type '{builtin_type}'")
                return None

            getter_template, setter_template, _ = mapping
            # Use the renamed typedef alias in TypeScript for readability;
            # the ts_type in the typedef info is already the stripped alias
            # (e.g. "U64" rather than "bigint").
            ts_type = typedef_info.get("ts_type", mapping[2])
            getter_body = getter_template.replace("{ref}", field_ref).replace("{field}", cpp_field_name)
            setter_body = setter_template.replace("{ref}", field_ref).replace("{field}", cpp_field_name)
            # If the typedef is an enum type (e.g. ImTextureFormat → int), C++ requires
            # an explicit cast when assigning an integer to the named enum type.
            # We always add the cast for integer-based typedefs since it's a no-op for
            # plain `typedef int X` and necessary for `typedef enum {...} X`.
            INTEGER_BUILTINS = {"int", "unsigned_int", "short", "unsigned_short", "char", "unsigned_char"}
            if builtin_type in INTEGER_BUILTINS:
                rhs_start = f"{field_ref}{cpp_field_name} = "
                setter_body = setter_body.replace(
                    rhs_start,
                    f"{rhs_start}static_cast<{target_name}>(",
                    1,
                )
                setter_body = setter_body[:-1] + ");"
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": ts_type,
                "getter_body": getter_body,
                "setter_body": setter_body,
                "extra_includes": [],
                "is_scalar": True,
                "is_readonly": False,
            }

        # Another struct we've already generated a wrapper for.
        if target_name in processed_structs:
            target_struct = processed_structs[target_name]
            wrapper_class = target_struct["cpp_class_name"]
            file_base = target_struct["file_base"]
            is_target_by_ref = target_struct.get("is_by_ref", False)

            if is_target_by_ref:
                # Target is a by-ref struct embedded by value inside the parent.
                # Getter returns a borrowed-pointer wrapper into the parent's memory.
                # Setter is not exposed: you can't sanely replace an embedded by-ref
                # sub-struct from JS.
                getter_body = f"return {wrapper_class}::NewInstance(env, &{field_ref}{cpp_field_name});"
                return {
                    "cpp_field_name": cpp_field_name,
                    "js_name": js_name,
                    "method_suffix": method_suffix,
                    "ts_type": wrapper_class,
                    "getter_body": getter_body,
                    "setter_body": None,
                    "extra_includes": [f"{file_base}.h"],
                    "is_scalar": False,
                    "is_readonly": True,
                }
            else:
                # By-value sub-struct: copy in/out via Unwrap.
                getter_body = f"return {wrapper_class}::NewInstance(env, {field_ref}{cpp_field_name});"
                setter_body = (
                    f"if (!value.IsObject()) {{\n"
                    f'    Napi::TypeError::New(info.Env(), "Expected {wrapper_class}").ThrowAsJavaScriptException();\n'
                    f"    return;\n"
                    f"  }}\n"
                    f"  {wrapper_class}* unwrapped = {wrapper_class}::Unwrap(value.As<Napi::Object>());\n"
                    f"  if (unwrapped == nullptr) {{\n"
                    f'    Napi::TypeError::New(info.Env(), "Expected {wrapper_class}").ThrowAsJavaScriptException();\n'
                    f"    return;\n"
                    f"  }}\n"
                    f"  {field_ref}{cpp_field_name} = unwrapped->Raw();"
                )
                return {
                    "cpp_field_name": cpp_field_name,
                    "js_name": js_name,
                    "method_suffix": method_suffix,
                    "ts_type": wrapper_class,
                    "getter_body": getter_body,
                    "setter_body": setter_body,
                    "extra_includes": [f"{file_base}.h"],
                    "is_scalar": False,
                    "is_readonly": False,
                }

        print(f"    Skipping '{cpp_field_name}': unresolved User type '{target_name}'")
        return None

    # ── Array ─────────────────────────────────────────────────────────────────
    if type_kind == "Array":
        _count_values = count_values or {}
        bounds_str = field.get("array_bounds", "")
        inner = type_description.get("inner_type", {})
        ikind = inner.get("kind", "")

        # Resolve the array bound to a concrete integer
        def _resolve_bound(s: str) -> int | None:
            if s in _count_values:
                return _count_values[s]
            try:
                return int(s)
            except ValueError:
                return None

        n = _resolve_bound(bounds_str)
        if n is None:
            print(f"    Skipping '{cpp_field_name}': unresolvable array bound '{bounds_str}'")
            return None

        # char[N] — fixed string buffer
        if ikind == "Builtin" and inner.get("builtin_type") == "char":
            getter = (
                f"return Napi::String::New(env, {field_ref}{cpp_field_name});"
            )
            setter = (
                f"std::string _s = value.As<Napi::String>().Utf8Value();\n"
                f"  size_t _len = std::min(_s.size(), (size_t)({n} - 1));\n"
                f"  std::memcpy({field_ref}{cpp_field_name}, _s.c_str(), _len);\n"
                f"  {field_ref}{cpp_field_name}[_len] = '\\0';"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "string",
                "getter_body": getter,
                "setter_body": setter,
                "extra_includes": ["<cstring>"],
                "is_scalar": False,
                "is_readonly": False,
            }

        # bool[N] — expose as read-only JS Array
        if ikind == "Builtin" and inner.get("builtin_type") == "bool":
            lines = [
                f"auto _arr = Napi::Array::New(env, {n});",
                f"for (uint32_t i = 0; i < {n}; i++)",
                f"  _arr.Set(i, Napi::Boolean::New(env, {field_ref}{cpp_field_name}[i]));",
                "return _arr;",
            ]
            getter = "\n  ".join(lines)
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "boolean[]",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }

        # float[N] / double[N] — Float32Array / Float64Array copy
        if ikind == "Builtin" and inner.get("builtin_type") in ("float", "double"):
            is_double = inner.get("builtin_type") == "double"
            ta_type = "Float64Array" if is_double else "Float32Array"
            c_type  = "double"       if is_double else "float"
            ts_type = ta_type
            elem_size = f"sizeof({c_type})"
            getter = (
                f"auto _ta = Napi::{ta_type}::New(env, {n});\n"
                f"  std::memcpy(_ta.Data(), &{field_ref}{cpp_field_name}, {n} * {elem_size});\n"
                f"  return _ta;"
            )
            setter = (
                f"auto _ta = value.As<Napi::{ta_type}>();\n"
                f"  std::memcpy(&{field_ref}{cpp_field_name}, _ta.Data(), {n} * {elem_size});"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": ts_type,
                "getter_body": getter,
                "setter_body": setter,
                "extra_includes": ["<cstring>"],
                "is_scalar": False,
                "is_readonly": False,
            }

        # int[N] — Int32Array copy
        if ikind == "Builtin" and inner.get("builtin_type") in ("int", "short", "unsigned_int", "unsigned_short", "unsigned_char"):
            is_signed = inner.get("builtin_type") in ("int", "short")
            ta_type = "Int32Array" if is_signed else "Uint32Array"
            c_type  = "int"        if is_signed else "unsigned int"
            ts_type = ta_type
            getter = (
                f"auto _ta = Napi::{ta_type}::New(env, {n});\n"
                f"  std::memcpy(_ta.Data(), &{field_ref}{cpp_field_name}, {n} * sizeof({c_type}));\n"
                f"  return _ta;"
            )
            setter = (
                f"auto _ta = value.As<Napi::{ta_type}>();\n"
                f"  std::memcpy(&{field_ref}{cpp_field_name}, _ta.Data(), {n} * sizeof({c_type}));"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": ts_type,
                "getter_body": getter,
                "setter_body": setter,
                "extra_includes": ["<cstring>"],
                "is_scalar": False,
                "is_readonly": False,
            }

        # User[N] where inner is a typedef to a builtin (e.g. ImU16[N])
        # Resolve through the typedef chain to get the underlying type.
        if ikind == "User":
            iname = inner.get("name", "")

            # Check if it's a typedef to a builtin first
            if iname in processed_typedefs:
                td = processed_typedefs[iname]
                bt = td.get("builtin_type", "")
                mapping = BUILTIN_TYPE_MAP.get(bt)
                if mapping and bt in ("unsigned_short", "unsigned_char", "unsigned_int"):
                    ta_type = "Uint32Array" if bt == "unsigned_int" else ("Uint16Array" if bt == "unsigned_short" else "Uint8Array")
                    c_type = iname
                    getter = (
                        f"auto _ta = Napi::{ta_type}::New(env, {n});\n"
                        f"  std::memcpy(_ta.Data(), &{field_ref}{cpp_field_name}, {n} * sizeof({c_type}));\n"
                        f"  return _ta;"
                    )
                    setter = (
                        f"auto _ta = value.As<Napi::{ta_type}>();\n"
                        f"  std::memcpy(&{field_ref}{cpp_field_name}, _ta.Data(), {n} * sizeof({c_type}));"
                    )
                    return {
                        "cpp_field_name": cpp_field_name,
                        "js_name": js_name,
                        "method_suffix": method_suffix,
                        "ts_type": ta_type,
                        "getter_body": getter,
                        "setter_body": setter,
                        "extra_includes": ["<cstring>"],
                        "is_scalar": False,
                        "is_readonly": False,
                    }
                elif mapping and bt in ("int", "short"):
                    ta_type = "Int32Array" if bt == "int" else "Int16Array"
                    c_type = iname
                    getter = (
                        f"auto _ta = Napi::{ta_type}::New(env, {n});\n"
                        f"  std::memcpy(_ta.Data(), &{field_ref}{cpp_field_name}, {n} * sizeof({c_type}));\n"
                        f"  return _ta;"
                    )
                    setter = (
                        f"auto _ta = value.As<Napi::{ta_type}>();\n"
                        f"  std::memcpy(&{field_ref}{cpp_field_name}, _ta.Data(), {n} * sizeof({c_type}));"
                    )
                    return {
                        "cpp_field_name": cpp_field_name,
                        "js_name": js_name,
                        "method_suffix": method_suffix,
                        "ts_type": ta_type,
                        "getter_body": getter,
                        "setter_body": setter,
                        "extra_includes": ["<cstring>"],
                        "is_scalar": False,
                        "is_readonly": False,
                    }

            if iname in processed_structs:
                s = processed_structs[iname]
                # Only handle 16-byte (4×float) structs like ImVec4
                elem_size_expr = f"sizeof({iname})"
                total = n
                # Expose as Float32Array of N * (sizeof/4) floats — use raw byte copy
                float_count = f"{total} * (sizeof({iname}) / sizeof(float))"
                getter = (
                    f"uint32_t _nf = {float_count};\n"
                    f"  auto _ta = Napi::Float32Array::New(env, _nf);\n"
                    f"  std::memcpy(_ta.Data(), &{field_ref}{cpp_field_name}, _nf * sizeof(float));\n"
                    f"  return _ta;"
                )
                setter = (
                    f"auto _ta = value.As<Napi::Float32Array>();\n"
                    f"  uint32_t _nf = {float_count};\n"
                    f"  if (_ta.ElementLength() >= _nf)\n"
                    f"    std::memcpy(&{field_ref}{cpp_field_name}, _ta.Data(), _nf * sizeof(float));"
                )
                return {
                    "cpp_field_name": cpp_field_name,
                    "js_name": js_name,
                    "method_suffix": method_suffix,
                    "ts_type": "Float32Array",
                    "getter_body": getter,
                    "setter_body": setter,
                    "extra_includes": ["<cstring>"],
                    "is_scalar": False,
                    "is_readonly": False,
                }
        print(f"    Skipping '{cpp_field_name}': unhandled Array inner type '{ikind}'")
        return None

    # ── Pointer ─────────────────────────────────────────────────────────────
    if type_kind == "Pointer":
        inner = type_description.get("inner_type", {})
        ikind = inner.get("kind", "")
        iname = inner.get("name", "")
        iscs  = inner.get("storage_classes", [])

        # const char* → string getter/setter with ownership map
        if ikind == "Builtin" and inner.get("builtin_type") == "char" and "const" in iscs:
            getter = (
                f"const char* _v = {field_ref}{cpp_field_name};\n"
                f"  return _v ? Napi::String::New(env, _v) : env.Null();"
            )
            setter = (
                f"static std::unordered_map<void*, std::string> _store;\n"
                f"  void* _key = (void*)&{field_ref}{cpp_field_name};\n"
                f"  if (value.IsNull() || value.IsUndefined()) {{\n"
                f"    _store.erase(_key);\n"
                f"    {field_ref}{cpp_field_name} = nullptr;\n"
                f"  }} else {{\n"
                f"    _store[_key] = value.As<Napi::String>().Utf8Value();\n"
                f"    {field_ref}{cpp_field_name} = _store[_key].c_str();\n"
                f"  }}"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "string | null",
                "getter_body": getter,
                "setter_body": setter,
                "extra_includes": ["<string>", "<unordered_map>"],
                "is_scalar": False,
                "is_readonly": False,
            }

        # char* (non-const) → readonly string getter
        if ikind == "Builtin" and inner.get("builtin_type") == "char" and "const" not in iscs:
            getter = (
                f"return {field_ref}{cpp_field_name}\n"
                f"  ? Napi::String::New(env, {field_ref}{cpp_field_name})\n"
                f"  : env.Null();"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "string | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }

        # void* fields named *UserData → skip (reserved for lib callback machinery)
        if ikind == "Builtin" and inner.get("builtin_type") == "void":
            if "UserData" in cpp_field_name or "userData" in cpp_field_name:
                print(f"    Skipping '{cpp_field_name}': void* UserData reserved for lib")
                return None
            # Other void* → readonly External<void>
            getter = (
                f"return {field_ref}{cpp_field_name}\n"
                f"  ? Napi::External<void>::New(env, {field_ref}{cpp_field_name})\n"
                f"  : env.Null();"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "unknown | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }

        # unsigned char* → readonly External<void> (raw pixel data etc.)
        if ikind == "Builtin" and inner.get("builtin_type") == "unsigned_char" and "const" not in iscs:
            getter = (
                f"return {field_ref}{cpp_field_name}\n"
                f"  ? Napi::External<void>::New(env, static_cast<void*>({field_ref}{cpp_field_name}))\n"
                f"  : env.Null();"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "unknown | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }

        # Other non-const builtin pointer (float*, int* etc.) → readonly External<void>
        if ikind == "Builtin" and "const" not in iscs and inner.get("builtin_type") not in ("void", "char", "unsigned_char"):
            getter = (
                f"return {field_ref}{cpp_field_name}\n"
                f"  ? Napi::External<void>::New(env, static_cast<void*>({field_ref}{cpp_field_name}))\n"
                f"  : env.Null();"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "unknown | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }
            getter = (
                f"return {field_ref}{cpp_field_name}\n"
                f"  ? Napi::External<void>::New(env, static_cast<void*>({field_ref}{cpp_field_name}))\n"
                f"  : env.Null();"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "unknown | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }

        # Pointer to a known struct → readonly getter returning NewInstance
        if ikind == "User" and iname in processed_structs:
            s = processed_structs[iname]
            wrapper = s["cpp_class_name"]
            file_base = s["file_base"]
            is_target_by_ref = s.get("is_by_ref", False)
            is_const = "const" in iscs
            if is_target_by_ref:
                cast = f"const_cast<{iname}*>({field_ref}{cpp_field_name})" if is_const else f"{field_ref}{cpp_field_name}"
                getter = f"return {field_ref}{cpp_field_name} ? {wrapper}::NewInstance(env, {cast}) : env.Null();"
            else:
                getter = f"return {field_ref}{cpp_field_name} ? {wrapper}::NewInstance(env, *{field_ref}{cpp_field_name}) : env.Null();"
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": f"{wrapper} | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [f"{file_base}.h"],
                "is_scalar": False,
                "is_readonly": True,
            }

        # Pointer to unknown User type → readonly External<void>
        if ikind == "User":
            is_const = "const" in iscs
            cast_expr = f"const_cast<void*>(static_cast<const void*>({field_ref}{cpp_field_name}))" if is_const else f"static_cast<void*>({field_ref}{cpp_field_name})"
            getter = (
                f"return {field_ref}{cpp_field_name}\n"
                f"  ? Napi::External<void>::New(env, {cast_expr})\n"
                f"  : env.Null();"
            )
            return {
                "cpp_field_name": cpp_field_name,
                "js_name": js_name,
                "method_suffix": method_suffix,
                "ts_type": "unknown | null",
                "getter_body": getter,
                "setter_body": None,
                "extra_includes": [],
                "is_scalar": False,
                "is_readonly": True,
            }

        # Pointer to Pointer → skip
        if ikind == "Pointer":
            print(f"    Skipping '{cpp_field_name}': pointer-to-pointer")
            return None

        print(f"    Skipping '{cpp_field_name}': unhandled Pointer inner '{ikind}'")
        return None

    # Type (function pointer) fields are deferred.
    if type_kind == "Type":
        print(f"    Skipping '{cpp_field_name}': function pointer field")
        return None

    print(f"    Skipping '{cpp_field_name}': unknown kind '{type_kind}'")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Struct method collection
# ─────────────────────────────────────────────────────────────────────────────

def _collect_struct_methods(
    c_struct_name: str,
    all_funcs: list[dict],
    processed_enums: dict,
    processed_typedefs: dict,
    processed_structs: dict,
) -> list[dict]:
    """Find and resolve all C functions that are methods of a given struct.

    Matches functions named ``{c_struct_name}_{MethodName}``.  The first arg
    (marked ``is_instance_pointer``) is skipped; remaining args are resolved
    using the standard _resolve_arg machinery.

    Returns a list of method descriptors (same shape as func_infos in func.py).
    """
    prefix = f"{c_struct_name}_"
    methods: list[dict] = []

    for func in all_funcs:
        c_func_name = func["name"]
        if not c_func_name.startswith(prefix):
            continue
        if func.get("is_internal"):
            continue
        if func.get("is_imstr_helper"):
            continue
        if func.get("is_manual_helper"):
            continue

        method_tail = c_func_name[len(prefix):]
        if not method_tail:
            continue

        cpp_method_name = method_tail                         # keep PascalCase
        js_method_name = method_tail[0].lower() + method_tail[1:]

        raw_args = func.get("arguments", [])
        # Only true instance methods have an is_instance_pointer arg.
        # Static-like factory functions (e.g. ImColor_HSV) have no such arg
        # and must be skipped here.
        if not any(a.get("is_instance_pointer", False) for a in raw_args):
            continue
        non_self_args = [a for a in raw_args if not a.get("is_instance_pointer", False)]

        ret = _resolve_return(
            func["return_type"],
            processed_enums, processed_typedefs, processed_structs,
        )
        if ret is None:
            print(f"  [method] Skip {c_func_name}: unsupported return type "
                  f"{func['return_type']['declaration']!r}")
            continue

        resolved_args: list[dict] = []
        all_includes: set[str] = set(ret["extra_includes"])
        skip = False
        _absorb_next_size = False
        _absorbed_size_expr = ""

        for arg in non_self_args:
            if arg.get("is_varargs"):
                skip = True
                break

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
                        "_name": "_size",
                    })
                    continue
                # Not size_t — fall through and resolve normally

            js_idx = sum(1 for r in resolved_args if not r.get("_absorbed"))
            resolved = _resolve_arg(
                arg, js_idx,
                processed_enums, processed_typedefs, processed_structs,
            )
            if resolved is None:
                t = arg["type"].get("declaration", "?")
                print(f"  [method] Skip {c_func_name}: unsupported arg "
                      f"'{arg['name']}' ({t})")
                skip = True
                break

            if resolved.get("absorbs_next_size"):
                _absorb_next_size   = True
                _absorbed_size_expr = resolved.pop("absorbed_size_expr")
                resolved.pop("absorbs_next_size", None)

            resolved["_name"] = arg["name"]
            resolved_args.append(resolved)
            for inc in resolved["extra_includes"]:
                all_includes.add(inc)

        if skip:
            continue

        methods.append({
            "c_func_name": c_func_name,
            "cpp_method_name": cpp_method_name,
            "js_name": js_method_name,
            "ret": ret,
            "args": resolved_args,
            "extra_includes": sorted(all_includes),
        })

    return methods


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic method injectors
# ─────────────────────────────────────────────────────────────────────────────

def _inject_font_atlas_synthetics(struct_info: dict) -> None:
    """Add synthetic GetTexDataAsAlpha8 / GetTexDataAsRGBA32 methods.

    These functions use unsigned char** out-params that the generic resolver
    cannot handle.  The synthetics call the C functions directly and return
    a JS object ``{ pixels: Uint8Array, width: number, height: number }``.
    """
    def _make_body(c_func: str, bpp_multiplier: int) -> str:
        return (
            "  Napi::Env env = info.Env();\n"
            "  unsigned char* pixels = nullptr;\n"
            "  int width = 0, height = 0;\n"
            f"  {c_func}(this->ptr, &pixels, &width, &height, nullptr);\n"
            f"  size_t byte_len = static_cast<size_t>(width) * static_cast<size_t>(height) * {bpp_multiplier};\n"
            "  auto ab = Napi::ArrayBuffer::New(env, byte_len);\n"
            "  std::memcpy(ab.Data(), pixels, byte_len);\n"
            "  auto arr = Napi::Uint8Array::New(env, byte_len, ab, 0);\n"
            "  Napi::Object result = Napi::Object::New(env);\n"
            '  result.Set("pixels", arr);\n'
            '  result.Set("width", Napi::Number::New(env, width));\n'
            '  result.Set("height", Napi::Number::New(env, height));\n'
            "  return result;"
        )

    struct_info["methods"].extend([
        {
            "c_func_name": "ImFontAtlas_GetTexDataAsAlpha8",
            "cpp_method_name": "GetTexDataAsAlpha8",
            "js_name": "getTexDataAsAlpha8",
            "ret": {"call_prefix": "", "return_stmt": "", "ts_type": "{ pixels: Uint8Array; width: number; height: number }", "extra_includes": []},
            "args": [],
            "extra_includes": ["<cstring>"],
            "synthetic_body": _make_body("ImFontAtlas_GetTexDataAsAlpha8", 1),
        },
        {
            "c_func_name": "ImFontAtlas_GetTexDataAsRGBA32",
            "cpp_method_name": "GetTexDataAsRGBA32",
            "js_name": "getTexDataAsRGBA32",
            "ret": {"call_prefix": "", "return_stmt": "", "ts_type": "{ pixels: Uint8Array; width: number; height: number }", "extra_includes": []},
            "args": [],
            "extra_includes": ["<cstring>"],
            "synthetic_body": _make_body("ImFontAtlas_GetTexDataAsRGBA32", 4),
        },
    ])


# ─────────────────────────────────────────────────────────────────────────────
# C++ code builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_header(
    class_name: str,
    c_struct_name: str,
    resolved_fields: list[dict],
    is_by_ref: bool = False,
    methods: list[dict] | None = None,
) -> str:
    """Return the content of the .h file for a struct wrapper."""

    # Deduplicate resolved_fields by method_suffix (keep first occurrence)
    method_suffixes_before = [f.get("method_suffix", "?") for f in resolved_fields]
    seen_suffixes = set()
    deduplicated_fields = []
    for field in resolved_fields:
        suffix = field["method_suffix"]
        if suffix not in seen_suffixes:
            deduplicated_fields.append(field)
            seen_suffixes.add(suffix)
    method_suffixes_after = [f.get("method_suffix", "?") for f in deduplicated_fields]
    if method_suffixes_before != method_suffixes_after:
        print(f"  [dedup] {class_name}: {len(method_suffixes_before)} → {len(method_suffixes_after)} fields")
    resolved_fields = deduplicated_fields

    # Collect additional headers required by nested struct-type fields.
    # System headers ("<...>") belong in the .cpp to avoid polluting consumers;
    # only user headers (".h") are placed in the .h.
    extra_includes = sorted({
        inc
        for field in resolved_fields
        for inc in field["extra_includes"]
        if not inc.startswith("<")
    })
    include_lines = "".join(f'#include "{inc}"\n' for inc in extra_includes)

    # Build the private method declarations (no setter decl for readonly fields).
    method_decls = []
    field_method_names = set()
    for field in resolved_fields:
        suffix = field["method_suffix"]
        decl = f"  Napi::Value Get{suffix}(const Napi::CallbackInfo& info);"
        if not field.get("is_readonly", False):
            decl += f"\n  void Set{suffix}(const Napi::CallbackInfo& info, const Napi::Value& value);"
        method_decls.append(decl)
        field_method_names.add(f"Get{suffix}")
        if not field.get("is_readonly", False):
            field_method_names.add(f"Set{suffix}")

    # Instance method declarations (skip if method name conflicts with field accessor)
    for m in (methods or []):
        if m['cpp_method_name'] not in field_method_names:
            method_decls.append(f"  Napi::Value {m['cpp_method_name']}(const Napi::CallbackInfo& info);")

    methods_block = "\n\n".join(method_decls)

    if is_by_ref:
        storage = f"  {c_struct_name}* ptr = nullptr;  // borrowed — do not delete"
        new_instance_sig = f"  static Napi::Object NewInstance(Napi::Env env, {c_struct_name}* ptr);"
        raw_method = f"  {c_struct_name}* Raw() {{ return this->ptr; }}"
        extra = (
            f"\n"
            f"  // Instances are only valid when constructed via NewInstance().\n"
            f"  // Direct JS construction (\"new {class_name}()\") leaves ptr null.\n"
        )
    else:
        storage = f"  {c_struct_name} value{{}};  // owned copy"
        new_instance_sig = f"  static Napi::Object NewInstance(Napi::Env env, const {c_struct_name}& source);"
        raw_method = f"  {c_struct_name}& Raw() {{ return this->value; }}"
        extra = "\n"

    return (
        f"#pragma once\n"
        f"#include <napi.h>\n"
        f'#include "dcimgui.h"\n'
        f"{include_lines}"
        f"\n"
        f"class {class_name} : public Napi::ObjectWrap<{class_name}> {{\n"
        f"public:\n"
        f"  static Napi::Object Init(Napi::Env env, Napi::Object exports);\n"
        f"  {class_name}(const Napi::CallbackInfo& info);\n"
        f"\n"
        f"{new_instance_sig}\n"
        f"  {raw_method}\n"
        f"{extra}"
        f"private:\n"
        f"  static Napi::FunctionReference ctor;\n"
        f"  {storage}\n"
        f"\n"
        f"{methods_block}\n"
        f"}};\n"
    )


def _build_cpp(
    class_name: str,
    c_struct_name: str,
    file_base: str,
    resolved_fields: list[dict],
    is_by_ref: bool = False,
    methods: list[dict] | None = None,
) -> str:
    """Return the content of the .cpp file for a struct wrapper."""

    # Deduplicate resolved_fields by method_suffix (keep first occurrence)
    seen_suffixes = set()
    deduplicated_fields = []
    for field in resolved_fields:
        suffix = field["method_suffix"]
        if suffix not in seen_suffixes:
            deduplicated_fields.append(field)
            seen_suffixes.add(suffix)
    resolved_fields = deduplicated_fields

    # Build DefineClass entries for both property accessors and instance methods.
    all_entries: list[str] = []
    for f in resolved_fields:
        if f.get("is_readonly", False):
            all_entries.append(
                f'InstanceAccessor<&{class_name}::Get{f["method_suffix"]}>("{f["js_name"]}")'
            )
        else:
            all_entries.append(
                f'InstanceAccessor<&{class_name}::Get{f["method_suffix"]}, '
                f'&{class_name}::Set{f["method_suffix"]}>("{f["js_name"]}")'
            )

    # Build set of field method names to avoid conflicts with instance methods
    field_method_names = set()
    for f in resolved_fields:
        field_method_names.add(f"Get{f['method_suffix']}")
        if not f.get("is_readonly", False):
            field_method_names.add(f"Set{f['method_suffix']}")

    # Add instance methods, skipping any that conflict with field accessors
    for m in (methods or []):
        if m["cpp_method_name"] not in field_method_names:
            all_entries.append(
                f'InstanceMethod<&{class_name}::{m["cpp_method_name"]}>("{m["js_name"]}")'
            )

    if is_by_ref:
        ctor_body = "  // By-ref wrapper — use NewInstance() to create a valid instance."
        new_instance_body = (
            f"  Napi::Object instance = ctor.New({{}});\n"
            f"  {class_name}::Unwrap(instance)->ptr = ptr;"
        )
        new_instance_sig = f"{c_struct_name}* ptr"
    else:
        # By-value: populate scalar fields from positional constructor arguments.
        ctor_lines = []
        arg_index = 0
        for field in resolved_fields:
            if not field["is_scalar"]:
                continue
            ctor_lines.append(
                f"  if (info.Length() > {arg_index}) {{\n"
                f"    Napi::Value value = info[{arg_index}];\n"
                f"    {field['setter_body']}\n"
                f"  }}"
            )
            arg_index += 1
        ctor_body = "\n".join(ctor_lines) if ctor_lines else "  // No scalar fields — use property setters after construction."
        new_instance_body = (
            f"  Napi::Object instance = ctor.New({{}});\n"
            f"  {class_name}::Unwrap(instance)->value = source;"
        )
        new_instance_sig = f"const {c_struct_name}& source"

    # Getter and setter method implementations.
    method_impls = []
    for field in resolved_fields:
        suffix = field["method_suffix"]
        impl = (
            f"Napi::Value {class_name}::Get{suffix}(const Napi::CallbackInfo& info) {{\n"
            f"  Napi::Env env = info.Env();\n"
            f"  {field['getter_body']}\n"
            f"}}"
        )
        if not field.get("is_readonly", False):
            impl += (
                f"\n\n"
                f"void {class_name}::Set{suffix}(const Napi::CallbackInfo& info, const Napi::Value& value) {{\n"
                f"  {field['setter_body']}\n"
                f"}}"
            )
        method_impls.append(impl)

    # Instance method implementations (struct methods like ImDrawList_AddLine).
    # The instance pointer is passed as the first arg to the C function.
    # Skip methods that have the same name as field accessors (they use properties instead).
    self_expr = "this->ptr" if is_by_ref else "&this->value"
    for m in (methods or []):
        if m["cpp_method_name"] in field_method_names:
            continue  # Skip — field property takes precedence

        # Synthetic methods supply a complete hand-written body.
        if "synthetic_body" in m:
            method_impls.append(
                f"Napi::Value {class_name}::{m['cpp_method_name']}(const Napi::CallbackInfo& info) {{\n"
                f"{m['synthetic_body']}\n"
                f"}}"
            )
            continue

        body_lines = ["  Napi::Env env = info.Env();"]
        for resolved in m["args"]:
            body_lines.extend(resolved["pre_lines"])
        call_args = ", ".join([self_expr] + [a["pass_expr"] for a in m["args"]])
        call = f'{m["c_func_name"]}({call_args})'
        ret = m["ret"]
        if ret["call_prefix"]:
            body_lines.append(f"  {ret['call_prefix'].strip()}{call};")
        else:
            body_lines.append(f"  {call};")
        body_lines.append(f"  {ret['return_stmt'].strip()}")
        body = "\n".join(body_lines)
        method_impls.append(
            f"Napi::Value {class_name}::{m['cpp_method_name']}(const Napi::CallbackInfo& info) {{\n"
            f"{body}\n"
            f"}}"
        )

    methods_str = "\n\n".join(method_impls)

    if all_entries:
        define_class_body = "    " + ",\n    ".join(all_entries) + ",\n  "
    else:
        define_class_body = ""

    # Collect extra includes needed by method implementations.
    method_user_includes = sorted({
        inc
        for m in (methods or [])
        for inc in m["extra_includes"]
        if not inc.startswith("<")
    })
    method_sys_includes = sorted({
        inc
        for m in (methods or [])
        for inc in m["extra_includes"]
        if inc.startswith("<")
    })
    # Collect system includes from fields (e.g. <cstring> for array fields)
    field_sys_includes = sorted({
        inc
        for field in resolved_fields
        for inc in field["extra_includes"]
        if inc.startswith("<")
    })
    all_sys_includes = sorted(set(field_sys_includes) | set(method_sys_includes))
    # Always include <string> when methods are present (const char* args use std::string).
    needs_string = methods and any(
        "std::string" in line
        for m in methods
        for a in m["args"]
        for line in a["pre_lines"]
    )
    method_include_lines = ""
    if needs_string:
        method_include_lines += "#include <string>\n"
    for inc in all_sys_includes:
        method_include_lines += f'#include {inc}\n'
    for inc in method_user_includes:
        method_include_lines += f'#include "{inc}"\n'

    return (
        f'#include "{file_base}.h"\n'
        f"{method_include_lines}"
        f"\n"
        f"Napi::FunctionReference {class_name}::ctor;\n"
        f"\n"
        f"Napi::Object {class_name}::Init(Napi::Env env, Napi::Object exports) {{\n"
        f"  Napi::Function func = DefineClass(env, \"{class_name}\", {{\n"
        f"{define_class_body}}});\n"
        f"  ctor = Napi::Persistent(func);\n"
        f"  ctor.SuppressDestruct();\n"
        f"  exports.Set(\"{class_name}\", func);\n"
        f"  return exports;\n"
        f"}}\n"
        f"\n"
        f"{class_name}::{class_name}(const Napi::CallbackInfo& info)\n"
        f"    : Napi::ObjectWrap<{class_name}>(info) {{\n"
        f"{ctor_body}\n"
        f"}}\n"
        f"\n"
        f"Napi::Object {class_name}::NewInstance(Napi::Env env, {new_instance_sig}) {{\n"
        f"{new_instance_body}\n"
        f"  return instance;\n"
        f"}}\n"
        f"\n"
        f"{methods_str}\n"
    )


def _format_type_import(names: set[str], module_path: str) -> str:
    if not names:
        return ""
    return f"import type {{ {', '.join(sorted(names))} }} from \"{module_path}\";\n"


def _build_dts(
    all_struct_infos: list[dict],
    enum_type_names: set[str],
    typedef_type_names: set[str],
) -> str:
    """Return the combined structs.d.ts content."""
    lines = ["// Auto-generated — do not edit."]
    lines.append(_format_type_import(enum_type_names, "./enums").rstrip())
    lines.append(_format_type_import(typedef_type_names, "./typedefs").rstrip())
    lines.append(
        'import type { BoolRef, CallbackRef, DoubleRef, FloatRef, IntRef, StringListRef, StringRef } from "../../dts/ref";'
    )
    lines.append("")

    for struct_info in all_struct_infos:
        class_name = struct_info["cpp_class_name"]
        is_by_ref = struct_info.get("is_by_ref", False)
        resolved_fields = struct_info["resolved_fields"]

        # By-value: constructor accepts scalar fields as optional args.
        # By-ref: no constructor args (instances always come from C++).
        if is_by_ref:
            ctor_line = f"  private constructor();"
        else:
            scalar_fields = [f for f in resolved_fields if f["is_scalar"]]
            ctor_param_names = make_unique_ts_identifiers([f["js_name"] for f in scalar_fields])
            ctor_params = ", ".join(
                f"{name}?: {field['ts_type']}"
                for name, field in zip(ctor_param_names, scalar_fields)
            )
            ctor_line = f"  constructor({ctor_params});"

        # Build property declarations (readonly where applicable).
        prop_lines = []
        for f in resolved_fields:
            prefix = "readonly " if f.get("is_readonly", False) else ""
            prop_lines.append(f"  {prefix}{f['js_name']}: {f['ts_type']};")

        # Build method signatures.
        method_sig_lines = []
        for m in struct_info.get("methods", []):
            visible_args = [
                a for a in m["args"]
                if not a.get("_absorbed") and a.get("ts_type") is not None
            ]
            method_param_names = make_unique_ts_identifiers([
                a.get("_name", "arg") for a in visible_args
            ])

            seen_optional = False
            method_param_tokens = []
            for name, arg in zip(method_param_names, visible_args):
                is_optional = arg["is_optional"] or seen_optional
                if is_optional:
                    seen_optional = True
                method_param_tokens.append(
                    f"{name}{'?' if is_optional else ''}: {arg['ts_type']}"
                )

            ts_params = ", ".join(
                method_param_tokens
            )
            method_sig_lines.append(f"  {m['js_name']}({ts_params}): {m['ret']['ts_type']};")

        lines.append(f"export class {class_name} {{")
        lines.append(ctor_line)
        if prop_lines:
            lines.append("")
            lines.extend(prop_lines)
        if method_sig_lines:
            lines.append("")
            lines.extend(method_sig_lines)
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def _build_init_header(class_names: list[str]) -> str:
    return (
        f"#pragma once\n"
        f"#include <napi.h>\n"
        f"\n"
        f"// Initialize all generated struct wrappers and register them on exports.\n"
        f"// Called once from module.cpp Init().\n"
        f"void InitStructs(Napi::Env env, Napi::Object exports);\n"
    )


def _build_init_cpp(class_names: list[str], file_bases: list[str]) -> str:
    includes = "".join(f'#include "{base}.h"\n' for base in file_bases)
    calls = "\n".join(f"  {name}::Init(env, exports);" for name in class_names)
    return (
        f'#include "structs_init.h"\n'
        f"{includes}"
        f"\n"
        f"void InitStructs(Napi::Env env, Napi::Object exports) {{\n"
        f"  // Initialise in dependency order so that wrapper types which appear\n"
        f"  // as field types in other structs are registered first.\n"
        f"{calls}\n"
        f"}}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def process_structs(
    bindings: dict,
    processed_enums: dict,
    processed_typedefs: dict,
    count_values: dict,
) -> dict:
    """Generate NAPI wrappers and TypeScript declarations for ImGui structs.

    Phase 1 scope: by-value structs (ImVec2, ImVec4, ImTextureRef, ImColor).

    Returns processed_structs: dict mapping original C struct name to its
    generation metadata, for use by downstream processors that need to
    reference these wrappers (e.g. when generating wrappers for structs that
    embed these as field types).
    """
    structs = bindings["structs"]

    # processed_structs is built up as we go so that later structs can find
    # wrappers for types they reference in their fields (e.g. Color finds Vec4).
    processed_structs: dict = {}

    # Phase 1: by-value structs.  They carry their data by value and the
    # wrapper owns it — simplest ownership model, no pointer aliasing.
    by_value_structs = [
        struct
        for struct in structs
        if struct["by_value"]
        and not struct["is_internal"]
        and not struct["forward_declaration"]
        and len(struct["fields"]) > 0
    ]

    # Phase 2: by-reference structs.  ImGui owns the memory; the wrapper holds
    # a borrowed pointer set by NewInstance().  Anonymous types are skipped.
    by_ref_structs = [
        struct
        for struct in structs
        if not struct["by_value"]
        and not struct["is_internal"]
        and not struct["forward_declaration"]
        and len(struct["fields"]) > 0
        and not struct["name"].startswith("__")
    ]

    all_struct_infos: list[dict] = []

    # Pre-register all structs so pointer field resolution can find any struct
    # regardless of processing order.
    for struct in by_value_structs:
        original_name = struct["name"]
        class_name = _strip_imgui_prefix(original_name)
        file_base = _to_file_base_name(class_name)
        processed_structs[original_name] = {
            "cpp_class_name": class_name,
            "file_base": file_base,
            "c_struct_name": original_name,
            "original_name": original_name,
            "resolved_fields": [],
            "is_by_ref": False,
            "methods": [],
        }
    for struct in by_ref_structs:
        original_name = struct["name"]
        class_name = _strip_imgui_prefix(original_name)
        file_base = _to_file_base_name(class_name)
        processed_structs[original_name] = {
            "cpp_class_name": class_name,
            "file_base": file_base,
            "c_struct_name": original_name,
            "original_name": original_name,
            "resolved_fields": [],
            "is_by_ref": True,
            "methods": [],
        }

    def _process_one(struct: dict, is_by_ref: bool) -> None:
        original_name = struct["name"]
        class_name = _strip_imgui_prefix(original_name)
        file_base = _to_file_base_name(class_name)
        c_struct_name = original_name
        field_ref = "this->ptr->" if is_by_ref else "this->value."

        print(f"  {'[ref]' if is_by_ref else '[val]'} {original_name} → {class_name} ({file_base}.h/.cpp)")

        resolved_fields = []
        for field in struct["fields"]:
            if field.get("is_internal", False):
                continue

            resolved = _resolve_field(
                field,
                processed_enums,
                processed_typedefs,
                processed_structs,
                field_ref=field_ref,
                count_values=count_values,
            )
            if resolved is not None:
                resolved_fields.append(resolved)

        struct_info = {
            "cpp_class_name": class_name,
            "file_base": file_base,
            "c_struct_name": c_struct_name,
            "original_name": original_name,
            "resolved_fields": resolved_fields,
            "is_by_ref": is_by_ref,
            "methods": [],  # filled in second pass
        }
        processed_structs[original_name] = struct_info
        all_struct_infos.append(struct_info)

    for struct in by_value_structs:
        _process_one(struct, is_by_ref=False)

    for struct in by_ref_structs:
        _process_one(struct, is_by_ref=True)

    # ── Second pass: collect instance methods now that ALL structs are
    # registered.  This ensures methods with args of type ImFont*, DrawList*,
    # etc. are resolved correctly regardless of declaration order.
    all_funcs = bindings.get("functions", [])
    for struct_info in all_struct_infos:
        c_struct_name = struct_info["c_struct_name"]
        struct_methods = _collect_struct_methods(
            c_struct_name,
            all_funcs,
            processed_enums,
            processed_typedefs,
            processed_structs,
        )
        struct_info["methods"] = struct_methods

        # ── Inject synthetic methods for structs with complex out-parameter
        # patterns that the generic resolver cannot handle.
        if c_struct_name == "ImFontAtlas":
            _inject_font_atlas_synthetics(struct_info)

        if struct_methods:
            print(f"  [methods] {c_struct_name}: {len(struct_methods)} bound")

        class_name = struct_info["cpp_class_name"]
        file_base = struct_info["file_base"]
        is_by_ref = struct_info["is_by_ref"]
        resolved_fields = struct_info["resolved_fields"]

        header_path = GEN_NAPI / f"{file_base}.h"
        cpp_path = GEN_NAPI / f"{file_base}.cpp"
        header_path.write_text(_build_header(class_name, c_struct_name, resolved_fields, is_by_ref, struct_methods))
        cpp_path.write_text(_build_cpp(class_name, c_struct_name, file_base, resolved_fields, is_by_ref, struct_methods))

    # Write combined TypeScript declarations.
    dts_path = GEN_DTS / "structs.d.ts"
    typedef_type_names = {
        td["name"]
        for name, td in processed_typedefs.items()
        if td.get("name")
        and name not in processed_enums
        and f"{name}_" not in processed_enums
    }
    enum_type_names = {
        enum_name
        for enum_name in processed_enums.values()
        if enum_name
    }
    dts_path.write_text(_build_dts(all_struct_infos, enum_type_names, typedef_type_names))

    # Write the init shim that module.cpp calls to register all wrappers.
    class_names = [info["cpp_class_name"] for info in all_struct_infos]
    file_bases = [info["file_base"] for info in all_struct_infos]

    (GEN_NAPI / "structs_init.h").write_text(_build_init_header(class_names))
    (GEN_NAPI / "structs_init.cpp").write_text(_build_init_cpp(class_names, file_bases))

    return processed_structs
