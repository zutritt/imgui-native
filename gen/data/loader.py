import json
from pathlib import Path

REQUIRED_KEYS = {'defines', 'enums', 'typedefs', 'structs', 'functions'}


def load_bindings(path: Path) -> dict:
    with open(path) as f:
        data = json.load(f)

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f'Bindings JSON missing keys: {missing}')

    for key in REQUIRED_KEYS:
        if not isinstance(data[key], list):
            raise ValueError(f'Expected list for "{key}", got {type(data[key]).__name__}')

    return data
