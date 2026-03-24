from core.text import braced
from core.text import lines


class CppFile:
    def __init__(self):
        self._includes: list[str] = []
        self._blocks: list[str] = []

    def include(self, header: str):
        self._includes.append(f'#include <{header}>')
        return self

    def blank(self):
        self._blocks.append('')
        return self

    def raw(self, text: str):
        self._blocks.append(text)
        return self

    def function(self, signature: str, body: str):
        self._blocks.append(braced(signature, body))
        return self

    def render(self) -> str:
        parts = []
        if self._includes:
            parts.append(lines(self._includes))
        parts.extend(self._blocks)
        return lines(parts)


class CppObject:
    def __init__(self, var_name: str):
        self.var = var_name
        self._sets: list[str] = []

    def set(self, key: str, value_expr: str):
        self._sets.append(f'{self.var}.Set("{key}", {value_expr});')
        return self

    def render(self) -> str:
        return lines(self._sets)


class CppScope:
    def __init__(self):
        self._lines: list[str] = []

    def stmt(self, code: str):
        self._lines.append(f'{code};')
        return self

    def raw(self, text: str):
        self._lines.append(text)
        return self

    def blank(self):
        self._lines.append('')
        return self

    def block(self, header: str, body: str):
        self._lines.append(braced(header, body))
        return self

    def render(self) -> str:
        return lines(self._lines)
