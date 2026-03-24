from config import BINDINGS_FILE
from config import GEN_DTS
from config import GEN_NAPI
from data.loader import load_bindings
from data.registry import Registry
from generators.enums import generate_enums


def clean_dir(path):
    if path.exists():
        for file in path.iterdir():
            if file.is_file():
                file.unlink()
    path.mkdir(parents=True, exist_ok=True)


def main():
    if not BINDINGS_FILE.exists():
        raise SystemExit('Bindings file not found - generate them first')

    clean_dir(GEN_NAPI)
    clean_dir(GEN_DTS)

    bindings = load_bindings(BINDINGS_FILE)
    registry = Registry(bindings)

    generate_enums(registry)

    print(f'Generated: {len(registry.enums)} enums')
    print(f'Registry: {len(registry.all_structs)} structs, {len(registry.all_functions)} functions')


if __name__ == '__main__':
    main()
