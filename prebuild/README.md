# prebuild

This folder is populated by CI release workflows.

Expected layout in published tarballs:

- `prebuild/linux-x64/imgui.node`
- `prebuild/win32-x64/imgui.node`
- `prebuild/darwin-x64/imgui.node`
- `prebuild/darwin-arm64/imgui.node`

Local development uses `build/Release/imgui.node` first, then falls back to these prebuild binaries.
