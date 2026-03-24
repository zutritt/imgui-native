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

BORROW_ONLY = {
    'ImGuiIO',
    'ImGuiStyle',
    'ImDrawList',
    'ImFont',
    'ImFontAtlas',
    'ImGuiViewport',
    'ImDrawData',
    'ImGuiPlatformIO',
    'ImGuiMultiSelectIO',
    'ImDrawCmd',
    'ImDrawVert',
    'ImGuiKeyData',
    'ImGuiStoragePair',
    'ImGuiTableColumnSortSpecs',
    'ImGuiTableSortSpecs',
    'ImGuiPayload',
    'ImGuiInputEvent',
    'ImGuiPlatformMonitor',
    'ImGuiPlatformImeData',
    'ImGuiSelectionExternalStorage',
    'ImTextureData',
    'ImDrawCmdHeader',
    'ImDrawChannel',
    'ImDrawListSplitter',
    'ImFontGlyph',
    'ImFontAtlasRect',
    'ImFontBaked',
    'ImGuiSizeCallbackData',
    'ImGuiInputTextCallbackData',
    'ImGuiSelectionRequest',
    'ImTextureRect',
}

SKIP_STRUCTS = {'__anonymous_type0', '__anonymous_type1', 'ImGuiTextFilter_ImGuiTextRange'}
