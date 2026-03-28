from config import GEN_NAPI

# Enums to exclude from generation (internal or not needed)
EXCLUDED_ENUMS = [
    # Add enum names here if they should be skipped
]

def process_enums(bindings):
    """
    Generate enum types and NAPI C++ bindings for constants defined in the bindings file.
    """
    
    enums_from_bindings = bindings.get("enums", [])
    
    generated_enum_blocks = []
    
    for enum_entry in enums_from_bindings:
        enum_name = enum_entry["name"]
        
        if enum_name in EXCLUDED_ENUMS:
            print(f"Skipping excluded enum: {enum_name}")
            continue
        
        if enum_entry.get("is_internal", False):
            print(f"Skipping internal enum: {enum_name}")
            continue
        
        stripped_enum_name = enum_name.rstrip("_")
        
        elements = enum_entry.get("elements", [])
        
        element_lines = []
        for element in elements:
            element_name = element["name"]
            element_value = element["value"]
            
            prefix_to_strip = enum_name + "_"
            if element_name.startswith(prefix_to_strip):
                stripped_element_name = element_name[len(prefix_to_strip):]
            else:
                stripped_element_name = element_name
            
            cpp_line = f'  _{stripped_enum_name}.Set("{stripped_element_name}", Napi::Number::New(env, {element_value}));'
            element_lines.append(cpp_line)
        
        generated_enum_blocks.append((stripped_enum_name, element_lines))
    
    # Build the C++ code for enums.cpp
    cpp_code_lines = [
        "// AUTO-GENERATED - DO NOT EDIT",
        "#include <napi.h>",
        "#include \"enums.h\"",
        "",
        "void InitEnums(Napi::Env env, Napi::Object exports)",
        "{",
        "  Napi::Object enums = Napi::Object::New(env);",
        '  Napi::Function freeze = env.Global().Get("Object").As<Napi::Object>().Get("freeze").As<Napi::Function>();',
        ""
    ]
    
    for enum_name, lines in generated_enum_blocks:
        cpp_code_lines.append(f"  Napi::Object _{enum_name} = Napi::Object::New(env);")
        cpp_code_lines.extend(lines)
        cpp_code_lines.append(f"  freeze.Call({{_{enum_name}}});")
        cpp_code_lines.append(f'  enums.Set("{enum_name}", _{enum_name});')
        cpp_code_lines.append("")
    
    cpp_code_lines.extend([
        "  freeze.Call({enums});",
        '  exports.Set("enums", enums);',
        "}",
        ""
    ])
    
    newline = chr(10)
    cpp_code = newline.join(cpp_code_lines)
    
    cpp_file = GEN_NAPI / "enums.cpp"
    cpp_file.write_text(cpp_code)
    print(f"Generated {cpp_file}")
    
    # Write enums.h header
    h_code = (
        "// AUTO-GENERATED - DO NOT EDIT\n"
        "#pragma once\n"
        "#include <napi.h>\n"
        "\n"
        "void InitEnums(Napi::Env env, Napi::Object exports);\n"
    )
    
    h_file = GEN_NAPI / "enums.h"
    h_file.write_text(h_code)
    print(f"Generated {h_file}")
