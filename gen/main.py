from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from data.loader import load_bindings
from data.registry import Registry
from generators.callbacks import generate_callbacks
from generators.enums import generate_enums
from generators.functions import generate_functions
from generators.structs import generate_structs


def clean_dir(path):
    if path.exists():
        for f in path.iterdir():
            if f.is_file():
                f.unlink()
    path.mkdir(parents=True, exist_ok=True)


def main():
    if not BINDINGS_FILE.exists():
        raise SystemExit('Bindings file not found')
    clean_dir(GEN_NAPI)
    clean_dir(GEN_DTS)
    bindings = load_bindings(BINDINGS_FILE)
    registry = Registry(bindings)
    generate_callbacks(registry)
    generate_enums(registry)
    generate_structs(registry)
    skipped = generate_functions(registry)
    print(f'Enums: {len(registry.enums)}')
    by_val = len(registry.by_value_structs)
    ctx = len([s for s in registry.opaque_structs if s['name'] == 'ImGuiContext'])
    from config import SKIP_STRUCTS

    regular = len([s for s in registry.regular_structs if s['name'] not in SKIP_STRUCTS])
    print(f'Structs: {by_val + ctx + regular} generated')
    print(f'Functions: {len(registry.free_functions) - skipped} generated, {skipped} skipped')


if __name__ == '__main__':
    main()
