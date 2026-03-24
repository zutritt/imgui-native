from core.text import indent
from core.text import lines


class DtsClass:
    def __init__(self, name: str):
        self._name = name
        self._members: list[str] = []

    def member(self, text: str):
        self._members.append(text)
        return self

    def blank(self):
        self._members.append('')
        return self

    def render(self) -> str:
        body = indent(lines(self._members))
        return f'export class {self._name} {{\n{body}\n}}'


class DtsFile:
    def __init__(self):
        self._blocks: list[str] = []

    def raw(self, text: str):
        self._blocks.append(text)
        return self

    def blank(self):
        self._blocks.append('')
        return self

    def render(self) -> str:
        return lines(self._blocks)


class DtsObject:
    def __init__(self, name: str, kind: str = 'readonly'):
        self._name = name
        self._kind = kind
        self._members: list[str] = []

    def field(self, name: str, ts_type: str, readonly: bool = True):
        prefix = 'readonly ' if readonly else ''
        self._members.append(f'{prefix}{name}: {ts_type};')
        return self

    def render(self) -> str:
        body = indent(lines(self._members))
        return f'{self._kind} {self._name}: {{\n{body}\n}};'


class DtsNamespace:
    def __init__(self, name: str):
        self._name = name
        self._members: list[str] = []

    def member(self, text: str):
        self._members.append(text)
        return self

    def blank(self):
        self._members.append('')
        return self

    def render(self) -> str:
        body = indent(lines(self._members))
        return f'declare const {self._name}: {{\n{body}\n}};'
