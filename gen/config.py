from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

BINDINGS_FILE = ROOT_DIR / 'lib' / 'gen' / 'bindings' / 'dcimgui.json'

GEN_NAPI = ROOT_DIR / 'lib' / 'gen' / 'napi'
GEN_DTS = ROOT_DIR / 'lib' / 'gen' / 'dts'
GEN_BACKENDS = ROOT_DIR / 'lib' / 'gen' / 'backends'
GEN_BACKEND_NAPI = ROOT_DIR / 'lib' / 'gen' / 'backend_napi'
SRC_DIR = ROOT_DIR / 'src'
