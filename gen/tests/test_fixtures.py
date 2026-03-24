import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def make_arg(name, kind, **kwargs):
    desc = {'kind': kind, **kwargs}
    return {'name': name, 'type': {'description': desc}}


def make_builtin_arg(name, bt, default=None):
    a = {
        'name': name,
        'type': {'description': {'kind': 'Builtin', 'builtin_type': bt}},
        'is_varargs': False,
        'is_array': False,
        'is_instance_pointer': False,
    }
    if default is not None:
        a['default_value'] = default
    return a


def make_ptr_arg(name, inner_kind, inner_bt=None, inner_name=None, storage=None, default=None):
    inner = {'kind': inner_kind}
    if inner_bt:
        inner['builtin_type'] = inner_bt
    if inner_name:
        inner['name'] = inner_name
    if storage:
        inner['storage_classes'] = storage
    a = {
        'name': name,
        'is_varargs': False,
        'is_array': False,
        'type': {'description': {'kind': 'Pointer', 'inner_type': inner}},
    }
    if default is not None:
        a['default_value'] = default
    return a


class FakeTypedefs:
    def resolve(self, name):
        return None

    def is_function_pointer(self, name):
        return False


class FakeRegistry:
    def __init__(self):
        self.typedefs = FakeTypedefs()

    def resolve_array_bound(self, b):
        return int(b) if b.isdigit() else None
