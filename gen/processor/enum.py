from config import GEN_DTS
from config import GEN_NAPI

ENUMS_CPP_FORMAT= """
#include <napi.h>

void InitEnums(Napi::Env env, Napi::Object exports)
{
  Napi::Object enums = Napi::Object::New(env);
  Napi::Function freeze = env
    .Global()
    .Get("Object")
    .As<Napi::Object>()
    .Get("freeze")
    .As<Napi::Function>();

  {enums}
}
"""


def process_enums(bindings):
    """
        Process typedefs from the bindings and generate DTS files and C++ napi code.
    """

    generated_enums = {}

    enums = bindings["enums"]
    for enum in enums:
        name: str = enum["name"]

        generated_entries = {}

        for element in enum["elements"]:
            is_internal = element["is_internal"]
            is_count = element["is_count"]

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

        if name.startswith("ImGui"):
            name = name.removeprefix("ImGui")
        elif name.startswith("Im"):
            name = name.removeprefix("Im")

        name = name.removesuffix("_")
        name = name.removeprefix("_")

        generated_enums[name] = generated_entries

    lines = []

    for name, entries in generated_enums.items():
        lines.append(f"Napi::Object _{name} = Napi::Object::New(env);")

        for element_name, element_value in entries.items():
            lines.append(f'_{name}["{element_name}"] = Napi::Number::New(env, {element_value});')

        lines.append(f'freeze.Call({{_{name}}});')
        lines.append(f'enums["{name}"] = _{name};')
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
    cpp_file.write_text(enum_cpp)

    dts_file = GEN_DTS / "enums.d.ts"
    dts_file.write_text(enum_dts)
