#!/usr/bin/env python3

import json
from pathlib import Path

from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from processor.enum import process_enums
from processor.typedef import process_typedefs
from processor.struct import process_structs
from processor.func import process_functions
from processor.backend import process_backends


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

    processed_enums, count_values = process_enums(bindings)
    processed_typedefs = process_typedefs(bindings, processed_enums)
    processed_structs = process_structs(bindings, processed_enums, processed_typedefs, count_values)
    process_functions(bindings, processed_enums, processed_typedefs, processed_structs)

    print("Generating backend wrappers")
    process_backends()

    print("All done")

if __name__ == "__main__":
    main()
