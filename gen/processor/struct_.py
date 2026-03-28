from config import GEN_NAPI, GEN_DTS

# Structs to exclude from generation (complex types, internal use, etc.)
EXCLUDED_STRUCTS = {
    # ImVector templates - complex template types, handle separately
    "ImVector_ImGuiTextRange": "template vector type",
    "ImVector_char": "template vector type",
    "ImVector_ImGuiStoragePair": "template vector type",
    "ImVector_ImGuiSelectionRequest": "template vector type",
    "ImVector_ImDrawChannel": "template vector type",
    "ImVector_ImDrawCmd": "template vector type",
    "ImVector_ImDrawIdx": "template vector type",
    "ImVector_ImDrawVert": "template vector type",
    "ImVector_ImVec2": "template vector type",
    "ImVector_ImVec4": "template vector type",
    "ImVector_ImTextureRef": "template vector type",
    "ImVector_ImU8": "template vector type",
    "ImVector_ImDrawListPtr": "template vector type",
    "ImVector_ImTextureRect": "template vector type",
    "ImVector_ImU32": "template vector type",
    "ImVector_ImWchar_t": "template vector type",
    "ImVector_ImFontPtr": "template vector type",
    "ImVector_ImFontConfig": "template vector type",
    "ImVector_ImDrawListSharedDataPtr": "template vector type",
    "ImVector_float": "template vector type",
    "ImVector_ImU16": "template vector type",
    "ImVector_ImFontGlyph": "template vector type",
    "ImVector_ImFontConfigPtr": "template vector type",
    "ImVector_ImGuiPlatformMonitor": "template vector type",
    "ImVector_ImTextureDataPtr": "template vector type",
    "ImVector_ImGuiViewportPtr": "template vector type",
    # Forward declarations / opaque types - no fields or need special handling
    "ImDrawListSharedData": "forward declaration",
    "ImDrawChannel": "opaque type",
    "ImDrawCmd": "opaque type",
    "ImDrawData": "opaque type",
    "ImDrawList": "opaque type",
    "ImFont": "opaque type",
    "ImFontAtlas": "opaque type",
    "ImFontAtlasBuilder": "opaque type",
    "ImFontAtlasRect": "opaque type - needs ImTextureRef which is excluded",
    "ImFontBaked": "opaque type",
    "ImFontConfig": "opaque type",
    "ImFontGlyphRangesBuilder": "opaque type",
    "ImFontLoader": "opaque type",
    "ImTextureData": "opaque type",
    "ImGuiContext": "opaque type",
    "ImGuiInputTextCallbackData": "opaque type",
    "ImGuiListClipper": "opaque type",
    "ImGuiMultiSelectIO": "opaque type - has ImVector types",
    "ImGuiPayload": "opaque type",
    "ImGuiPlatformIO": "opaque type",
    "ImGuiPlatformMonitor": "opaque type",
    "ImGuiSelectionBasicStorage": "opaque type",
    "ImGuiSelectionExternalStorage": "opaque type",
    "ImGuiSelectionRequest": "opaque type",
    "ImGuiSizeCallbackData": "opaque type",
    "ImGuiStorage": "opaque type - has ImVector types",
    "ImGuiStyle": "opaque type - large, has array field",
    "ImGuiTableSortSpecs": "opaque type",
    "ImGuiTextBuffer": "opaque type - has ImVector_char",
    "ImGuiTextFilter": "opaque type - has ImVector_ImGuiTextRange",
    "ImGuiViewport": "opaque type",
    "ImGuiWindowClass": "opaque type - has multiple User types",
    "ImColor": "opaque type - has ImVec4",
    "ImDrawCmdHeader": "opaque type - has ImTextureRef",
    "ImDrawListSplitter": "opaque type - has ImVector_ImDrawChannel",
    # Types with pointer fields - need special handling
    "ImTextureRef": "has pointer fields",
    "ImGuiTextFilter_ImGuiTextRange": "nested type",
    # Complex types with arrays
    "__anonymous_type0": "anonymous union type",
    "__anonymous_type1": "anonymous type",
}

# Mapping from builtin types to TypeScript types
BUILTIN_TO_TS = {
    "bool": "boolean",
    "float": "number",
    "double": "number",
    "int": "number",
    "unsigned_int": "number",
    "short": "number",
    "unsigned_short": "number",
    "char": "number",
    "unsigned_char": "number",
    "long_long": "bigint",
    "unsigned_long_long": "bigint",
}

# Mapping from User types (typedefs and structs) to TypeScript types
USER_TO_TS = {}

# Set of User type names that are actual structs (not typedefs to builtins)
# These need special handling because they can't be stored as simple numbers
STRUCT_TYPES = set()

def get_type_kind_and_details(field_type_info):
    """Extract kind and details from field type info."""
    description = field_type_info.get("description", {})
    kind = description.get("kind", "unknown")
    return kind, description

def can_generate_struct(struct_entry):
    """Check if we can generate code for this struct."""
    name = struct_entry["name"]
    if name in EXCLUDED_STRUCTS:
        return False, "excluded"
    if struct_entry.get("forward_declaration", False):
        return False, "forward declaration"
    fields = struct_entry.get("fields", [])
    if not fields:
        return False, "no fields"
    # Check all fields are builtins or mappable User types
    for field in fields:
        kind, desc = get_type_kind_and_details(field["type"])
        if kind == "Builtin":
            continue
        elif kind == "User":
            user_name = desc.get("name", "")
            if user_name in USER_TO_TS:
                # Check if it's a struct type that needs special handling
                if user_name in STRUCT_TYPES:
                    return False, f"User type {user_name} is a struct (needs nested wrapper)"
                continue
            return False, f"User type {user_name} not in mapping"
        elif kind == "Array":
            return False, "has Array field"
        elif kind == "Pointer":
            return False, "has Pointer field"
        else:
            return False, f"has {kind} field"
    return True, "ok"

def get_napi_type_method(field):
    """Get the appropriate Napi::Number method for a field type."""
    decl = field["type"].get("declaration", "float").lower()
    if "float" in decl:
        return "FloatValue"
    elif "double" in decl:
        return "DoubleValue"
    elif "int" in decl or "short" in decl or "char" in decl:
        return "Int32Value"
    elif "unsigned" in decl:
        return "Uint32Value"
    else:
        return "FloatValue"

def get_ts_type_for_field(field):
    """Get TypeScript type for a field."""
    kind, desc = get_type_kind_and_details(field["type"])
    if kind == "Builtin":
        builtin = desc.get("builtin_type", "float")
        return BUILTIN_TO_TS.get(builtin, "number")
    elif kind == "User":
        user_name = desc.get("name", "")
        return USER_TO_TS.get(user_name, "unknown")
    return "unknown"

def strip_imgui_prefix(name):
    """Strip 'ImGui' prefix from type name if present."""
    if name.startswith("ImGui"):
        return name[5:]
    return name

def generate_struct_h(struct_entry):
    """Generate C++ header file for a struct wrapper."""
    name = struct_entry["name"]
    stripped_name = strip_imgui_prefix(name)
    wrapper_name = stripped_name + "Wrapper"
    
    lines = [
        "#pragma once",
        "",
        "#include <napi.h>",
        f'#include "dcimgui.h"',
        "",
        f"class {wrapper_name} : public Napi::ObjectWrap<{wrapper_name}> {{",
        " public:",
        f"  static Napi::Object Init(Napi::Env env, Napi::Object exports);",
        f"  {wrapper_name}(const Napi::CallbackInfo& info);",
        "",
        f"  inline {name}_t Value();",
        f"  inline {name}_t* Ptr();",
        "",
        " private:",
        f"  {name}_t native;",
    ]
    
    for field in struct_entry["fields"]:
        field_name = field["name"]
        capitalized_field_name = field_name[0].upper() + field_name[1:]
        lines.append(f"  Napi::Value Get{capitalized_field_name}(const Napi::CallbackInfo& info);")
        lines.append(f"  void Set{capitalized_field_name}(const Napi::CallbackInfo& info, const Napi::Value& value);")
    
    lines.append("};")
    return "\n".join(lines)

def generate_struct_cpp(struct_entry):
    """Generate C++ cpp file for a struct wrapper."""
    name = struct_entry["name"]
    stripped_name = strip_imgui_prefix(name)
    wrapper_name = stripped_name + "Wrapper"
    fields = struct_entry["fields"]
    
    lines = [
        f'#include "{wrapper_name}.h"',
        "",
        f"Napi::Object {wrapper_name}::Init(Napi::Env env, Napi::Object exports) {{",
        f"  Napi::Function func = DefineClass(env, \"{stripped_name}\", {{",
    ]
    
    accessors = []
    for field in fields:
        field_name = field["name"]
        capitalized = field_name[0].upper() + field_name[1:]
        accessors.append(f"    InstanceAccessor<&{wrapper_name}::Get{capitalized}, &{wrapper_name}::Set{capitalized}>(\"{field_name}\")")
    
    lines.append(",\n".join(accessors))
    lines.append("  });")
    lines.append(f"  exports.Set(\"{stripped_name}\", func);")
    lines.append("  return exports;")
    lines.append("}")
    lines.append("")
    
    lines.append(f"{wrapper_name}::{wrapper_name}(const Napi::CallbackInfo& info)")
    lines.append(f"    : Napi::ObjectWrap<{wrapper_name}>(info) {{")
    lines.append(f"  memset(&this->native, 0, sizeof({name}_t));")
    lines.append("  if (info.Length() > 0 && !info[0].IsEmpty()) {")
    lines.append("    // TODO: Initialize from JS object if needed")
    lines.append("  }")
    lines.append("}")
    lines.append("")
    
    lines.append(f"inline {name}_t {wrapper_name}::Value() {{ return this->native; }}")
    lines.append(f"inline {name}_t* {wrapper_name}::Ptr() {{ return &this->native; }}")
    lines.append("")
    
    for field in fields:
        field_name = field["name"]
        capitalized = field_name[0].upper() + field_name[1:]
        kind, desc = get_type_kind_and_details(field["type"])
        
        if kind == "Builtin":
            napi_method = get_napi_type_method(field)
            lines.append(f"Napi::Value {wrapper_name}::Get{capitalized}(const Napi::CallbackInfo& info) {{")
            lines.append(f"  return Napi::Number::New(info.Env(), this->native.{field_name});")
            lines.append("}")
            lines.append("")
            lines.append(f"void {wrapper_name}::Set{capitalized}(const Napi::CallbackInfo& info, const Napi::Value& value) {{")
            lines.append(f"  this->native.{field_name} = value.As<Napi::Number>().{napi_method}();")
            lines.append("}")
            lines.append("")
        elif kind == "User":
            lines.append(f"Napi::Value {wrapper_name}::Get{capitalized}(const Napi::CallbackInfo& info) {{")
            lines.append(f"  return Napi::Number::New(info.Env(), this->native.{field_name});")
            lines.append("}")
            lines.append("")
            lines.append(f"void {wrapper_name}::Set{capitalized}(const Napi::CallbackInfo& info, const Napi::Value& value) {{")
            lines.append(f"  this->native.{field_name} = value.As<Napi::Number>().Int32Value();")
            lines.append("}")
            lines.append("")
    
    return "\n".join(lines)

def generate_struct_ts(struct_entry):
    """Generate TypeScript interface for a struct."""
    name = struct_entry["name"]
    stripped_name = strip_imgui_prefix(name)
    fields = struct_entry["fields"]
    
    lines = [
        f"export class {stripped_name} {{",
        "  constructor();",
    ]
    
    for field in fields:
        lines.append(f"  {field['name']}: {get_ts_type_for_field(field)};")
    
    lines.append("  Ptr(): bigint;")
    lines.append("}")
    lines.append("")
    
    return "\n".join(lines)

def build_user_type_mapping(bindings):
    """Build mapping from User type names (typedefs and structs) to TypeScript types."""
    global USER_TO_TS
    
    # First, process typedefs
    typedefs = bindings.get("typedefs", [])
    for td in typedefs:
        name = td["name"]
        type_info = td.get("type", {})
        desc = type_info.get("description", {})
        kind = desc.get("kind", "")
        
        if kind == "Builtin":
            builtin = desc.get("builtin_type", "float")
            ts_type = BUILTIN_TO_TS.get(builtin)
            if ts_type:
                USER_TO_TS[name] = ts_type
        elif kind == "User":
            target = desc.get("name", "")
            if target in USER_TO_TS:
                USER_TO_TS[name] = USER_TO_TS[target]
    
    # Then, add structs with stripped names (ImVec2 -> Vec2)
    # Also track which User types are actual structs
    global STRUCT_TYPES
    structs = bindings.get("structs", [])
    for s in structs:
        name = s["name"]
        if name not in EXCLUDED_STRUCTS and s.get("fields"):
            stripped = strip_imgui_prefix(name)
            USER_TO_TS[name] = stripped
            STRUCT_TYPES.add(name)
    
    print(f"User type mapping built with {len(USER_TO_TS)} entries")

def process_structs(bindings):
    """Generate NAPI C++ wrappers and TypeScript interfaces for structs."""
    build_user_type_mapping(bindings)
    
    structs = bindings.get("structs", [])
    
    print("\nStruct analysis:")
    can_generate = []
    
    for struct_entry in structs:
        name = struct_entry["name"]
        gen, reason = can_generate_struct(struct_entry)
        if gen:
            can_generate.append(struct_entry)
            print(f"  [GEN] {name}")
        else:
            print(f"  [SKIP] {name}: {reason}")
    
    print(f"\nCan generate: {len(can_generate)}")
    
    generated_wrappers = []
    
    for struct_entry in can_generate:
        name = struct_entry["name"]
        stripped_name = strip_imgui_prefix(name)
        wrapper_name = stripped_name + "Wrapper"
        generated_wrappers.append(wrapper_name)
        
        h_content = generate_struct_h(struct_entry)
        h_file = GEN_NAPI / f"{wrapper_name}.h"
        h_file.write_text(h_content)
        
        cpp_content = generate_struct_cpp(struct_entry)
        cpp_file = GEN_NAPI / f"{wrapper_name}.cpp"
        cpp_file.write_text(cpp_content)
        
        ts_content = generate_struct_ts(struct_entry)
        ts_file = GEN_DTS / f"{stripped_name}.d.ts"
        ts_file.write_text(ts_content)
        
        print(f"Generated {wrapper_name}")
    
    print(f"\nTotal generated: {len(can_generate)} structs")
    print(f"Generated wrappers: {generated_wrappers}")
    return generated_wrappers
