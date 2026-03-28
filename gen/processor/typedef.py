from config import GEN_DTS

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

def process_typedefs(bindings):
    """
        Process typedefs from the bindings and generate DTS files.
        Typedefs are additional named types, so they don't need any napi code,
        but thet will be preserved in DTS for better readability.
    """

    ultimate_builtin_types = {}

    typedefs = bindings["typedefs"]
    typedefs_by_name = { t["name"]: t for t in typedefs }

    type_declarations = {}

    def declare_type(name: str, ts_type: str, comment: str | None = None):
        if name in type_declarations:
            current_ts_type = type_declarations[name].ts_type
            print(f"Duplicate typedef {name=}, investigate: {current_ts_type} {ts_type=}")

        type_declarations[name] = {
            "name": name,
            "ts_type": ts_type,
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

            declare_type(name, ts_type)
            ultimate_builtin_types[name] = builtin_type

        elif type_kind == "User":
            # This typedef resolves to another typedef, function pointer or struct

            target_name = type_info_description["name"]
            if target_name not in typedefs_by_name:
                # TODO: remove short circuit, for now we just generate is a unknown ts type
                # This is because some downstream types might depend on this one
                declare_type(name, "unknown", "Struct or enum or other user defined type")
                continue

                # This does not point to antother typedef, perhaps its a struct
                # TODO update logic to handle those

                print(f"Unknown typedef target {name=} {type_kind=} {target_name=}")
                continue
            else:
                declare_type(name, target_name)
                ultimate_builtin_types[name] = ultimate_builtin_types[target_name]

            # Now we know we know that resulting type will be just an alias to another one
        elif type_kind == "Type":
            # This is how function pointers are represented, the tricky part is - how to convert
            # them to ts types? Structure might be mapped via other parts of this generator, but
            # we need to know what do those functions return and take as args in js land

            type_details = type_info["type_details"]
            flavour = type_details["flavour"]

            if flavour == "function_pointer":
                _arguments = type_details["arguments"]
                _return_type = type_details["return_type"]

                # TODO process function

                declare_type(name, "CallbackRef<(...args: unknown[]) => unknown>",
                             "Function pointer not supported yet")
                continue

            else:
                print(f"Unknown typedef type for {name}: {type_kind} with flavour {flavour}")
                continue

        else:
            print(f"Unknown typedef type for {name}: {type_kind}")
            continue


    lines = []
    for name, info in type_declarations.items():
        if "comment" in info and info["comment"] is not None:
            lines.append(f"type {name} = {info["ts_type"]}; // {info["comment"]}")
        else:
            lines.append(f"type {name} = {info["ts_type"]};")

    enum_dts = "\n".join(lines)

    dts_file = GEN_DTS / "typedefs.d.ts"
    dts_file.write_text(enum_dts)

    return ultimate_builtin_types
