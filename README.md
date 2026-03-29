# imgui-native

Native Node.js bindings for Dear ImGui using N-API.

This package ships prebuilt `.node` binaries for major desktop targets and TypeScript declarations generated from Dear ImGui metadata.

## Install

```bash
bun install imgui-native
```

## Usage

```ts
import imgui from "imgui-native";

const ctx = imgui.createContext();
const io = imgui.getIO();

// ... your frame loop ...

imgui.destroyContext(ctx);
```

## Prebuilt Binaries

At runtime, the loader searches for:

1. `build/Release/imgui.node` (local development build)
2. `prebuild/<platform>-<arch>/imgui.node` (published package binary)

Current release workflow produces prebuilds for:

- `linux-x64`
- `win32-x64`
- `darwin-x64`
- `darwin-arm64`

## Local Development

Generate bindings and build:

```bash
uv sync
bun install
git submodule update --init --recursive
bun run configure
bun run build
```

## License

MIT, matching Dear ImGui.
See [LICENSE](LICENSE).
