from config import GEN_NAPI, GEN_DTS

# Functions to exclude from generation
EXCLUDED_FUNCTIONS = {
    # Internal or problematic functions
}

# Mapping from builtin types to NAPI C++ types
BUILTIN_TO_NAPI_TYPE = {
    "void": "void",
    "bool": "bool",
    "float": "float",
    "double": "double",
    "int": "int32_t",
    "unsigned_int": "uint32_t",
    "short": "int16_t",
    "unsigned_short": "uint16_t",
    "char": "char",
    "unsigned_char": "uint8_t",
    "long_long": "int64_t",
    "unsigned_long_long": "uint64_t",
}

# Mapping from builtin types to TypeScript types
BUILTIN_TO_TS_TYPE = {
    "void": "void",
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


def get_type_info(type_entry):
    """Extract type information from a type entry."""
    desc = type_entry.get("description", {})
    kind = desc.get("kind", "unknown")
    
    if kind == "Builtin":
        return ("builtin", desc.get("builtin_type", "void"))
    elif kind == "User":
        return ("user", desc.get("name", "unknown"))
    elif kind == "Pointer":
        return ("pointer", desc.get("name", "void"))
    else:
        return (kind, desc.get("name", "unknown"))


def can_generate_function(func_entry):
    """Check if we can generate a NAPI binding for this function."""
    name = func_entry["name"]
    
    if name in EXCLUDED_FUNCTIONS:
        return False, "excluded"
    
    if func_entry.get("is_internal", False):
        return False, "internal"
    
    arguments = func_entry.get("arguments", [])
    
    # Check all arguments
    for arg in arguments:
        type_desc = arg.get("type", {}).get("description", {})
        kind = type_desc.get("kind", "unknown")
        
        if kind == "Pointer":
            return False, "has pointer argument"
        elif kind == "User":
            user_name = type_desc.get("name", "")
            return False, "has user arg: " + user_name
    
    # Check return type
    ret_type = func_entry.get("return_type", {})
    ret_desc = ret_type.get("description", {})
    ret_kind = ret_desc.get("kind", "unknown")
    
    if ret_kind == "Pointer":
        return False, "returns pointer"
    elif ret_kind == "User":
        user_name = ret_desc.get("name", "")
        return False, "returns user type: " + user_name
    
    return True, "ok"


def get_cpp_type(type_entry):
    """Get the C++ type string for a type entry."""
    kind, details = get_type_info(type_entry)
    
    if kind == "builtin":
        return BUILTIN_TO_NAPI_TYPE.get(details, "void")
    elif kind == "user":
        return details
    elif kind == "pointer":
        return "void*"
    else:
        return "void"


def get_ts_type(type_entry):
    """Get the TypeScript type string for a type entry."""
    kind, details = get_type_info(type_entry)
    
    if kind == "builtin":
        return BUILTIN_TO_TS_TYPE.get(details, "unknown")
    elif kind == "user":
        return details
    else:
        return "unknown"


def get_napi_value_method(builtin_type):
    """Get the Napi::Number method to extract a value."""
    if builtin_type in ("float", "double"):
        return "FloatValue"
    elif builtin_type in ("int", "short", "char", "long_long"):
        return "Int32Value"
    elif "unsigned" in builtin_type:
        return "Uint32Value"
    else:
        return "FloatValue"


def generate_function_cpp(func_entry):
    """Generate C++ NAPI binding code for a function."""
    name = func_entry["name"]
    arguments = func_entry.get("arguments", [])
    ret_type = func_entry.get("return_type", {})
    
    ret_kind, ret_details = get_type_info(ret_type)
    
    if ret_kind == "builtin":
        ret_str = BUILTIN_TO_NAPI_TYPE.get(ret_details, "void")
    elif ret_kind == "void":
        ret_str = "void"
    else:
        ret_str = "void"
    
    lines = []
    func_sig = "Napi::Value " + name + "(const Napi::CallbackInfo& info)"
    lines.append(func_sig)
    lines.append("{")
    lines.append("  Napi::Env env = info.Env();")
    lines.append("")
    
    # Extract arguments from JS
    js_idx = 0
    call_args = []
    for i, arg in enumerate(arguments):
        arg_name = arg.get("name", "arg" + str(i))
        if arg_name == "self":
            continue
        type_entry = arg.get("type", {})
        kind, details = get_type_info(type_entry)
        
        if kind == "builtin":
            napi_method = get_napi_value_method(details)
            cpp_type = BUILTIN_TO_NAPI_TYPE.get(details, "float")
            lines.append("  " + cpp_type + " " + arg_name + " = info[" + str(js_idx) + "].As<Napi::Number>()." + napi_method + "();")
            call_args.append(arg_name)
            js_idx += 1
    
    lines.append("")
    
    if ret_kind == "builtin" and ret_details != "void":
        lines.append("  " + ret_str + " result = " + name + "(" + ", ".join(call_args) + ");")
        lines.append("  return Napi::Number::New(env, result);")
    elif ret_kind == "void":
        lines.append("  " + name + "(" + ", ".join(call_args) + ");")
        lines.append("  return env.Undefined();")
    else:
        lines.append("  " + name + "(" + ", ".join(call_args) + ");")
        lines.append("  return env.Undefined();")
    
    lines.append("}")
    
    return "\n".join(lines)


def generate_function_ts(func_entry):
    """Generate TypeScript declaration for a function."""
    name = func_entry["name"]
    arguments = func_entry.get("arguments", [])
    ret_type = func_entry.get("return_type", {})
    
    ret_kind, ret_details = get_type_info(ret_type)
    
    arg_strs = []
    for arg in arguments:
        arg_name = arg.get("name", "arg")
        if arg_name == "self":
            continue
        ts_type = get_ts_type(arg.get("type", {}))
        arg_strs.append(arg_name + ": " + ts_type)
    
    if ret_kind == "builtin":
        ret_ts = BUILTIN_TO_TS_TYPE.get(ret_details, "void")
    else:
        ret_ts = "void"
    
    return "function " + name + "(" + ", ".join(arg_strs) + "): " + ret_ts + ";"


def process_functions(bindings):
    """Generate NAPI C++ bindings for functions."""
    all_functions = bindings.get("functions", [])
    
    print("")
    print("Function analysis (total: " + str(len(all_functions)) + "):")
    
    can_generate = []
    
    for func in all_functions:
        func_name = func["name"]
        gen, reason = can_generate_function(func)
        if gen:
            can_generate.append(func)
            print("  [GEN] " + func_name)
        else:
            print("  [SKIP] " + func_name + ": " + reason)
    
    print("")
    print("Can generate: " + str(len(can_generate)))
    
    if not can_generate:
        return []
    
    # Generate header content
    h_lines = [
        "#pragma once",
        "#include <napi.h>",
        "",
        "void InitFunctions(Napi::Env env, Napi::Object exports);",
        "",
    ]
    for func in can_generate:
        func_name = func["name"]
        ret_type = func.get("return_type", {})
        ret_kind, ret_details = get_type_info(ret_type)
        if ret_kind == "builtin":
            ret_str = BUILTIN_TO_NAPI_TYPE.get(ret_details, "void")
        elif ret_kind == "void":
            ret_str = "void"
        else:
            ret_str = "void"
        h_lines.append("Napi::Value " + func_name + "(const Napi::CallbackInfo& info);")
    
    h_content = "\n".join(h_lines)
    h_file = GEN_NAPI / "functions.h"
    h_file.write_text(h_content)
    print("Generated " + str(h_file))
    
    # Generate C++ code
    cpp_lines = [
        "// AUTO-GENERATED - DO NOT EDIT",
        "#include <napi.h>",
        "#include \"dcimgui.h\"",
        "#include \"functions.h\"",
        "",
    ]
    
    # Add function definitions
    for func in can_generate:
        func_name = func["name"]
        cpp_lines.append(generate_function_cpp(func))
        cpp_lines.append("")
    
    # Add InitFunctions
    cpp_lines.append("void InitFunctions(Napi::Env env, Napi::Object exports) {")
    for func in can_generate:
        func_name = func["name"]
        cpp_lines.append("  exports.Set(\"" + func_name + "\", Napi::Function::New(env, " + func_name + "));")
    cpp_lines.append("}")
    
    cpp_content = "\n".join(cpp_lines)
    cpp_file = GEN_NAPI / "functions.cpp"
    cpp_file.write_text(cpp_content)
    print("Generated " + str(cpp_file))
    
    # Write TS declarations
    ts_lines = []
    for func in can_generate:
        ts_lines.append(generate_function_ts(func))
    
    ts_content = "\n".join(ts_lines)
    ts_file = GEN_DTS / "functions.d.ts"
    ts_file.write_text(ts_content)
    print("Generated " + str(ts_file))
    
    return can_generate
