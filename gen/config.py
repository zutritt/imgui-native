from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

BINDINGS_FILE = ROOT_DIR / 'lib' / 'gen' / 'bindings' / 'dcimgui.json'

GEN_NAPI = ROOT_DIR / 'lib' / 'gen' / 'napi'
GEN_DTS = ROOT_DIR / 'lib' / 'gen' / 'dts'

NEEDS_CPP_CONSTRUCTOR = {
    'ImFontConfig',
    'ImGuiWindowClass',
    'ImGuiSelectionBasicStorage',
}

OWNED_RETURNS = {
    'ImDrawList_CloneOutput': 'IM_DELETE',
}
