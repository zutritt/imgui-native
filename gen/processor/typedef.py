from __future__ import annotations

from config import GEN_DTS
from processor.ts_names import make_unique_ts_identifiers

EXCLUDED_TYPEDEFS = [
    # Support for custom allocators is not planned
    # Perhaps those can be added in the future
    "ImGuiMemAllocFunc",
    "ImGuiMemFreeFunc"
]

BUILTIN_TYPE_TO_TS_TYPE = {
    "bool": "boolean",
    "float": "number",
    "double": "number",
    "unsigned_int": "number",
    "unsigned_short": "number",
    "unsigned_char": "number",
    "int": "number",
    "short": "number",
    "char": "number",
    "long_long": "bigint",
    "unsigned_long_long": "bigint",
}


def _strip_imgui_prefix(name: str) -> str:
    if name.startswith("ImGui"):
        return name.removeprefix("ImGui")
    if name.startswith("Im"):
        return name.removeprefix("Im")
    return name


def _resolve_user_ts_type(
    target_name: str,
    typedefs_by_name: dict,
    type_declarations: dict,
    processed_enums: dict,
) -> str:
    if target_name == "size_t":
        return "number"

    if target_name in processed_enums:
        return processed_enums[target_name]

    underscored = f"{target_name}_"
    if underscored in processed_enums:
        return processed_enums[underscored]

    # Typedefs can alias other typedefs declared earlier in this pass.
    if target_name in type_declarations:
        return type_declarations[target_name]["name"]

    # Typedef referenced before it was visited in this pass.
    if target_name in typedefs_by_name:
        return _strip_imgui_prefix(target_name)

    # Non-typedef user type is typically a struct/class from structs.d.ts.
    return f'import("./structs").{_strip_imgui_prefix(target_name)}'


def _callback_ts_type_from_description(
    desc: dict,
    typedefs_by_name: dict,
    type_declarations: dict,
    processed_enums: dict,
) -> str:
    kind = desc.get("kind")

    if kind == "Builtin":
        builtin_type = desc.get("builtin_type")
        if builtin_type == "void":
            return "void"
        return BUILTIN_TYPE_TO_TS_TYPE.get(builtin_type, "unknown")

    if kind == "User":
        target_name = desc.get("name", "")
        return _resolve_user_ts_type(target_name, typedefs_by_name, type_declarations, processed_enums)

    if kind == "Pointer":
        inner = desc.get("inner_type", {})
        inner_kind = inner.get("kind")
        storage_classes = inner.get("storage_classes", [])

        if inner_kind == "Builtin":
            inner_builtin = inner.get("builtin_type")
            if inner_builtin == "char" and "const" in storage_classes:
                return "string"
            if inner_builtin == "void":
                return "unknown"
            # Generic raw data pointers remain opaque for now.
            return "unknown"

        if inner_kind == "User":
            target_name = inner.get("name", "")
            return _resolve_user_ts_type(target_name, typedefs_by_name, type_declarations, processed_enums)

        if inner_kind == "Function":
            return "CallbackRef<(...args: unknown[]) => unknown>"

        return "unknown"

    if kind == "Type":
        inner = desc.get("inner_type")
        if isinstance(inner, dict):
            return _callback_ts_type_from_description(inner, typedefs_by_name, type_declarations, processed_enums)
        return "unknown"

    if kind == "Array":
        inner = desc.get("inner_type", {})
        if inner.get("kind") != "Builtin":
            return "unknown"

        inner_builtin = inner.get("builtin_type")
        if inner_builtin == "float":
            return "Float32Array"
        if inner_builtin in ("int", "short"):
            return "Int32Array"
        if inner_builtin in ("unsigned_int", "unsigned_short", "unsigned_char"):
            return "Uint32Array"
        if inner_builtin == "char":
            return "string"
        return "unknown"

    return "unknown"


def _build_callback_ref_signature(
    type_details: dict,
    typedefs_by_name: dict,
    type_declarations: dict,
    processed_enums: dict,
) -> str:
    arguments = type_details.get("arguments", [])
    raw_arg_names = [
        arg.get("name") or f"arg{idx + 1}"
        for idx, arg in enumerate(arguments)
    ]
    arg_names = make_unique_ts_identifiers(raw_arg_names)

    ts_params = []
    for idx, arg in enumerate(arguments):
        desc = arg.get("type", {}).get("description", {})
        ts_type = _callback_ts_type_from_description(
            desc,
            typedefs_by_name,
            type_declarations,
            processed_enums,
        )
        ts_params.append(f"{arg_names[idx]}: {ts_type}")

    return_desc = type_details.get("return_type", {}).get("description", {})
    return_type = _callback_ts_type_from_description(
        return_desc,
        typedefs_by_name,
        type_declarations,
        processed_enums,
    )

    args = ", ".join(ts_params)
    return f"CallbackRef<({args}) => {return_type}>"

def process_typedefs(bindings, processed_enums):
    """
        Process typedefs from the bindings and generate DTS files.
        Typedefs are additional named types, so they don't need any napi code,
        but thet will be preserved in DTS for better readability.
    """

    typedefs = bindings["typedefs"]
    typedefs_by_name = { t["name"]: t for t in typedefs }

    type_declarations = {}

    def declare_type(name: str, ts_type: str, builtin_type: str, comment: str | None = None):
        if name in type_declarations:
            current_ts_type = type_declarations[name]["ts_type"]
            print(f"Duplicate typedef {name=}, investigate: {current_ts_type} {ts_type=}")

        renamed = _strip_imgui_prefix(name)

        type_declarations[name] = {
            "name": renamed,
            "ts_type": ts_type,
            "builtin_type": builtin_type,
            "comment": comment
        }

    for name, typedef in typedefs_by_name.items():
        if name in EXCLUDED_TYPEDEFS:
            continue

        if typedef["is_internal"]:
            print(f"Skipping internal typedef: {name}")
            continue

        type_info = typedef["type"]
        type_info_description = type_info["description"]
        type_kind = type_info_description["kind"]

        if type_kind == "Builtin":
            # This typedef resolves directly to a builtin

            builtin_type = type_info_description["builtin_type"]
            ts_type = BUILTIN_TYPE_TO_TS_TYPE.get(builtin_type)

            if ts_type is None:
                print(f"Cannot map {name=} {builtin_type=} to ts type")
                continue

            declare_type(name, ts_type, builtin_type)

        elif type_kind == "User":
            # This typedef resolves to another typedef, function pointer or struct

            target_name = type_info_description["name"]
            if target_name not in typedefs_by_name:
                # TODO: remove short circuit, for now we just generate is a unknown ts type
                # This is because some downstream types might depend on this one
                declare_type(
                    name,
                    "unknown",
                    "<unknown>",
                    "Struct or enum or other user defined type"
                )
                continue

                # This does not point to antother typedef, perhaps its a struct
                # TODO update logic to handle those

                print(f"Unknown typedef target {name=} {type_kind=} {target_name=}")
                continue
            else:
                if target_name in type_declarations:
                    renamed = type_declarations[target_name]["name"]
                    builtin_type = type_declarations[target_name]["builtin_type"]
                else:
                    renamed = _strip_imgui_prefix(target_name)
                    builtin_type = "<unknown>"
                declare_type(name, renamed, builtin_type)

            # Now we know we know that resulting type will be just an alias to another one
        elif type_kind == "Type":
            # This is how function pointers are represented, the tricky part is - how to convert
            # them to ts types? Structure might be mapped via other parts of this generator, but
            # we need to know what do those functions return and take as args in js land

            type_details = type_info["type_details"]
            flavour = type_details["flavour"]

            if flavour == "function_pointer":
                callback_signature = _build_callback_ref_signature(
                    type_details,
                    typedefs_by_name,
                    type_declarations,
                    processed_enums,
                )

                declare_type(
                    name,
                    callback_signature,
                    "<function_pointer>",
                )
                continue

            else:
                print(f"Unknown typedef type for {name}: {type_kind} with flavour {flavour}")
                continue

        else:
            print(f"Unknown typedef type for {name}: {type_kind}")
            continue

    lines = []
    for name, info in type_declarations.items():
        if name in processed_enums or f'{name}_' in processed_enums:
            # ImGui defines enums, but uses _ after the name, and then defines name without
            # underscore as a typedef of integer - this gives a type hint to programmer
            # but we don't have to replicate that behaviour, so we are skipping typedefs
            # that point to enums. We still want to have ultimate resoltuion table
            # for those types, so this filtering step is performed here
            continue

        renamed = info["name"]

        if "comment" in info and info["comment"] is not None:
            lines.append(f"export type {renamed} = {info['ts_type']}; // {info['comment']}")
        else:
            lines.append(f"export type {renamed} = {info['ts_type']};")

    prelude = [
        "// Auto-generated — do not edit.",
        'import type { CallbackRef } from "../../dts/ref";',
        "",
    ]
    enum_dts = "\n".join(prelude + lines) + "\n"

    dts_file = GEN_DTS / "typedefs.d.ts"
    dts_file.write_text(enum_dts, encoding="utf-8")

    return type_declarations
