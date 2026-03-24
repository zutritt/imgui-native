EXTERNAL_TYPES = {
    'size_t': {'kind': 'Builtin', 'builtin_type': 'unsigned_int'},
}

FUNCTION_POINTER_TYPEDEFS = {
    'ImGuiInputTextCallback',
    'ImGuiSizeCallback',
    'ImGuiMemAllocFunc',
    'ImGuiMemFreeFunc',
    'ImDrawCallback',
}


class TypedefResolver:
    def __init__(self, typedefs: list[dict]):
        self._table = {}
        for td in typedefs:
            self._table[td['name']] = td['type']['description']

    def resolve(self, name: str) -> dict | None:
        if name in EXTERNAL_TYPES:
            return EXTERNAL_TYPES[name]

        seen = set()
        current = name
        while current in self._table:
            if current in seen:
                return None
            seen.add(current)
            desc = self._table[current]
            if desc['kind'] == 'Builtin':
                return desc
            if desc['kind'] == 'User':
                current = desc['name']
            else:
                return desc
        return None

    def is_function_pointer(self, name: str) -> bool:
        if name in FUNCTION_POINTER_TYPEDEFS:
            return True
        if name in self._table:
            desc = self._table[name]
            return desc.get('kind') == 'Type'
        return False

    def is_known(self, name: str) -> bool:
        return name in self._table or name in EXTERNAL_TYPES
