from config import BINDINGS_FILE, GEN_NAPI, GEN_DTS
from json import loads
from enums import generate_enums


if __name__ == '__main__':
    if not BINDINGS_FILE.exists():
        print('Bindings file not found - generate them first')
        exit(1)

    if GEN_NAPI.exists():
        for file in GEN_NAPI.iterdir():
            if file.is_file():
                file.unlink()

    if GEN_DTS.exists():
        for file in GEN_DTS.iterdir():
            if file.is_file():
                file.unlink()

    GEN_NAPI.mkdir(parents=True, exist_ok=True)
    GEN_DTS.mkdir(parents=True, exist_ok=True)

    try:
        with open(BINDINGS_FILE, 'r') as file:
            bindings = loads(file.read())
    except Exception:
        print('Failed to read bindings file')
        exit(1)

    generate_enums(bindings)

    print('All done!')
