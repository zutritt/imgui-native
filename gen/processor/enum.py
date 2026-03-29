from config import GEN_DTS
from config import GEN_NAPI

ENUMS_CPP_FORMAT = """
#include "enums_init.h"

void InitEnums(Napi::Env env, Napi::Object exports)
{
  Napi::Function freeze = env
    .Global()
    .Get("Object")
    .As<Napi::Object>()
    .Get("freeze")
    .As<Napi::Function>();

  {enums}
}
"""

ENUMS_INIT_H = """#pragma once
#include <napi.h>

// Register all generated ImGui enum objects on exports.
// Called once from module.cpp Init().
void InitEnums(Napi::Env env, Napi::Object exports);
"""


def process_enums(bindings):
    """
        Process enums from the bindings and generate DTS files and C++ napi code.

        Returns a tuple of:
          enum_names:   dict mapping original C enum name → stripped JS name
          count_values: dict mapping count constant name → resolved int value
                        (e.g. "ImGuiCol_COUNT" → 62). Needed by the struct
                        processor to resolve fixed-array bounds like
                        `ImVec4 Colors[ImGuiCol_COUNT]`.
    """

    generated_enums = {}
    enum_names = {}
    # Collect is_count elements separately — they are excluded from the public
    # enum objects but the struct processor needs their numeric values to size
    # fixed C arrays (e.g. ImGuiCol_COUNT, ImGuiKey_NamedKey_COUNT).
    count_values = {}

    enums = bindings["enums"]
    for enum in enums:
        name: str = enum["name"]

        generated_entries = {}

        for element in enum["elements"]:
            is_internal = element["is_internal"]
            is_count = element["is_count"]

            if is_count:
                # Record ALL count constants (including internal ones) so that
                # struct array-bound resolution works (e.g. ImGuiKey_NamedKey_COUNT).
                count_values[element["name"]] = element["value"]

            if is_internal or is_count:
                continue

            element_name: str = element["name"]
            element_value: int = element["value"]

            simplified_element_name = element_name.removeprefix(name)
            if simplified_element_name == element_name:
                # Special case mapping for key modifiers
                if simplified_element_name.startswith("ImGuiMod_"):
                    simplified_element_name = "Mod" + \
                        simplified_element_name.removeprefix("ImGuiMod_")
                else:
                    print(f"{element_name=} is not prefixed with enum {name=}")
                    continue

            simplified_element_name = simplified_element_name.removeprefix("_")

            if simplified_element_name[0].isdigit():
                simplified_element_name = "_" + simplified_element_name

            generated_entries[simplified_element_name] = element_value

        raw_name = name

        if name.startswith("ImGui"):
            name = name.removeprefix("ImGui")
        elif name.startswith("Im"):
            name = name.removeprefix("Im")

        name = name.removesuffix("_")
        name = name.removeprefix("_")

        generated_enums[name] = generated_entries
        enum_names[raw_name] = name

    lines = []

    for name, entries in generated_enums.items():
        lines.append(f"Napi::Object _{name} = Napi::Object::New(env);")

        for element_name, element_value in entries.items():
            lines.append(f'_{name}["{element_name}"] = Napi::Number::New(env, {element_value});')

        lines.append(f'freeze.Call({{_{name}}});')
        lines.append(f'exports["{name}"] = _{name};')
        lines.append("")

    enum_cpp = ENUMS_CPP_FORMAT.replace("{enums}", "\n  ".join(lines).strip())

    lines = []

    for name, entries in generated_enums.items():
        lines.append(f'export enum {name} {{')

        for element_name, element_value in entries.items():
            lines.append(f'  {element_name} = {element_value},')

        lines.append("}")
        lines.append("")

    enum_dts = "\n".join(lines)

    cpp_file = GEN_NAPI / "enums.cpp"
    cpp_file.write_text(enum_cpp, encoding="utf-8")

    hdr_file = GEN_NAPI / "enums_init.h"
    hdr_file.write_text(ENUMS_INIT_H, encoding="utf-8")

    dts_file = GEN_DTS / "enums.d.ts"
    dts_file.write_text(enum_dts, encoding="utf-8")

    return enum_names, count_values
