# Stage 2: Struct & Function Bindings — Implementation Plan

## 0. Fundamental Contract

The call chain is strictly:

```
JS → NAPI C++ → dcimgui.h (C ABI) → dcimgui.cpp (C wrapper) → imgui (C++)
```

Generated NAPI code includes `dcimgui.h` for all function calls and type definitions.
Dear bindings has already solved all C++ compatibility: opaque structs, by-value conversions,
method dispatch via reinterpret_cast. We call plain C functions.

**Narrow exception:** `imgui.h` is included in a single construction helper for two purposes:
1. Placement-new construction of 3 structs whose C++ constructors set non-zero defaults
   (`ImFontConfig`, `ImGuiWindowClass`, `ImGuiSelectionBasicStorage`) — the C API exposes no
   constructor wrappers for these.
2. `IM_DELETE` for freeing the owned `ImDrawList*` returned by `ImDrawList_CloneOutput()` —
   it was allocated via `IM_NEW` (imgui's custom allocator), not C++ `new`.

All function calls still go exclusively through the C ABI via `dcimgui.h`. The `imgui.h`
include is only for object lifecycle (construction/destruction) where the C API has gaps.

---

## 1. Struct Classification

### 1a. By-Value Structs (4 total)

`ImVec2`, `ImVec4`, `ImColor`, `ImTextureRef` — marked `by_value: true` in JSON.

These are passed and returned **by value** in the C ABI:
```c
CIMGUI_API ImVec2 ImGui_GetWindowPos(void);
CIMGUI_API void   ImDrawList_AddLine(ImDrawList* self, ImVec2 p1, ImVec2 p2, ImU32 col);
```

Special treatment: the C struct is **embedded** directly inside the ObjectWrap (no heap pointer,
no owned/borrowed concept). Value is copied on every get/set.

### 1b. Opaque / Forward-Declared Structs (4 total)

`ImGuiContext`, `ImDrawListSharedData`, `ImFontAtlasBuilder`, `ImFontLoader` — `forward_declaration: true`.

Confirmed in `dcimgui.h`: these are **typedef-only forward declarations with no struct body**:
```c
typedef struct ImDrawListSharedData_t ImDrawListSharedData;  // line 223
typedef struct ImFontAtlasBuilder_t   ImFontAtlasBuilder;    // line 228
typedef struct ImFontLoader_t         ImFontLoader;          // line 234
typedef struct ImGuiContext_t         ImGuiContext;           // line 240
```
No field definitions appear anywhere in the header. There is nothing to expose.

Appearances in the C API:
- `ImGuiContext`: returned by `ImGui_CreateContext()` / `ImGui_GetCurrentContext()`, consumed by `ImGui_DestroyContext()` / `ImGui_SetCurrentContext()` — expose as an opaque owned handle.
- `ImDrawListSharedData`: returned by `ImGui_GetDrawListSharedData()`, consumed by `ImDrawList__SetDrawListSharedData()` — expose as an opaque borrowed handle.
- `ImFontAtlasBuilder` / `ImFontLoader`: appear in zero function signatures — do not expose at all.

`ImGuiContext` is the only struct in the entire C API with explicit alloc/free functions.

### 1c. ImVector_* Template Instantiations (26 total)

`ImVector_ImDrawCmd`, `ImVector_ImVec2`, etc.

Confirmed structure from `dcimgui.h`: every ImVector instantiation is a plain C struct with
exactly three fields:
```c
struct ImVector_ImDrawCmd_t { int Size; int Capacity; ImDrawCmd* Data; };
```

The `ImVector_*` structs themselves are **not wrapped** as standalone JS classes — no C API
methods exist for them (only generic `ImVector_Construct`/`ImVector_Destruct` which take `void*`).

However, **ImVector fields on parent structs ARE exposed** as read-only JS array getters.
The generator produces a getter for each ImVector field that reads `Size` and `Data`, then
builds a JS array of appropriately wrapped elements. See §5 for the accessor pattern.

### 1d. Regular Structs (~41 remaining)

Full field definitions available in `dcimgui.h`. These are the main generation targets.

**Sub-classification by constructability:**

A struct is user-constructable if no C API function is the authoritative source for its
allocation AND the user needs to create one to use some imgui feature. Non-constructable
structs are only ever obtained as borrowed pointers from API calls.

**Category A — Zero-init safe (C++ constructor is trivial/memset-only):**

| Struct | Evidence |
|---|---|
| `ImGuiListClipper` | Constructor is pure `memset(this, 0, sizeof(*this))`. `Begin()` sets up state. |
| `ImGuiTextFilter` | Constructor sets `InputBuf[0]=0`, `CountGrep=0` — equivalent to zero. |
| `ImGuiStorage` | No constructor declared. Sole `ImVector` field is zero-safe. |
| `ImGuiTextBuffer` | Constructor is `{}` (empty body). Sole `ImVector` field is zero-safe. |
| `ImFontGlyphRangesBuilder` | Delegates to `Clear()` which zeros the `UsedChars` vector. |

These use `new StructType{}` (C++ value-init → zeroes all fields).

**Category B — Require C++ constructor (non-zero defaults, no C API constructor):**

| Struct | Non-Zero Defaults | Impact of Zero-Init |
|---|---|---|
| `ImFontConfig` | `FontDataOwnedByAtlas=true`, `ExtraSizeScale=1.0f`, `GlyphMaxAdvanceX=FLT_MAX`, `RasterizerMultiply=1.0f`, `RasterizerDensity=1.0f` | Invisible fonts (zero scale/multiply), broken glyph layout |
| `ImGuiWindowClass` | `ParentViewportId=(ImGuiID)-1`, `DockingAllowUnclassed=true` | Wrong docking/viewport parenting behavior |
| `ImGuiSelectionBasicStorage` | `AdapterIndexToStorageId=<identity lambda>`, `_SelectionOrder=1` | NULL function pointer crash on `ApplyRequests()` |

These use placement-new with the real C++ constructor: `new(ptr) StructType()`. This calls
imgui's constructor which sets the correct defaults. Gated by a generator override table:

```python
NEEDS_CPP_CONSTRUCTOR = {"ImFontConfig", "ImGuiWindowClass", "ImGuiSelectionBasicStorage"}
```

The generated C++ code includes `imgui.h` (see §0) to access these constructors.

**Category C — Special lifecycle:**

`ImGuiContext` — must use `ImGui_CreateContext()` / `ImGui_DestroyContext()`.

**Non-constructable (borrow-only):**

| Struct | Source |
|---|---|
| `ImGuiIO` | `ImGui_GetIO()` — owned by context |
| `ImGuiStyle` | `ImGui_GetStyle()` — owned by context |
| `ImDrawList` | `ImGui_GetWindowDrawList()` etc. — borrowed; exception: `CloneOutput()` returns owned |
| `ImFont` | `ImFontAtlas_AddFont*()` — atlas owns lifetime |
| `ImFontAtlas` | `io->Fonts` field — context owns it |
| `ImGuiViewport` | `ImGui_GetMainViewport()` etc. — imgui-owned |
| `ImDrawData` | `ImGui_GetDrawData()` — populated by `Render()` |
| `ImGuiPlatformIO` | `ImGui_GetPlatformIO()` — context-owned |
| `ImGuiMultiSelectIO` | `ImGui_BeginMultiSelect()` / `ImGui_EndMultiSelect()` |
| Remaining data structs | `ImDrawCmd`, `ImDrawVert`, `ImFontGlyph`, `ImGuiKeyData`, etc. — internal records accessed as fields or array elements of parent structs |

Non-constructable structs are only ever created via borrowed factory wrapping.

---

## 2. Memory Management

### The Core Model

Every non-by-value wrapper carries two fields:

```cpp
StructType* ptr;
bool owned;
```

- `owned = true`: we allocated the memory. GC cleans up (method depends on struct type).
- `owned = false`: imgui owns the memory. GC is a no-op.

### Construction Patterns

**Category A — Zero-init safe (JS `new`):**

```cpp
ptr = new StructType{};  // C++ value-init: zeros all POD fields
owned = true;
// destructor: delete ptr;
```

**Category B — C++ constructor required (JS `new`):**

```cpp
ptr = static_cast<StructType*>(ImGui::MemAlloc(sizeof(StructType)));
new(ptr) StructType();  // placement-new: calls real C++ constructor
owned = true;
// destructor: ptr->~StructType(); ImGui::MemFree(ptr);
```

Alternatively, since the struct types are POD-like from the C perspective and `IM_NEW`/`IM_DELETE`
are available via the `imgui.h` include:

```cpp
ptr = IM_NEW(StructType);  // IM_NEW = placement-new over ImGui::MemAlloc
owned = true;
// destructor: IM_DELETE(ptr);
```

**Category C — `ImGuiContext` (special lifecycle):**

```cpp
// Construct:
ptr = ImGui_CreateContext(nullptr);
owned = true;

// Destruct:
if (owned) ImGui_DestroyContext(ptr);
// Do NOT use 'delete' or 'IM_DELETE' for ImGuiContext — ever.
```

**Borrowed (returned by imgui C API):**

```cpp
ptr = <pointer returned from C function>;
owned = false;
// destructor: nothing
```

### Special Case: ImDrawList_CloneOutput

`ImDrawList_CloneOutput(self)` is the **only non-Context function that returns an owned pointer**
(excluding `ImGui_MemAlloc` which returns raw `void*`).

It allocates via `IM_NEW` (imgui's custom allocator, NOT C++ `new`). Therefore:
- **`delete ptr` is WRONG** — causes heap corruption (wrong allocator).
- **Correct cleanup: `IM_DELETE(ptr)`** — calls destructor, then `ImGui::MemFree()`.

The generated binding sets `owned = true` on the returned wrapper. The destructor uses
`IM_DELETE(reinterpret_cast<::ImDrawList*>(ptr))`.

Detection in generator: override table entry:

```python
OWNED_RETURNS = {"ImDrawList_CloneOutput": "IM_DELETE"}
```

### Borrowed Factory Pattern

Each wrapper class exposes a static C++ factory used internally by function bindings:

```cpp
class DrawListWrap : public Napi::ObjectWrap<DrawListWrap> {
public:
    static Napi::FunctionReference constructor;
    ImDrawList* ptr;
    bool owned;

    // Internal factory for borrowed wrapping (not callable from JS)
    static Napi::Value Wrap(Napi::Env env, ImDrawList* raw) {
        auto external = Napi::External<ImDrawList>::New(env, raw);
        return constructor.New({external});
    }

    DrawListWrap(const Napi::CallbackInfo& info)
        : Napi::ObjectWrap<DrawListWrap>(info) {
        if (info[0].IsExternal()) {
            // borrowed path — called by Wrap()
            ptr = info[0].As<Napi::External<ImDrawList>>().Data();
            owned = false;
        } else {
            // DrawList is borrow-only: JS `new DrawList()` is not valid
            Napi::TypeError::New(info.Env(),
                "DrawList cannot be constructed directly; use getWindowDrawList() etc.")
                .ThrowAsJavaScriptException();
        }
    }

    ~DrawListWrap() {
        if (owned) IM_DELETE(reinterpret_cast<::ImDrawList*>(ptr));
    }
};
// Note: for Category A structs the else branch does:
//   ptr = new StructType{};
//   owned = true;
// For Category B structs the else branch does:
//   ptr = IM_NEW(StructType);
//   owned = true;
```

The `Napi::External` trick threads the raw pointer through the JS constructor without
exposing it to JS (External is not a normal JS value).

### Lifetime Hazard (borrowed pointers)

Imgui invalidates many pointers between frames (e.g. `ImDrawList*` from
`ImGui_GetWindowDrawList()`). Borrowed wrappers are **single-frame valid**.

**Do not attempt runtime detection.** Document this constraint. The owned/borrowed flag does
not mean "safe to hold across frames" — it means "who cleans up". This is the user's
responsibility to understand.

---

## 3. Type System & Converters

All conversions live in a shared `types.h` / `types.cpp` (hand-written, not generated).
The generator emits calls to these converters. This is the critical infrastructure layer.

### Typedef Chain Resolution

The generator builds a typedef lookup table from the JSON `typedefs` array. For any
`kind: "User"` type, it walks the chain until hitting a `kind: "Builtin"`. Maximum chain
depth in the imgui API is 2 hops. Examples:

| Type | Chain | Resolved |
|---|---|---|
| `ImTextureID` | → `ImU64` → `unsigned long long` | `Napi::BigInt` |
| `ImGuiSortDirection` | → `ImU8` → `unsigned char` | `Napi::Number` |
| `ImGuiSelectionUserData` | → `ImS64` → `signed long long` | `Napi::BigInt` |
| `ImWchar` | → `ImWchar32` → `unsigned int` | `Napi::Number` |
| `ImGuiWindowFlags` | → `int` | `Napi::Number` (enum) |

**External types** not in the JSON typedef table (hardcoded in generator):
- `size_t` → `Napi::Number` / `Uint32Value()` / TS `number`

This covers 100% of types referenced in the JSON.

### Builtin Type Mapping

| C type | NAPI | JS/TS |
|---|---|---|
| `bool` | `Napi::Boolean` | `boolean` |
| `int`, `unsigned int`, `short`, `unsigned short` | `Napi::Number` | `number` |
| `float`, `double` | `Napi::Number` | `number` |
| `ImU32`, `ImGuiID`, `ImS32`, `ImU16`, `ImU8` | `Napi::Number` | `number` |
| `ImU64` | `Napi::BigInt` | `bigint` |
| `ImTextureID` (= `ImU64`) | `Napi::BigInt` | `bigint` |
| `ImWchar` | `Napi::Number` | `number` |
| `const char*` | `Napi::String` | `string` |
| `void` | `undefined` | `void` |
| `size_t` | `Napi::Number` | `number` |

### const char* Lifetime — Critical Gotcha

`Napi::String::Utf8Value()` returns a `std::string` (temporary). Do NOT do this:

```cpp
// WRONG: cstr is dangling, std::string temporary destroyed
const char* cstr = info[0].As<Napi::String>().Utf8Value().c_str();
```

Always do this:

```cpp
// CORRECT: string outlives the C call
std::string str = info[0].As<Napi::String>().Utf8Value();
SomeCFunction(str.c_str());
```

Generator must emit the two-line pattern, never the one-line version.

### Struct Type Mapping

| C type pattern | NAPI | Notes |
|---|---|---|
| `ImVec2` (by value) | `Vec2Wrap` | Embedded value, no pointer |
| `ImVec4` (by value) | `Vec4Wrap` | Embedded value, no pointer |
| `ImColor` (by value) | `ColorWrap` | Embedded value |
| `ImTextureRef` (by value) | `TextureRefWrap` | Embedded value |
| `SomeStruct*` (non-const) | `SomeStructWrap` (borrowed) | Wrap factory |
| `const SomeStruct*` | `SomeStructWrap` (borrowed) | Read-only conceptually |
| `ImGuiContext*` | `ImGuiContextWrap` | Special lifecycle |

### Pointer Type Rules

| Pattern | Treatment |
|---|---|
| `const char*` | String (input or output) |
| `bool*`, `int*`, `float*` (non-const, non-self) | Mutable ref parameter (see §6) |
| `void*` | Skip / `Napi::External<void>` |
| `StructType*` where struct is `ImVector_*` | Skip (ImVector structs are not wrapped) |
| Forward-declared struct pointer | Opaque handle |
| Function pointer (`callback`) | FunctionRef trampoline (see §6a) |

### Fixed-Size Array Types

| C type | NAPI | TS |
|---|---|---|
| `float[2]`, `float[3]`, `float[4]` | `Napi::Float32Array` | `Float32Array` |
| `int[2]`, `int[3]`, `int[4]` | `Napi::Int32Array` | `Int32Array` |
| `ImVec4[N]` (array of by-value structs) | `Napi::Float32Array` (flattened, length N*4) | `Float32Array` |
| `ImU8[N]` large | Skip (internal) | — |
| `const char*[]` | `Napi::Array` of strings | `string[]` |

### Array Bounds Resolution

Fixed-size array fields in structs may use symbolic bounds: `"ImGuiCol_COUNT"`,
`"ImGuiKey_NamedKey_COUNT"`, `"5"`, etc.

Resolution: numeric literals are used directly. Symbolic bounds are resolved by looking up
the enum entry with `is_count: true` in the JSON `enums` array and using its `value` field.
These `is_count` entries are already parsed (they are omitted from the generated enum exports
but their numeric values are available to the generator).

### Enum Types

Enums are `int` in C. Accept and return as `Napi::Number`. In TypeScript, type as the
generated enum type (e.g., `enums.WindowFlags`).

### ImVec2 Input Flexibility

Anywhere an `ImVec2` is an input parameter, accept all three forms:

```typescript
type Vec2Like = Vec2 | [number, number] | {x: number, y: number}
```

In C++, the converter:

```cpp
ImVec2 ExtractImVec2(Napi::Value v) {
    if (v.IsObject()) {
        // could be Vec2Wrap instance or plain {x,y}
        Napi::Object obj = v.As<Napi::Object>();
        if (obj.InstanceOf(Vec2Wrap::constructor.Value())) {
            return Vec2Wrap::Unwrap(obj)->value;
        }
        return ImVec2{
            obj.Get("x").As<Napi::Number>().FloatValue(),
            obj.Get("y").As<Napi::Number>().FloatValue()
        };
    }
    if (v.IsArray()) {
        Napi::Array arr = v.As<Napi::Array>();
        return ImVec2{
            arr.Get(0u).As<Napi::Number>().FloatValue(),
            arr.Get(1u).As<Napi::Number>().FloatValue()
        };
    }
    // error
}
```

---

## 4. By-Value Struct Wrapper Pattern

`ImVec2`, `ImVec4`, `ImColor`, `ImTextureRef` — value embedded, no ptr:

```cpp
class Vec2Wrap : public Napi::ObjectWrap<Vec2Wrap> {
public:
    ImVec2 value;  // embedded — no allocation, no ownership

    static Napi::Value New(Napi::Env env, ImVec2 v) {
        // create from C value
        return constructor.New({
            Napi::Number::New(env, v.x),
            Napi::Number::New(env, v.y)
        });
    }

    Vec2Wrap(const Napi::CallbackInfo& info) : Napi::ObjectWrap(info) {
        value.x = info[0].As<Napi::Number>().FloatValue();
        value.y = info[1].As<Napi::Number>().FloatValue();
    }
    // no destructor needed
    // x/y exposed as instance accessors
};
```

`ImColor` wraps `ImVec4`. Its single field is itself a by-value struct — handle recursively.

`ImColor_HSV` is a **static method** (`is_static: true` in JSON). It takes no instance pointer
and returns `ImColor` by value. Expose as a static factory on the Color class:

```typescript
export class Color {
    static hsv(h: number, s: number, v: number, a?: number): Color;
    value: Vec4;
}
```

Detection: check `is_static: true` on the function entry. Static methods have no
`is_instance_pointer` on their first argument.

---

## 5. Field Accessor Generation

For each non-skipped field of a regular struct, generate a getter + setter pair.

### Field Skip Conditions

Skip a field if:
- Its type is a forward-declared struct (opaque)
- Its type is `void*`
- It is marked `is_internal: true` in JSON
- Its name starts with `_` (internal imgui convention)

**Note:** ImVector fields and function pointer fields are NOT skipped — they get specialized
accessor generation (see below).

### Field Type → Accessor Pattern

**Primitive field** (`float`, `bool`, `int`, etc.):
```cpp
// getter
Napi::Value GetDeltaTime(const Napi::CallbackInfo& info) {
    return Napi::Number::New(info.Env(), ptr->DeltaTime);
}
// setter
void SetDeltaTime(const Napi::CallbackInfo& info, const Napi::Value& val) {
    ptr->DeltaTime = val.As<Napi::Number>().FloatValue();
}
```

**By-value struct field** (`ImVec2`, `ImVec4`):
```cpp
// getter — returns a COPY (not a reference into the struct)
Napi::Value GetDisplaySize(const Napi::CallbackInfo& info) {
    return Vec2Wrap::New(info.Env(), ptr->DisplaySize);
}
// setter — copies from JS value into struct field
void SetDisplaySize(const Napi::CallbackInfo& info, const Napi::Value& val) {
    ptr->DisplaySize = ExtractImVec2(val);
}
```

This copy semantics is intentional. Returning a reference into a struct's field memory
creates a dangling pointer hazard when the parent wrapper is GC'd. Always copy.

**Pointer field** (`ImFont* FontDefault`, `ImFontAtlas* Fonts`):
```cpp
// getter — borrowed wrap of the pointed-to struct
Napi::Value GetFontDefault(const Napi::CallbackInfo& info) {
    if (!ptr->FontDefault) return info.Env().Null();
    return FontWrap::Wrap(info.Env(), ptr->FontDefault);
}
// setter — most pointer fields are read-only from JS
// only expose setter where it makes semantic sense
```

**String field** (`const char* IniFilename`):
```cpp
Napi::Value GetIniFilename(const Napi::CallbackInfo& info) {
    if (!ptr->IniFilename) return info.Env().Null();
    return Napi::String::New(info.Env(), ptr->IniFilename);
}
```

**Fixed numeric array field** (`float[4]`, `int[2]`):
```cpp
// Return a Float32Array copy of the struct's memory
Napi::Value GetSomeArray(const Napi::CallbackInfo& info) {
    auto buf = Napi::ArrayBuffer::New(info.Env(), 4 * sizeof(float));
    memcpy(buf.Data(), ptr->SomeArray, 4 * sizeof(float));
    return Napi::Float32Array::New(info.Env(), 4, buf, 0);
}
```

Returning a copy (not a view) avoids the dangling memory hazard.

**Fixed array-of-structs field** (`ImVec4[ImGuiCol_COUNT]` — e.g., `ImGuiStyle.Colors`):

Exposed as a flat `Float32Array` with length `COUNT * fields_per_element`:
```cpp
// ImGuiStyle.Colors: ImVec4[ImGuiCol_COUNT] → Float32Array of length COUNT*4
Napi::Value GetColors(const Napi::CallbackInfo& info) {
    constexpr int count = ImGuiCol_COUNT;  // resolved from enum at generation time
    auto buf = Napi::ArrayBuffer::New(info.Env(), count * 4 * sizeof(float));
    memcpy(buf.Data(), ptr->Colors, count * 4 * sizeof(float));
    return Napi::Float32Array::New(info.Env(), count * 4, buf, 0);
}
void SetColors(const Napi::CallbackInfo& info, const Napi::Value& val) {
    auto arr = val.As<Napi::Float32Array>();
    memcpy(ptr->Colors, arr.Data(), ImGuiCol_COUNT * 4 * sizeof(float));
}
```

User accesses individual colors by index: `colors[idx * 4 + 0]` through `colors[idx * 4 + 3]`.

**ImVector field** (`ImVector_ImDrawCmd CmdBuffer`, `ImVector_ImFontPtr Fonts`, etc.):

Read-only getter that builds a JS array from the vector's `Size` and `Data`:

```cpp
// ImDrawList.CmdBuffer: ImVector_ImDrawCmd → JS array of DrawCmd wrappers
Napi::Value GetCmdBuffer(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    int size = ptr->CmdBuffer.Size;
    Napi::Array arr = Napi::Array::New(env, size);
    for (int i = 0; i < size; i++) {
        arr.Set(i, DrawCmdWrap::Wrap(env, &ptr->CmdBuffer.Data[i]));
    }
    return arr;
}

// ImFontAtlas.Fonts: ImVector_ImFontPtr → JS array of Font wrappers
Napi::Value GetFonts(const Napi::CallbackInfo& info) {
    Napi::Env env = info.Env();
    int size = ptr->Fonts.Size;
    Napi::Array arr = Napi::Array::New(env, size);
    for (int i = 0; i < size; i++) {
        arr.Set(i, FontWrap::Wrap(env, ptr->Fonts.Data[i]));
    }
    return arr;
}
```

For pointer-to-pointer vectors (`ImVector_ImDrawListPtr` → `ImDrawList** Data`), each element
is `Data[i]` (an `ImDrawList*`), wrapped as borrowed.

For value vectors (`ImVector_ImDrawCmd` → `ImDrawCmd* Data`), each element is `&Data[i]`,
wrapped as borrowed (pointing into the vector's memory).

**Special case — VtxBuffer and IdxBuffer**: These are performance-critical for GPU upload.
Instead of wrapping each element, return TypedArray views:

```cpp
// ImDrawList.VtxBuffer → ArrayBuffer (raw bytes, 20 bytes per ImDrawVert)
Napi::Value GetVtxBuffer(const Napi::CallbackInfo& info) {
    return Napi::ArrayBuffer::New(info.Env(),
        ptr->VtxBuffer.Data, ptr->VtxBuffer.Size * sizeof(ImDrawVert));
}

// ImDrawList.IdxBuffer → Uint16Array (ImDrawIdx = unsigned short)
Napi::Value GetIdxBuffer(const Napi::CallbackInfo& info) {
    auto buf = Napi::ArrayBuffer::New(info.Env(),
        ptr->IdxBuffer.Data, ptr->IdxBuffer.Size * sizeof(ImDrawIdx));
    return Napi::Uint16Array::New(info.Env(), ptr->IdxBuffer.Size, buf, 0);
}
```

These are zero-copy views into native memory — valid only for the current frame.

**Function pointer field** — see §6a for FunctionRef-based accessor generation.

**Field naming**: camelCase the C field name. `DisplaySize` → `displaySize`, `ConfigFlags` → `configFlags`.

---

## 6. Mutable Parameter System (Refs)

Imgui is an immediate-mode API. **State lives outside imgui and is passed in each frame.**
A checkbox's boolean, a slider's float, a window's open flag — these are persistent variables
owned by the application, read and potentially modified by imgui every frame.

The naive approach (returning modified values from a function call) fails because the
updated value needs to be fed back into the next frame's call. You'd write:

```js
// BROKEN — value is lost between frames, can never be false
let result = imgui.begin("win", true);  // always passes true
```

The correct model is a **mutable ref object**: the user creates it once, stores it, passes
it every frame. Imgui reads and writes through it in-place. The ref persists.

### Five Mutable Parameter Patterns (from full API scan)

**Pattern 1 — `bool*` scalar** (13 functions): `p_open`, `p_visible`, `p_selected`, `v`
- `ImGui_Begin`, `ImGui_Checkbox`, `ImGui_SelectableBoolPtr`, `ImGui_MenuItemBoolPtr`,
  `ImGui_BeginPopupModal`, `ImGui_BeginTabItem`, `ImGui_ShowDemoWindow`, etc.
- Nullable (can pass null = feature disabled): detected by `argument.default_value == "NULL"`
- Non-nullable: `Checkbox` `v`, `SelectableBoolPtr` `p_selected` (no `default_value: "NULL"`)

**Pattern 2 — `float*` / `int*` / `double*` scalar** (18+ functions): `v`, `v_current_min/max`
- `ImGui_DragFloat[Ex]`, `ImGui_SliderFloat[Ex]`, `ImGui_InputFloat[Ex]`
- `ImGui_DragInt[Ex]`, `ImGui_SliderInt[Ex]`, `ImGui_InputInt[Ex]`, `ImGui_InputDouble[Ex]`
- `ImGui_DragFloatRange2[Ex]` / `ImGui_DragIntRange2[Ex]` — two separate scalar pointers

**Pattern 3 — `float[N]` / `int[N]` fixed array** (30+ functions): `v`, `col`
- `ImGui_DragFloat2/3/4`, `ImGui_SliderFloat2/3/4`, `ImGui_InputFloat2/3/4`
- `ImGui_DragInt2/3/4`, `ImGui_SliderInt2/3/4`, `ImGui_InputInt2/3/4`
- `ImGui_ColorEdit3` (`float[3]`), `ImGui_ColorEdit4` (`float[4]`)

**Pattern 4 — `char* buf, size_t buf_size` text buffer** (6 functions)
- `ImGui_InputText[Ex]`, `ImGui_InputTextMultiline[Ex]`, `ImGui_InputTextWithHint[Ex]`
- Buffer is owned by caller; imgui writes updated text in-place; `buf_size` is the capacity

**Pattern 5 — pure write-only outputs** (4 functions): `out_*` named params
- `ImGui_ColorConvertRGBtoHSV(r, g, b, out_h*, out_s*, out_v*)` — all outputs, no persistent state
- `ImGui_ColorConvertHSVtoRGB(h, s, v, out_r*, out_g*, out_b*)` — same
- `ImFontAtlas_GetTexDataAsAlpha8(self, out_pixels**, out_width*, out_height*, out_bytes*)`
- These are **not in-out** — they have no prior state to preserve, imgui only writes

Pattern 5 is handled differently: allocate the output vars on the C stack, call the function,
return results as a plain JS object. No ref needed.

### Nullable Detection Rule

The authoritative rule for parameter nullability:

1. If `argument.default_value == "NULL"` → **nullable** (accept `null`/`undefined` from JS, pass `nullptr` to C)
2. Otherwise → **non-nullable** (must pass valid ref/value)

The `is_nullable` field on the type descriptor is a secondary confirmation (289 instances
in the JSON, all `false` = non-nullable). Its absence means unspecified — fall back to
`default_value` as the authority.

---

### Ref Class Design

Four scalar ref types + one text ref type, all hand-written (not generated), exposed
on the module alongside structs:

```
lib/
    refs.h      # Ref class declarations
    refs.cpp    # Ref class implementations
```

#### BoolRef

```cpp
class BoolRef : public Napi::ObjectWrap<BoolRef> {
public:
    bool val = false;
    bool* Ptr() { return &val; }

    BoolRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap(info) {
        if (!info[0].IsUndefined()) val = info[0].As<Napi::Boolean>().Value();
    }
    Napi::Value GetValue(const Napi::CallbackInfo& info) {
        return Napi::Boolean::New(info.Env(), val);
    }
    void SetValue(const Napi::CallbackInfo& info, const Napi::Value& v) {
        val = v.As<Napi::Boolean>().Value();
    }
};
```

#### FloatRef / IntRef / DoubleRef

Same pattern, different stored type and NAPI number conversion:

```cpp
class FloatRef : public Napi::ObjectWrap<FloatRef> {
public:
    float val = 0.0f;
    float* Ptr() { return &val; }
    // constructor: val = info[0].As<Napi::Number>().FloatValue()
    // getter/setter via Napi::Number
};
// IntRef: int val; Int32Value() / Int32Value()
// DoubleRef: double val; DoubleValue()
```

#### StringRef

The text buffer is more complex: it must own a fixed-size `char[]` allocation whose address
stays stable (imgui holds a pointer into it for the duration of the frame).

```cpp
class StringRef : public Napi::ObjectWrap<StringRef> {
    std::vector<char> buf;
public:
    char*  Data() { return buf.data(); }
    size_t Size() { return buf.size(); }  // total capacity incl. null terminator

    StringRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap(info) {
        // info[0]: initial string value
        // info[1]: buffer capacity (bytes, excluding null terminator)
        size_t cap = info[1].As<Napi::Number>().Uint32Value();
        buf.resize(cap + 1, '\0');
        if (!info[0].IsUndefined() && info[0].IsString()) {
            std::string init = info[0].As<Napi::String>().Utf8Value();
            strncpy(buf.data(), init.c_str(), cap);
        }
    }
    Napi::Value GetValue(const Napi::CallbackInfo& info) {
        return Napi::String::New(info.Env(), buf.data());  // reads until null terminator
    }
    void SetValue(const Napi::CallbackInfo& info, const Napi::Value& v) {
        std::string s = v.As<Napi::String>().Utf8Value();
        strncpy(buf.data(), s.c_str(), buf.size() - 1);
        buf[buf.size() - 1] = '\0';
    }
};
```

**StringRef stability**: `std::vector<char>` does NOT reallocate unless you call `resize` or
`push_back`. Once constructed, `buf.data()` is stable for the object's lifetime. Never resize
a StringRef's buffer after construction.

---

### TypedArray Pass-Through for float[N] / int[N]

The `float[2]`, `float[3]`, `float[4]`, `int[2]` etc. parameters (Pattern 3) do NOT need a
special ref type. A `Float32Array` or `Int32Array` in JS has a stable underlying `ArrayBuffer`
whose data pointer is directly usable as a C `float*` / `int*`:

```cpp
// Generated binding for ImGui_DragFloat4(label, float[4] v, ...)
Napi::Float32Array arr = info[1].As<Napi::Float32Array>();
float* v = reinterpret_cast<float*>(arr.Data());
// verify arr.ElementLength() >= 4 (optional safety check)
bool changed = ImGui_DragFloat4(label_cstr, v, ...);
// arr.Data() contents are updated in-place — JS Float32Array reflects new values
```

The user's code:
```js
// Created once, reused every frame
const color = new Float32Array([1.0, 0.5, 0.0, 1.0]);

// Every frame:
if (imgui.colorEdit4("color", color)) {
    console.log("changed:", color[0], color[1], color[2], color[3]);
}
```

This is zero-copy: imgui writes directly into the `ArrayBuffer` backing the `Float32Array`.
No conversion, no allocation per frame.

The generated code must validate that the typed array has sufficient length and correct element
type before extracting the pointer. Mismatch should throw `TypeError`.

---

### void* p_data — Generic Scalar (DragScalar family)

`DragScalar`, `SliderScalar`, `InputScalar` and their N/Ex variants take `void* p_data` with
an `ImGuiDataType data_type` argument. The `void*` points to a value of the type specified by
`data_type`.

These functions are **already covered by the typed variants** (`DragFloat`, `DragInt`, etc.)
for the common S32 and Float cases. The generic variants add S8, U8, S16, U16, U32, S64,
U64, Double support.

Design: accept a typed ref object, **infer `data_type` from the ref's C++ type**:

| Ref type | ImGuiDataType |
|---|---|
| `FloatRef` | `ImGuiDataType_Float` |
| `DoubleRef` | `ImGuiDataType_Double` |
| `IntRef` | `ImGuiDataType_S32` |
| `Float32Array` (1 element) | `ImGuiDataType_Float` |
| `Int32Array` (1 element) | `ImGuiDataType_S32` |

The user does not pass `data_type` explicitly from JS — it is derived from the ref type.
This collapses the entire DragScalar/SliderScalar/InputScalar family into the same pattern
as their typed counterparts:

```js
const val = new FloatRef(0.5);
imgui.dragScalar("val", val, 0.01, 0.0, 1.0);  // data_type = Float inferred
```

S64/U64 refs (64-bit) require `BigInt` handling. Defer those to a later stage; skip
`ImGuiDataType_S64` / `ImGuiDataType_U64` in the initial auto-gen.

For the N-component variants (`DragScalarN` etc.), accept a `Float32Array` or `Int32Array`
with the appropriate element count. The `data_type` is inferred from the array type.

---

### Generated Code: Ref Extraction Patterns

The `types.py` converter for each ref-accepting parameter type:

**`bool*` (nullable)** — detected by `argument.default_value == "NULL"`:
```cpp
bool* p_open = nullptr;
if (!info[N].IsNull() && !info[N].IsUndefined()) {
    p_open = BoolRef::Unwrap(info[N].As<Napi::Object>())->Ptr();
}
```

**`bool*` (non-nullable)** — no `default_value: "NULL"`:
```cpp
bool* v = BoolRef::Unwrap(info[N].As<Napi::Object>())->Ptr();
```

**`float*` (non-nullable)**:
```cpp
float* v = FloatRef::Unwrap(info[N].As<Napi::Object>())->Ptr();
```

**`float[N]` (fixed array)**:
```cpp
Napi::Float32Array arr_N = info[N].As<Napi::Float32Array>();
float* v = reinterpret_cast<float*>(arr_N.Data());
```

**`char* buf, size_t buf_size`** — these two C parameters come from ONE JS ref argument,
consuming a single `info[N]` slot. The generator must fuse the `(buf, buf_size)` pair:
```cpp
StringRef* sref_N = StringRef::Unwrap(info[N].As<Napi::Object>());
// then in the call:
ImGui_InputText(label, sref_N->Data(), sref_N->Size(), flags);
// (buf_size parameter is NOT a separate JS argument)
```

The `(char* buf, size_t buf_size)` fusion is a named pair pattern the generator detects:
consecutive arguments where one is `char*` (non-const) and the next is `size_t` named
`buf_size` — merge them into a single `StringRef` JS argument.

---

### Pure Output Parameters (Pattern 5)

For functions where all pointer args are write-only outputs (no prior state), allocate
on the C stack and return results as a plain object:

```cpp
// Generated for ImGui_ColorConvertRGBtoHSV(r, g, b, out_h, out_s, out_v)
Napi::Value ColorConvertRGBtoHSV(const Napi::CallbackInfo& info) {
    float r = info[0].As<Napi::Number>().FloatValue();
    float g = info[1].As<Napi::Number>().FloatValue();
    float b = info[2].As<Napi::Number>().FloatValue();
    float out_h, out_s, out_v;
    ImGui_ColorConvertRGBtoHSV(r, g, b, &out_h, &out_s, &out_v);
    Napi::Object ret = Napi::Object::New(info.Env());
    ret.Set("h", Napi::Number::New(info.Env(), out_h));
    ret.Set("s", Napi::Number::New(info.Env(), out_s));
    ret.Set("v", Napi::Number::New(info.Env(), out_v));
    return ret;
}
```

Detection heuristic for "pure output": all of the following hold:
- Parameter name starts with `out_`
- Parameter type is `T*` (non-const) where T is a primitive
- There is no `default_value` on the parameter

Additionally, `is_reference: true` on the type descriptor confirms the C++ original was a
reference (`float&`), not a pointer — these are always non-nullable pure outputs. Only 7
arguments in the entire JSON have this flag.

`ImFontAtlas_GetTexDataAsAlpha8` with its `unsigned char**` output is a manual binding —
double pointer output is outside the scope of the auto-generator.

---

### JS API Shape (Refs)

```js
// Ref types exposed directly on the module
const open     = new imgui.BoolRef(true);
const volume   = new imgui.FloatRef(0.8);
const count    = new imgui.IntRef(0);
const name     = new imgui.StringRef("Player", 64);  // 64-byte buffer
const color    = new Float32Array([1, 0.5, 0, 1]);   // stdlib, no import needed

// Every frame:
if (imgui.begin("Settings", open)) {  // returns bool; open.value mutated in-place
    imgui.sliderFloat("Volume", volume, 0.0, 1.0);
    imgui.inputText("Name", name);
    imgui.colorEdit4("Color", color);
    imgui.end();
}
if (!open.value) stopRenderingSettings();
```

### TypeScript Declarations for Refs

```typescript
export class BoolRef {
    constructor(value?: boolean);
    value: boolean;
}
export class FloatRef {
    constructor(value?: number);
    value: number;
}
export class IntRef {
    constructor(value?: number);
    value: number;
}
export class DoubleRef {
    constructor(value?: number);
    value: number;
}
export class StringRef {
    constructor(initialValue: string, capacity: number);
    value: string;
    readonly capacity: number;
}

// Scalar parameter types used in function signatures:
type BoolParam    = BoolRef | null;          // nullable bool* (p_open etc.)
type BoolParamReq = BoolRef;                 // non-nullable bool* (checkbox v)
type FloatParam   = FloatRef;
type IntParam     = IntRef;
type DoubleParam  = DoubleRef;
type TextParam    = StringRef;
type FloatArray2  = Float32Array;            // must have length >= 2
type FloatArray3  = Float32Array;            // must have length >= 3
type FloatArray4  = Float32Array;            // must have length >= 4
type IntArray2    = Int32Array;
```

### InitRefs Integration

```cpp
// refs.cpp exports all ref types during module init
void InitRefs(Napi::Env env, Napi::Object exports) {
    exports.Set("BoolRef",   BoolRef::GetClass(env));
    exports.Set("FloatRef",  FloatRef::GetClass(env));
    exports.Set("IntRef",    IntRef::GetClass(env));
    exports.Set("DoubleRef", DoubleRef::GetClass(env));
    exports.Set("StringRef", StringRef::GetClass(env));
}
```

`InitRefs` must run before `InitFunctions` — function bindings call `BoolRef::Unwrap` etc.
which requires the class to be registered. Order: `InitRefs → InitStructs → InitFunctions → InitEnums`.

---

## 6a. Callback / Function Pointer System (FunctionRef)

All callback-taking functions are supported. JS functions are bridged to C function pointers
via a FunctionRef pattern and generic trampoline templates.

### Callback Patterns in the API

**18 function-pointer argument occurrences** across the API, grouped by invocation pattern:

| Pattern | Functions | Count | user_data Mechanism |
|---|---|---|---|
| Sync, `void*` in callback sig | Combo/ListBox/Plot getters | 8 | user_data is a callback parameter |
| Sync, separate `void*` arg | InputText/SizeConstraint | 4 | user_data delivered via callback data struct |
| Stored globally | SetAllocatorFunctions | 1 (2 callbacks) | user_data in callback signature |
| Stored in draw command | AddCallback/AddCallbackEx | 2 | userdata via `ImDrawCmd::UserCallbackData` |
| Platform/Renderer setters | PlatformIO setters | 4 | No user_data; viewport context |

Additionally, **34 function pointer fields** exist across structs:
- `ImGuiPlatformIO`: 29 fields (4 with paired `void*`, 25 use viewport context)
- `ImGuiIO`: 2 fields (`GetClipboardTextFn`, `SetClipboardTextFn` with `ClipboardUserData`)
- `ImGuiSelectionBasicStorage`: 1 field (`AdapterIndexToStorageId` with `UserData`)
- `ImGuiSelectionExternalStorage`: 1 field (`AdapterSetItemSelected` with `UserData`)
- `ImDrawCmd`: 1 field (`UserCallback` with `UserCallbackData`)

### Function Pointer Detection in JSON

Two forms exist in the JSON metadata:

**Form A — Inline function pointer:** `arg.type.type_details` exists with
`flavour: "function_pointer"`. Contains full `return_type` and `arguments` for the callback.

**Form B — Typedef reference:** `arg.type.description.kind == "User"` where the name matches
a function-pointer typedef. The 5 callback typedefs are:
`ImGuiInputTextCallback`, `ImGuiSizeCallback`, `ImGuiMemAllocFunc`, `ImGuiMemFreeFunc`,
`ImDrawCallback`.

Detection: check for `type_details` first (catches Form A), then cross-reference the typedef
table for Form B.

### Generic Trampoline Templates

One trampoline per unique callback signature. The trampoline is a static C-compatible function
that extracts the JS function reference from user_data and invokes it:

```cpp
// Trampoline for: const char* (*)(void* user_data, int idx)
// Used by: ComboCallback, ListBoxCallback
static const char* TrampolineStringGetter(void* user_data, int idx) {
    auto* ctx = static_cast<CallbackContext*>(user_data);
    Napi::Value result = ctx->func.Call({
        Napi::Number::New(ctx->env, idx)
    });
    ctx->lastString = result.As<Napi::String>().Utf8Value();
    return ctx->lastString.c_str();
}
```

The `CallbackContext` holds:
- `Napi::FunctionReference func` — persistent reference to the JS function
- `Napi::Env env` — the NAPI environment
- `std::string lastString` — storage for string return values (must outlive the pointer)

For synchronous callbacks (Patterns 1-2), the context lives on the C++ stack for the
duration of the function call. For stored callbacks (Patterns 3-5), the context is
allocated on the heap and its lifetime is tied to the FunctionRef JS object.

### Function Pointer Struct Fields

For struct fields that are function pointers (e.g., `ImGuiSelectionBasicStorage.AdapterIndexToStorageId`),
the generated setter sets BOTH the function pointer field (to the trampoline) AND the
paired user_data field (to the callback context). The getter returns the wrapped JS function
or null.

For `ImGuiPlatformIO` multi-viewport callbacks without explicit user_data, the trampoline
retrieves context from `ImGuiViewport::PlatformUserData` or `RendererUserData`.

---

## 7. Method Generation

**Source**: functions where `original_class` is non-null and first arg has `is_instance_pointer: true`.

**Exception**: functions with `is_static: true` are static methods (no instance pointer).
Currently only `ImColor_HSV` — see §4.

**Skip** `is_default_argument_helper: true` — JS handles defaults natively.

**Method name derivation**:
- Strip `StructName_` prefix from function name
- If a helper exists with name = `this_function.name` minus trailing `Ex`, strip `Ex`
- camelCase the remainder
- `ImDrawList_AddLineEx` → strip `ImDrawList_` → `AddLineEx` → strip `Ex` → `AddLine` → `addLine`
- `ImGuiListClipper_Begin` → `begin`

**Default value handling**:
- JSON `default_value` on argument → emit as JS default parameter in TypeScript
- In C++ body: check `info[n].IsUndefined()` and use the default when not provided
- For simple defaults (numbers, booleans): inline the value
- For compound defaults (`ImVec2(0,0)`, `NULL`): use conditional

**Method body pattern** (for `ImDrawList_AddLineEx`):
```cpp
Napi::Value AddLine(const Napi::CallbackInfo& info) {
    ImVec2 p1 = ExtractImVec2(info[0]);
    ImVec2 p2 = ExtractImVec2(info[1]);
    ImU32 col = info[2].As<Napi::Number>().Uint32Value();
    float thickness = info[3].IsUndefined() ? 1.0f : info[3].As<Napi::Number>().FloatValue();
    ImDrawList_AddLineEx(ptr, p1, p2, col, thickness);
    return info.Env().Undefined();
}
```

Note: `self->ptr` is the first argument to every C method call. The `self` arg from JS args
is skipped (starts from `info[0]` for the first non-self argument).

---

## 8. Free Function Generation

**Source**: functions where `original_class` is null.

**Skip rules**:
- `is_default_argument_helper: true` → skip (use Ex canonical version with JS default params)
- `is_manual_helper: true` → skip
- `is_imstr_helper: true` → skip
- `is_internal: true` → skip

**Varargs functions** (15 total) — NOT skipped. Generated as normal functions; the varargs
argument is dropped. The C call uses `"%s"` as the format string with the user's pre-formatted
string:

```cpp
// Generated for ImGui_Text(const char* fmt, ...)
Napi::Value Text(const Napi::CallbackInfo& info) {
    std::string text = info[0].As<Napi::String>().Utf8Value();
    ImGui_Text("%s", text.c_str());
    return info.Env().Undefined();
}
```

The user formats strings in JS before passing them. TypeScript type: `text(str: string): void`.

**Callback functions** — NOT skipped. Generated with FunctionRef trampoline support (see §6a).
The generator detects callback arguments via `type_details.flavour == "function_pointer"` or
cross-referencing the function-pointer typedef set.

**Function name derivation**:
- Strip `ImGui_` prefix (or other class prefix for methods)
- If a helper exists with name = `this_function.name` minus trailing `Ex`, strip `Ex`
- camelCase the result
- `ImGui_Begin` → strip `ImGui_` → `Begin` → `begin`
- `ImGui_DragFloatEx` → strip `ImGui_` → `DragFloatEx` → strip `Ex` → `DragFloat` → `dragFloat`
- C++ overloads (multiple C functions sharing `original_fully_qualified_name`) are kept as
  **separate JS functions** with their disambiguated C names (camelCased). No runtime dispatch.

**Attachment**: all free functions attached to the top-level exports object.

```js
// Flat on exports
exports.begin("name", null, 0);
exports.end();
exports.text("hello");
```

---

## 9. Naming Normalization (Summary)

| Input | Output |
|---|---|
| `ImDrawList` | `DrawList` |
| `ImGuiIO` | `IO` |
| `ImVec2` | `Vec2` |
| `ImVec4` | `Vec4` |
| `ImColor` | `Color` |
| `ImGuiListClipper` | `ListClipper` |
| `ImGuiWindowFlags_NoTitleBar` (field) | `NoTitleBar` (already done for enums) |
| `ImDrawList_AddLineEx` (method) | `addLine` |
| `ImGui_GetWindowPos` (free fn) | `getWindowPos` |
| `ImGui_DragFloatEx` (free fn) | `dragFloat` |
| `ImGui_GetColorU32ImVec4` (overload) | `getColorU32ImVec4` |
| `DisplaySize` (field) | `displaySize` |
| `ConfigFlags` (field) | `configFlags` |

Rule: strip leading `Im`/`ImGui` from type names, strip class prefix from method names,
strip `Ex` suffix when a helper exists for the base name, camelCase everything.
C++ overloads keep their disambiguating suffixes.

---

## 10. Skip List

### Skip Entirely

- All `ImVector_*` structs (26) — not wrapped as standalone classes; their data is exposed via parent struct ImVector field getters
- `ImFontAtlasBuilder`, `ImFontLoader` — forward-declared with zero appearances in C API function signatures
- `ImDrawListSharedData` — forward-declared, only appears as an internal draw list field and in one setup function
- Fields typed as `void*` — no type info, not safely bridgeable
- Fields named starting with `_` — imgui convention for private members
- `is_internal: true` fields/functions
- `is_default_argument_helper: true` functions — use the Ex canonical version with JS default params
- `is_manual_helper: true` functions — C-level glue, not part of the public API contract
- `is_imstr_helper: true` functions — C-level ImStr compatibility helpers, redundant in JS

### NOT Skipped (supported)

- **Varargs functions** (15 total) — generated as single-string-argument functions using `"%s"` format
- **Callback functions** (18 argument occurrences) — generated with FunctionRef trampoline support
- **ImVector fields** (30 across 15 structs) — generated as read-only JS array getters
- **Function pointer struct fields** (34 total) — generated with FunctionRef setter/getter

---

## 11. File & Module Structure

### Generated Files

```
lib/gen/napi/
    structs.h          # Forward declarations, extern constructor refs, Wrap() factories
    structs.cpp        # All ObjectWrap class implementations + InitStructs()
    functions.cpp      # All free function implementations + InitFunctions()
    callbacks.cpp      # Trampoline templates + CallbackContext + InitCallbacks()

lib/gen/dts/
    structs.d.ts       # All struct class/interface declarations
    functions.d.ts     # All free function declarations
    # enums.d.ts already exists
```

### Hand-Written Files (not generated)

```
lib/
    types.h            # Converter declarations (ExtractImVec2, ExtractImVec4, etc.)
    types.cpp          # Converter implementations
    refs.h             # BoolRef, FloatRef, IntRef, DoubleRef, StringRef declarations
    refs.cpp           # Ref class implementations + InitRefs()
```

Refs and type converters are hand-written because they depend on no JSON metadata —
they're pure infrastructure.

Rationale for single generated files: 75 structs x 2 files = 150 files is excessive. Single
file per category keeps compile units manageable and include paths simple.

### module.cpp Integration

```cpp
#include <napi.h>
#include "dcimgui.h"
#include "imgui.h"                // for IM_NEW/IM_DELETE and Category B constructors

#include "types.h"
#include "types.cpp"
#include "refs.h"
#include "refs.cpp"
#include "gen/napi/callbacks.cpp"  // trampoline templates (no init dependencies)
#include "gen/napi/structs.h"      // needs forward decls for cross-struct references
#include "gen/napi/structs.cpp"
#include "gen/napi/functions.cpp"
#include "gen/napi/enums.cpp"

Napi::Object Init(Napi::Env env, Napi::Object exports) {
    InitRefs(env, exports);      // FIRST: ref classes used by function bindings
    InitStructs(env, exports);   // SECOND: struct wrappers used by function bindings
    InitFunctions(env, exports); // THIRD: free functions reference both refs and structs
    InitEnums(env, exports);     // order-independent
    return exports;
}
```

**Init order is load-bearing.** `InitRefs` before `InitStructs` before `InitFunctions`.
Any wrapper class referenced during `Unwrap` calls must have its constructor registered first.

### JS API Shape

```js
const imgui = require('./imgui.node');

// Struct constructors on exports
const clipper = new imgui.ListClipper();
const vec = new imgui.Vec2(100, 200);
const ctx = new imgui.Context();  // calls ImGui_CreateContext
const fontCfg = new imgui.FontConfig();  // calls C++ constructor (non-zero defaults)

// Methods on instances
clipper.begin(1000);
while (clipper.step()) { ... }
clipper.end();

// Free functions on exports
imgui.begin("Hello");
imgui.end();
const pos = imgui.getWindowPos();  // returns Vec2 instance
const io = imgui.getIO();          // returns ImGuiIO borrowed wrapper
io.displaySize = {x: 1920, y: 1080};

// ImVector fields as JS arrays
const drawData = imgui.getDrawData();
for (const cmdList of drawData.cmdLists) {       // JS array of DrawList wrappers
    for (const cmd of cmdList.cmdBuffer) {        // JS array of DrawCmd wrappers
        // cmd.clipRect, cmd.elemCount, etc.
    }
    const vtx = cmdList.vtxBuffer;                // ArrayBuffer (zero-copy)
    const idx = cmdList.idxBuffer;                // Uint16Array (zero-copy)
}

// Callbacks
imgui.comboCallback("items", currentItem, (idx) => items[idx], items.length);
```

---

## 12. TypeScript Declaration Shape

```typescript
// structs.d.ts

export class Vec2 {
    constructor(x: number, y: number);
    x: number;
    y: number;
}

export class Vec4 {
    constructor(x: number, y: number, z: number, w: number);
    x: number; y: number; z: number; w: number;
}

export class Color {
    // By-value struct; wraps ImVec4
    value: Vec4;
    static hsv(h: number, s: number, v: number, a?: number): Color;
}

export class DrawList {
    // No public constructor — only obtained via getWindowDrawList() etc.
    addLine(p1: Vec2Like, p2: Vec2Like, col: number, thickness?: number): void;
    addRect(pMin: Vec2Like, pMax: Vec2Like, col: number, rounding?: number,
            roundingCorners?: number, thickness?: number): void;
    getClipRectMin(): Vec2;
    getClipRectMax(): Vec2;
    // ImVector fields — read-only JS arrays
    readonly cmdBuffer: ReadonlyArray<DrawCmd>;
    readonly vtxBuffer: ArrayBuffer;
    readonly idxBuffer: Uint16Array;
    // ... all non-skipped methods
}

export class IO {
    // No public constructor — only obtained via getIO()
    configFlags: number;
    displaySize: Vec2;
    deltaTime: number;
    // ... all non-skipped fields
}

export class Style {
    // No public constructor — only obtained via getStyle()
    readonly colors: Float32Array;  // ImVec4[ImGuiCol_COUNT] flattened
    alpha: number;
    // ... all non-skipped fields
}

export class FontConfig {
    constructor();  // calls C++ constructor with correct defaults
    fontDataOwnedByAtlas: boolean;
    sizePixels: number;
    // ... all non-skipped fields
}

export class ListClipper {
    constructor();
    displayStart: number;
    displayEnd: number;
    begin(itemsCount: number, itemsHeight?: number): void;
    step(): boolean;
    end(): void;
}

export class Context {
    constructor(sharedFontAtlas?: FontAtlas | null);
}

// functions.d.ts

export type Vec2Like = Vec2 | [number, number] | {x: number, y: number};

export function begin(name: string, p_open?: BoolRef | null, flags?: number): boolean;
export function end(): void;
export function getIO(): IO;
export function getWindowPos(): Vec2;
export function text(text: string): void;
export function dragFloat(label: string, v: FloatRef, vSpeed?: number,
    vMin?: number, vMax?: number, format?: string, flags?: number): boolean;
export function colorEdit4(label: string, col: Float32Array, flags?: number): boolean;
export function comboCallback(label: string, currentItem: IntRef,
    getter: (idx: number) => string, itemsCount: number,
    popupMaxHeightInItems?: number): boolean;
// ...
```

---

## 13. Generator Code Structure

```
gen/
    main.py       # orchestrator: loads JSON, calls generators, writes files
    config.py     # paths (exists)
    enums.py      # enum generation (exists)
    naming.py     # NEW: shared name normalization functions
    types.py      # NEW: type descriptor → C++ converter expression + TS type string
    structs.py    # NEW: ObjectWrap class generation (structs.h, structs.cpp, structs.d.ts)
    functions.py  # NEW: free function generation (functions.cpp, functions.d.ts)
    callbacks.py  # NEW: trampoline template generation (callbacks.cpp)
```

### types.py Responsibilities

Central registry mapping JSON type descriptors to:
1. The C++ NAPI extraction expression (JS → C)
2. The C++ NAPI wrapping expression (C → JS)
3. The TypeScript type string

This is the only file that knows about conversions. Both `structs.py` and `functions.py`
import from `types.py`. If a type is unknown/unsupported, `types.py` returns `None` and the
caller skips that field/function with a comment in the generated output.

**Typedef chain resolution:** `types.py` builds a lookup table from JSON `typedefs`. For any
`kind: "User"` type, it walks chains (max 2 hops) to resolve to a `kind: "Builtin"`. External
types not in the table (`size_t`) are hardcoded. Function-pointer typedefs are identified by
`type_details.flavour == "function_pointer"` in the typedef entry.

**Array bounds resolution:** `types.py` builds a constant table from JSON `enums`, collecting
all entries with `is_count: true` and their numeric `value`. This resolves symbolic bounds
like `"ImGuiCol_COUNT"` to integers for fixed-size array field generation.

`types.py` must handle the special mutable parameter cases:
- `bool*` (nullable) → `BoolRef::Unwrap` with null check — detected by `default_value == "NULL"`
- `bool*` (non-nullable) → `BoolRef::Unwrap` direct — no `default_value: "NULL"`
- `float*` → `FloatRef::Unwrap`
- `int*` → `IntRef::Unwrap`
- `double*` → `DoubleRef::Unwrap`
- `float[N]` → `Float32Array` extraction
- `int[N]` → `Int32Array` extraction
- `(char*, size_t)` pair → `StringRef::Unwrap` (fused, consumes one JS arg slot)
- `out_*` named pointers → stack allocation, returned in result object
- Function pointer args → FunctionRef trampoline (delegates to `callbacks.py`)

### callbacks.py Responsibilities

1. Collect all unique callback signatures from functions and struct fields
2. Generate a trampoline function per unique signature
3. Generate `CallbackContext` struct(s) for holding `Napi::FunctionReference` + state
4. Generate `callbacks.cpp` with all trampolines

Detection logic:
- Form A: `arg.type.type_details` exists with `flavour: "function_pointer"` → inline FP
- Form B: `arg.type.description.kind == "User"` and name is in function-pointer typedef set
  (`ImGuiInputTextCallback`, `ImGuiSizeCallback`, `ImGuiMemAllocFunc`, `ImGuiMemFreeFunc`,
  `ImDrawCallback`)

### structs.py Responsibilities

1. Filter structs: skip `ImVector_*`, skip forward-declared (except ImGuiContext)
2. Classify each struct: Category A (zero-init), B (C++ ctor), C (special), or borrow-only
3. For each struct: collect its methods by grouping functions on `original_class`
4. Generate ObjectWrap class with:
   - Constructor (owned path: zero-init, C++ ctor, or special; + borrowed path via External)
   - Destructor (`delete`, `IM_DELETE`, `ImGui_DestroyContext`, or no-op based on category)
   - Field accessors (get/set per field, including ImVector array getters, using types.py)
   - Method bindings (for each grouped method, using types.py)
   - Static methods (detected by `is_static: true`)
   - `static Wrap()` factory
   - `static Init(env, exports)` that sets up the class and registers on exports
5. Generate TypeScript class declaration

### functions.py Responsibilities

1. Filter functions: only `original_class == null`, apply skip rules
2. Handle varargs: drop varargs arg, use `"%s"` format string pattern
3. Handle callbacks: use trampoline from callbacks.py
4. For each function: generate NAPI binding using types.py
5. Generate `InitFunctions(env, exports)`
6. Generate TypeScript function declarations

---

## 14. Known Gotchas & Hazards

1. **`const char*` temporaries** — always store `Utf8Value()` in a named `std::string` before
   `.c_str()`. Generator must enforce this pattern.

2. **Borrowed pointer lifetime** — wrappers obtained mid-frame (draw list, viewport, IO) are
   invalid after `ImGui_Render()`. Document clearly. Do not attempt to detect this in C++.

3. **Field ImVec2 is always a copy** — `io.displaySize` returns a new `Vec2` object every call,
   not a reference. Mutation must be done via assignment: `io.displaySize = new Vec2(...)` or
   `io.displaySize = {x:..., y:...}`. Do not attempt to make `io.displaySize.x = 5` work — it
   would modify a temporary.

4. **Struct constructor for borrow-only types** — `IO`, `DrawList`, `Style`, etc. must NOT
   expose a JS constructor. If `new imgui.IO()` is called, it would allocate a C struct but
   that struct is meaningless without the imgui context having set it up. The constructor
   should throw: `Napi::TypeError::New(env, "IO cannot be constructed directly")`.

5. **`ImGuiContext` destructor** — must call `ImGui_DestroyContext(ptr)`, NOT `delete ptr`.
   Calling `delete` on an imgui context will not run imgui's internal cleanup. This is the
   only struct with this requirement.

6. **`ImDrawList_CloneOutput` destructor** — must use `IM_DELETE`, NOT `delete`. The memory
   was allocated via `IM_NEW` (imgui's custom allocator). Using C++ `delete` causes heap
   corruption. This is detected via the `OWNED_RETURNS` override table.

7. **Category B constructors** — `ImFontConfig`, `ImGuiWindowClass`, `ImGuiSelectionBasicStorage`
   must use placement-new with the real C++ constructor. Zero-initialization produces
   incorrect/dangerous defaults (invisible fonts, NULL function pointers, wrong docking behavior).
   Detected via the `NEEDS_CPP_CONSTRUCTOR` override table.

8. **InitStructs before InitFunctions** — function bindings call `StructWrap::Wrap()` which
   uses `StructWrap::constructor`. The constructor reference is set during `InitStructs`.
   Wrong order = segfault.

9. **`std::string` and multiple C calls** — if a function has two `const char*` args, store
   each as a separate named `std::string`. Do not reuse the same variable name.

10. **Default value `NULL` for pointer args** — JSON `default_value: "NULL"` means the C arg
    can be `nullptr`. In generated code: `info[n].IsUndefined() || info[n].IsNull() ? nullptr : ...`.

11. **Enum arguments** — enum types are `int` in C. Accept as `Napi::Number`, cast to the enum
    type with a C cast: `(ImGuiWindowFlags)info[n].As<Napi::Number>().Int32Value()`. TypeScript
    types them as `number` (the enum object values are already numbers from stage 1).

12. **`is_default_argument_helper` naming** — these shorter-arg variants have the same base
    name as the Ex version (e.g., `ImGui_DragFloat` is the helper, `ImGui_DragFloatEx` is
    canonical). We skip the helper, expose the Ex version under the base name (stripping `Ex`),
    and implement it with the Ex function body using JS defaults. `Ex` suffix never appears
    in the JS API. Detection: for each function, check if a helper exists with name =
    `this_name` minus trailing `Ex` and `is_default_argument_helper: true`. Edge cases:
    `ImGui_TreeNodeEx` is NOT an Ex-variant (different `original_fully_qualified_name`).

13. **StringRef buffer stability** — `std::vector<char>` reallocates when grown. Never call
    `resize()` or any mutating method on `StringRef::buf` after construction. The pointer
    passed to imgui (`sref->Data()`) must remain valid for the entire frame. This is safe as
    long as the `StringRef` object is not GC'd mid-frame (it won't be, since JS holds a
    reference to it).

14. **Float32Array alignment** — `Float32Array::Data()` returns `void*`. The cast to `float*`
    is safe only if the buffer is 4-byte aligned. Node.js `ArrayBuffer` allocations are always
    at least 8-byte aligned. Safe.

15. **`(char*, size_t)` fusion — argument index shift** — the generator must be aware that
    the `(char* buf, size_t buf_size)` C parameter pair maps to ONE JS argument (a `StringRef`).
    All subsequent parameter indices shift by -1. A generator that naively maps `info[N]` to
    the Nth C argument will produce wrong bindings for all parameters after a fused pair.

16. **Nullable bool* detection** — the JSON does not set `is_nullable: true` on the type
    descriptor for `bool*` arguments. Nullability is determined by `argument.default_value == "NULL"`.
    Check `default_value`, not the type descriptor. This is the authoritative rule — see §6.

17. **`ImTextureID` type** — confirmed in `dcimgui.h` line 377: `typedef ImU64 ImTextureID`.
    It is always a 64-bit unsigned integer, not `void*`. JS `number` is a 64-bit float and can
    represent integers exactly only up to 2^53. For backends that use GPU texture handles (which
    are typically small integers 0-N), `number` is safe in practice. For backends that store raw
    pointers as texture IDs (64-bit addresses), `number` will silently lose precision on high
    addresses. Use `Napi::BigInt` for correctness, or `Napi::Number` with documented caveat.
    Recommend `BigInt` for `ImTextureID` specifically; all other `ImU64` occurrences are rare
    enough to handle case-by-case.

18. **Varargs via `"%s"` format** — all 15 varargs functions (`ImGui_Text`, `ImGui_TextColored`,
    `ImGui_TreeNodeStr`, etc.) are generated as single-string functions. The C call always uses
    `"%s"` as the format string: `ImGui_Text("%s", str.c_str())`. This safely passes the user's
    string without printf interpretation — strings containing `%` characters are handled correctly.

19. **ImVector field getters create new arrays each call** — calling `drawList.cmdBuffer`
    allocates a new JS array and wraps each element every time. Do not call in a tight loop
    without caching. VtxBuffer/IdxBuffer are zero-copy TypedArray views (no allocation per
    element), but the view object itself is created each call.

20. **`const char*` long-term retention** — some imgui fields retain the `const char*` pointer
    long-term (e.g., `ImGuiIO.IniFilename`, `ImFontConfig.GlyphRanges`). Setting these from
    JS via a temporary `Utf8Value()` produces a dangling pointer. This is the library user's
    responsibility: they must provide a ref (e.g., `StringRef`) with a lifespan that covers
    imgui's needs, or accept the potential for leaked memory in exchange for simplicity.

21. **Callback trampoline and string returns** — for callbacks that return `const char*`
    (e.g., Combo/ListBox getters), the trampoline must store the `std::string` result in the
    `CallbackContext` so the pointer survives until imgui finishes reading it. The context's
    `lastString` member serves this purpose.
