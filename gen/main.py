#!/usr/bin/env python3

import json
from pathlib import Path

from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from processor.enum import process_enums
from processor.struct_ import process_structs
from processor.typedef import process_typedefs
from processor.function_ import process_functions


def clean_dir(path: Path):
    if path.exists():
        for f in path.iterdir():
            if f.is_file():
                f.unlink()

    path.mkdir(parents=True, exist_ok=True)


def main():
    if not BINDINGS_FILE.exists():
        raise SystemExit(f"Bindings file not found: {BINDINGS_FILE}")

    print("Bindings file found")

    clean_dir(GEN_NAPI)
    clean_dir(GEN_DTS)

    print("Output directories cleaned")

    try:
        bindings = json.loads(BINDINGS_FILE.read_text())
    except Exception as err:
        raise SystemExit(f"Failed to read and decode bindings file: {BINDINGS_FILE}") from err

    print("File loaded, generating bindings")

    process_enums(bindings)
    process_structs(bindings)
    process_typedefs(bindings)
    process_functions(bindings)

    print("All done")

if __name__ == "__main__":
    main()
