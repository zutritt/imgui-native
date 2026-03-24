from textwrap import indent as _indent


def indent(text: str, level: int = 1, prefix: str = '  ') -> str:
    """
    >>> indent('a\\nb', 1)
    '  a\\n  b'
    >>> indent('x', 2)
    '    x'
    """
    return _indent(text, prefix * level)


def lines(parts: list[str]) -> str:
    """
    >>> lines(['a', 'b', 'c'])
    'a\\nb\\nc'
    """
    return '\n'.join(parts)


def braced(header: str, body: str) -> str:
    """
    >>> braced('void f()', 'return;')
    'void f()\\n{\\n  return;\\n}'
    """
    return f'{header}\n{{\n{indent(body)}\n}}'


def spaced(*blocks: str) -> str:
    """Join blocks with double newlines (blank line between each).

    >>> spaced('a', 'b')
    'a\\n\\nb'
    """
    return '\n\n'.join(b for b in blocks if b)
