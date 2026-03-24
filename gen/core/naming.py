def strip_imgui_prefix(name: str) -> str:
    """
    >>> strip_imgui_prefix('ImGuiIO')
    'IO'
    >>> strip_imgui_prefix('ImVec2')
    'Vec2'
    >>> strip_imgui_prefix('ImDrawList')
    'DrawList'
    >>> strip_imgui_prefix('Image')
    'Image'
    """
    if name.startswith('ImGui'):
        return name[5:]
    if name.startswith('Im') and len(name) > 2 and name[2].isupper():
        return name[2:]
    return name


def to_camel(name: str) -> str:
    """
    >>> to_camel('GetWindowPos')
    'getWindowPos'
    >>> to_camel('Begin')
    'begin'
    >>> to_camel('IO')
    'iO'
    >>> to_camel('')
    ''
    """
    if not name:
        return name
    return name[0].lower() + name[1:]


def struct_name(c_name: str) -> str:
    """
    >>> struct_name('ImGuiIO')
    'IO'
    >>> struct_name('ImDrawList')
    'DrawList'
    """
    return strip_imgui_prefix(c_name)


def enum_name(c_name: str) -> str:
    """
    >>> enum_name('ImGuiWindowFlags_')
    'WindowFlags'
    """
    return strip_imgui_prefix(c_name.rstrip('_'))


def enum_element(raw_element_name: str, enum_js_name: str) -> str:
    """Strip ImGui prefix then enum prefix from an element name.

    >>> enum_element('ImGuiWindowFlags_NoTitleBar', 'WindowFlags')
    'NoTitleBar'
    >>> enum_element('ImDrawFlags_None', 'DrawFlags')
    'None'
    """
    stripped = strip_imgui_prefix(raw_element_name)
    prefix = f'{enum_js_name}_'
    if stripped.startswith(prefix):
        return stripped[len(prefix) :]
    return stripped


def method_name(c_func: str, class_prefix: str, has_helper: bool) -> str:
    """
    >>> method_name('ImDrawList_AddLineEx', 'ImDrawList_', True)
    'addLine'
    >>> method_name('ImGuiListClipper_Begin', 'ImGuiListClipper_', False)
    'begin'
    """
    name = c_func.removeprefix(class_prefix)
    if has_helper and name.endswith('Ex'):
        name = name[:-2]
    return to_camel(name)


def free_fn_name(c_func: str, has_helper: bool) -> str:
    """
    >>> free_fn_name('ImGui_GetWindowPos', False)
    'getWindowPos'
    >>> free_fn_name('ImGui_DragFloatEx', True)
    'dragFloat'
    """
    name = c_func.removeprefix('ImGui_')
    if has_helper and name.endswith('Ex'):
        name = name[:-2]
    return to_camel(name)
