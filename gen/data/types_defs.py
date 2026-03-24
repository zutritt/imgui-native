from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as _f


@dataclass
class ParamInfo:
    decls: list[str] = _f(default_factory=list)
    c_arg: str = ''
    ts_type: str = 'unknown'
    consumed_next: bool = False
    size_c_arg: str = ''
    is_out: bool = False
    out_c_type: str = ''


@dataclass
class RetInfo:
    wrap: str = ''
    ts_type: str = 'unknown'
