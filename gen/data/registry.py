from data.typedefs import TypedefResolver


class Registry:
    def __init__(self, bindings: dict):
        self.raw = bindings
        self.typedefs = TypedefResolver(bindings['typedefs'])

        self.enums = bindings['enums']
        self.all_structs = bindings['structs']
        self.all_functions = bindings['functions']
        self.defines = bindings['defines']

        self._classify_structs()
        self._classify_functions()
        self._build_enum_counts()
        self._build_helper_index()
        self._build_owned_structs()

    def _classify_structs(self):
        self.by_value_structs = []
        self.opaque_structs = []
        self.imvector_structs = []
        self.regular_structs = []

        for s in self.all_structs:
            name = s['name']
            if s.get('by_value'):
                self.by_value_structs.append(s)
            elif s.get('forward_declaration'):
                self.opaque_structs.append(s)
            elif name.startswith('ImVector_'):
                self.imvector_structs.append(s)
            else:
                self.regular_structs.append(s)

    def _classify_functions(self):
        self.helpers = []
        self.free_functions = []
        self.methods = []
        self.skipped_functions = []

        for f in self.all_functions:
            if f.get('is_default_argument_helper'):
                self.helpers.append(f)
                continue
            if f.get('is_manual_helper') or f.get('is_imstr_helper') or f.get('is_internal'):
                self.skipped_functions.append(f)
                continue
            if f.get('original_class'):
                self.methods.append(f)
            else:
                self.free_functions.append(f)

    def _build_enum_counts(self):
        self.enum_counts = {}
        for enum in self.enums:
            for el in enum['elements']:
                if el.get('is_count'):
                    self.enum_counts[el['name']] = el['value']

    def _build_helper_index(self):
        self.helper_names = {f['name'] for f in self.helpers}

    def _build_owned_structs(self):
        from config import OWNED_RETURNS

        fn_map = {f['name']: f for f in self.all_functions}
        self.owned_structs = {}
        for fn_name, delete_method in OWNED_RETURNS.items():
            fn = fn_map.get(fn_name)
            if not fn:
                continue
            ret = fn['return_type']['description']
            if ret['kind'] == 'Pointer' and ret['inner_type']['kind'] == 'User':
                self.owned_structs[ret['inner_type']['name']] = delete_method

    def has_helper(self, func_name: str) -> bool:
        if not func_name.endswith('Ex'):
            return False
        return func_name[:-2] in self.helper_names

    def methods_for(self, class_name: str) -> list[dict]:
        return [m for m in self.methods if m['original_class'] == class_name]

    def resolve_array_bound(self, bound: str) -> int | None:
        if bound.isdigit():
            return int(bound)
        return self.enum_counts.get(bound)
