# Stage 2: Struct & Function Bindings — Implementation Plan

## 0. Fundamental Contract

The call chain is strictly:

```
JS → NAPI C++ → dcimgui.h (C ABI) → dcimgui.cpp (C wrapper) → imgui (C++)
```

Generated NAPI code includes only `dcimgui.h`. imgui headers are never touched.
Dear bindings has already solved all C++ compatibility: opaque structs, by-value conversions,
method dispatch via reinterpret_cast. We call plain C functions.

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

Two reasons to skip both wrappers and field accessors for these:

**1. Zero C API coverage.** Searched entire JSON functions array: there are no functions with
`original_class` set to any `ImVector_*` type. No iteration helpers, no accessors, nothing.
Exposing the struct would give the user three raw fields (`size`, `capacity`, `data`) with no
way to do anything useful with them from JS without unsafe pointer arithmetic into `Data`.

**2. The data they hold is better surfaced via parent struct methods.** Where ImVector fields
matter for real usage (e.g., iterating `ImDrawData.CmdLists` for a custom renderer, reading
glyph data from `ImFont`), the right approach is purpose-built accessor methods on those parent
structs — returning JS arrays of wrapped elements — rather than raw vector access. These are
advanced backend use cases that warrant manual bindings, not auto-generated field pass-through.

24 regular structs contain ImVector_* fields. Those fields are skipped in accessor generation;
the rest of their fields are generated normally.

### 1d. Regular Structs (~41 remaining)

Full field definitions available in `dcimgui.h`. These are the main generation targets.

**Sub-classification by constructability:**

The rule: a struct is user-constructable if and only if (a) no C API function is the
authoritative source for its allocation, AND (b) zero-initializing its fields is a valid
starting state (i.e., it has no C++ constructor logic that dear_bindings fails to expose,
confirmed by checking whether its C++ constructor does meaningful work beyond zeroing).

| Struct | Constructable | Evidence & Reasoning |
|---|---|---|
| `ImGuiListClipper` | Yes (owned) | No alloc function. Fields are zero-valid; `Begin()` sets up state. |
| `ImGuiTextFilter` | Yes (owned) | No alloc function. Zero-init gives empty filter, `Draw()` works immediately. |
| `ImGuiStorage` | Yes (owned) | No alloc function. Empty `Data` ImVector is valid (zero-init). |
| `ImGuiTextBuffer` | Yes (owned) | No alloc function. Empty `Buf` ImVector is valid. |
| `ImGuiSelectionBasicStorage` | Yes (owned) | No alloc function. Zero-init is valid start state. |
| `ImGuiWindowClass` | Yes (owned) | No alloc function. Pure config struct; zero-init gives default behavior. |
| `ImFontConfig` | Yes (owned) | No alloc function. Config struct passed to `ImFontAtlas_AddFont*()`; zero-init gives default font settings. |
| `ImGuiContext` | Yes (special) | Must use `ImGui_CreateContext()` — runs C++ constructor, allocates internal state. `new ImGuiContext{}` would produce a corrupt/unusable context. |
| `ImGuiIO` | **No** | Only `ImGui_GetIO()` returns `ImGuiIO*`. Owned by context; its fields are initialized by imgui at context creation. Constructing one in isolation produces a struct disconnected from all context state. |
| `ImGuiStyle` | **No** | Only `ImGui_GetStyle()` returns `ImGuiStyle*`. Owned by context. |
| `ImDrawList` | **No (mostly)** | 5 accessor fns return borrowed ptrs. Exception: `ImDrawList_CloneOutput()` returns an owned copy — see §2. |
| `ImFont` | **No** | Only via `ImFontAtlas_AddFont*()` (9 fns). Atlas owns font lifetime. |
| `ImFontAtlas` | **No** | Zero functions in the entire C API return `ImFontAtlas*`. Accessed via `io->Fonts`. Its C++ constructor does non-trivial initialization (sets texture format, format defaults); zero-init would be incorrect. |
| `ImGuiViewport` | **No** | Only 4 accessor functions return it; all are imgui-owned per-window/platform state. |
| `ImDrawData` | **No** | Only `ImGui_GetDrawData()`. Populated by imgui during `Render()`; constructing one empty has no use. |
| Remaining data structs | **No** | `ImDrawCmd`, `ImDrawVert`, `ImFontGlyph`, `ImGuiKeyData`, etc. are internal data records only ever accessed as fields or array elements of parent structs. No standalone use case. |

Non-constructable structs are only ever created via borrowed factory wrapping.

---

## 2. Memory Management

### The Core Model

Every non-by-value wrapper carries two fields:

```cpp
StructType* ptr;
bool owned;
```

- `owned = true`: we allocated the memory with `new`. GC calls `delete ptr`.
- `owned = false`: imgui owns the memory. GC is a no-op.

### Construction Pattern

**Owned (JS `new`):**

Dear bindings does NOT generate `_StructName()` constructor or `_destroy()` destructor functions.
Confirmed: searched entire JSON, none exist. Therefore:

```cpp
// Allocate
ptr = new StructType{};  // C++ value-init: zeros all POD fields
owned = true;
```

Zero-initialization is safe for the constructable structs listed in §1d because:
- `ImGuiListClipper`, `ImGuiTextFilter`, `ImGuiTextBuffer`, `ImGuiStorage`, `ImGuiSelectionBasicStorage`: their C++ constructors only zero members (confirmed: dear_bindings generates NO constructor wrappers for them, meaning imgui's own C++ ctor is trivial/POD-equivalent).
- `ImGuiWindowClass`, `ImFontConfig`: pure config structs — zero-init represents "use all defaults", which is the intended starting state before the user fills in fields.

The structs NOT in this list (IO, Style, Font, etc.) are excluded precisely because their C++
constructors do meaningful work, and dear_bindings exposes no way to call them.

**Special case: `ImGuiContext`**

```cpp
// Construct:
ptr = ImGui_CreateContext(nullptr);
owned = true;

// Destruct:
if (owned) ImGui_DestroyContext(ptr);
// Do NOT use 'delete' for ImGuiContext — ever.
```

**Borrowed (returned by imgui C API):**

```cpp
ptr = <pointer returned from C function>;
owned = false;
// destructor: nothing
```

### Special Case: ImDrawList_CloneOutput

`ImDrawList_CloneOutput(self)` is the **only non-Context function that returns an owned pointer**.
It allocates a deep copy of the draw list that the caller is responsible for freeing.
The generated binding for this function must set `owned = true` on the returned wrapper,
unlike all other `ImDrawList*`-returning functions which are borrowed.

Detection in generator: check function name directly — this is a known exception,
not derivable from JSON metadata alone. Hard-code it or annotate via a config override.

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
        if (owned) delete ptr;
    }
};
// Note: for owned structs (ListClipper, TextFilter, etc.) the else branch does:
//   ptr = new StructType{};
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
| `bool*`, `int*`, `float*` (non-const, non-self) | Out-parameter (see §6) |
| `void*` | Skip / `Napi::External<void>` |
| `StructType*` where struct is in skip list (`ImVector_*`) | Skip |
| Forward-declared struct pointer | Opaque handle |
| Function pointer (`callback`) | Defer / skip |

### Fixed-Size Array Types

| C type | NAPI | TS |
|---|---|---|
| `float[2]`, `float[3]`, `float[4]` | `Napi::Float32Array` | `Float32Array` |
| `int[2]`, `int[3]`, `int[4]` | `Napi::Int32Array` | `Int32Array` |
| `ImU8[N]` large | Skip (internal) | — |
| `const char*[]` | `Napi::Array` of strings | `string[]` |

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

---

## 5. Field Accessor Generation

For each non-skipped field of a regular struct, generate a getter + setter pair.

### Field Skip Conditions

Skip a field if:
- Its type is `ImVector_*`
- Its type is a forward-declared struct (opaque)
- Its type is `void*`
- Its type is a function pointer
- It is marked `is_internal: true` in JSON
- Its name starts with `_` (internal imgui convention)

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

**Fixed array field** (`float[4]`, `int[2]`):
```cpp
// Return a Float32Array view into the struct's memory
Napi::Value GetSomeArray(const Napi::CallbackInfo& info) {
    auto buf = Napi::ArrayBuffer::New(info.Env(), 4 * sizeof(float));
    memcpy(buf.Data(), ptr->SomeArray, 4 * sizeof(float));
    return Napi::Float32Array::New(info.Env(), 4, buf, 0);
}
```

Returning a copy (not a view) avoids the dangling memory hazard.

**Field naming**: camelCase the C field name. `DisplaySize` → `displaySize`, `ConfigFlags` → `configFlags`.

---

## 6. Output Parameter Protocol

**Definition**: An output parameter is a function argument that is:
- A pointer to a non-const primitive type: `bool*`, `int*`, `float*`, `ImVec2*`, `ImVec4*`
- Not the `self` instance pointer (`is_instance_pointer: false`)
- Not `void*`

Detection rule from JSON type descriptor:
```
kind == "Pointer" AND inner_type has no "const" storage class AND inner_type is Builtin or known by-value User type
```

### Handling Pattern

In-out parameters (user provides current value, imgui may update it):

**C signature**: `bool ImGui_Begin(const char* name, bool* p_open, ImGuiWindowFlags flags)`

**Generated JS**:
```js
// p_open defaults to null (no close button)
begin(name: string, p_open: boolean | null, flags: number): { result: boolean, p_open?: boolean }
```

**Generated C++ body**:
```cpp
Napi::Value Begin(const Napi::CallbackInfo& info) {
    std::string name = info[0].As<Napi::String>().Utf8Value();
    bool has_p_open = !info[1].IsNull() && !info[1].IsUndefined();
    bool p_open_val = has_p_open ? info[1].As<Napi::Boolean>().Value() : false;
    ImGuiWindowFlags flags = info[2].As<Napi::Number>().Int32Value();

    bool result = ImGui_Begin(name.c_str(), has_p_open ? &p_open_val : nullptr, flags);

    Napi::Object ret = Napi::Object::New(info.Env());
    ret.Set("result", Napi::Boolean::New(info.Env(), result));
    if (has_p_open) ret.Set("p_open", Napi::Boolean::New(info.Env(), p_open_val));
    return ret;
}
```

### Simplification Rules

- If the C return type is `void` AND there is exactly ONE output param: return the out value directly (not wrapped in object).
- If the C return type is non-void AND there are NO output params: return the value directly.
- Only wrap in a result object when there are mixed returns (C return + out params together).

---

## 7. Method Generation

**Source**: functions where `original_class` is non-null and first arg has `is_instance_pointer: true`.

**Skip** `is_default_argument_helper: true` — JS handles defaults natively.

**Method name derivation**:
- Strip `StructName_` prefix from function name
- camelCase the remainder
- `ImDrawList_AddLine` → strip `ImDrawList_` → `AddLine` → `addLine`
- `ImGuiListClipper_Begin` → `begin`

**Default value handling**:
- JSON `default_value` on argument → emit as JS default parameter in TypeScript
- In C++ body: check `info[n].IsUndefined()` and use the default when not provided
- For simple defaults (numbers, booleans): inline the value
- For compound defaults (`ImVec2(0,0)`, `NULL`): use conditional

**Method body pattern** (for `ImDrawList_AddLine`):
```cpp
Napi::Value AddLine(const Napi::CallbackInfo& info) {
    ImVec2 p1 = ExtractImVec2(info[0]);
    ImVec2 p2 = ExtractImVec2(info[1]);
    ImU32 col = info[2].As<Napi::Number>().Uint32Value();
    float thickness = info[3].IsUndefined() ? 1.0f : info[3].As<Napi::Number>().FloatValue();
    ImDrawList_AddLine(ptr, p1, p2, col, thickness);
    return info.Env().Undefined();
}
```

Note: `self->ptr` is the first argument to every C method call. The `self` arg from JS args
is skipped (starts from `info[0]` for the first non-self argument).

---

## 8. Free Function Generation

**Source**: functions where `original_class` is null.

**Skip rules** (same as methods plus):
- `is_default_argument_helper: true` → skip (use Ex versions)
- `is_manual_helper: true` → skip
- `is_imstr_helper: true` → skip
- `is_internal: true` → skip
- Has varargs (`is_varargs: true` on any argument) → skip (cannot bridge to JS)
- Has function pointer arguments → skip (defer to later stage)

**Function name derivation**:
- Strip `ImGui_` prefix
- camelCase the result
- `ImGui_Begin` → strip `ImGui_` → `Begin` → `begin`
- `ImGui_GetWindowPos` → `getWindowPos`
- `ImGui_SetNextWindowPos` → `setNextWindowPos`

**Attachment**: all free functions attached to the top-level exports object under a namespace.

```js
// Preferred: flat on exports
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
| `ImDrawList_AddLine` (method) | `addLine` |
| `ImGui_GetWindowPos` (free fn) | `getWindowPos` |
| `DisplaySize` (field) | `displaySize` |
| `ConfigFlags` (field) | `configFlags` |

Rule: strip leading `Im`/`ImGui` from type names, strip class prefix from method names,
camelCase everything.

---

## 10. Skip / Defer List

### Skip Entirely

- All `ImVector_*` structs (26) — 3 raw fields, zero C API methods; useful data accessed via parent struct purpose-built accessors
- `ImFontAtlasBuilder`, `ImFontLoader` — forward-declared with zero appearances in C API function signatures
- `ImDrawListSharedData` — forward-declared, only appears as an internal draw list field and in one setup function
- Fields typed as `ImVector_*` (24 structs affected) — see §1c
- Fields typed as `void*` — no type info, not safely bridgeable
- Fields typed as function pointers — not bridgeable; deferred
- Fields named starting with `_` — imgui convention for private members
- `is_internal: true` fields/functions
- `is_default_argument_helper: true` functions — use the Ex canonical version with JS default params
- `is_manual_helper: true` functions — C-level glue, not part of the public API contract
- `is_imstr_helper: true` functions — C-level ImStr compatibility helpers, redundant in JS

### Defer to Later Stage

- Functions with varargs (`...`) — 15 total, expose as `text(str: string)` as manual binding
- Functions with function pointer arguments — 24 total, requires JS→C trampoline
- `void* user_data` patterns — requires persistent JS reference storage

---

## 11. File & Module Structure

### Generated Files

```
lib/gen/napi/
    structs.h          # Forward declarations, extern constructor refs, Wrap() factories
    structs.cpp        # All ObjectWrap class implementations + InitStructs()
    functions.cpp      # All free function implementations + InitFunctions()

lib/gen/dts/
    structs.d.ts       # All struct class/interface declarations
    functions.d.ts     # All free function declarations
    # enums.d.ts already exists
```

Rationale for single files: 75 structs × 2 files = 150 files is excessive. Single file per
category keeps compile units manageable and include paths simple.

### module.cpp Integration

```cpp
#include "gen/napi/structs.h"   // needs forward decls for cross-struct references
#include "gen/napi/structs.cpp"
#include "gen/napi/functions.cpp"
#include "gen/napi/enums.cpp"

Napi::Object Init(Napi::Env env, Napi::Object exports) {
    InitStructs(env, exports);   // registers constructor functions on exports
    InitFunctions(env, exports); // registers free functions on exports
    InitEnums(env, exports);     // already exists
    return exports;
}
```

`InitStructs` must run before `InitFunctions` because function bindings that return structs
need the wrapper constructors already registered.

### JS API Shape

```js
const imgui = require('./imgui.node');

// Struct constructors on exports
const clipper = new imgui.ListClipper();
const vec = new imgui.Vec2(100, 200);
const ctx = new imgui.Context();  // calls ImGui_CreateContext

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

export class DrawList {
    // No public constructor — only obtained via getWindowDrawList() etc.
    addLine(p1: Vec2Like, p2: Vec2Like, col: number, thickness?: number): void;
    addRect(pMin: Vec2Like, pMax: Vec2Like, col: number, rounding?: number,
            roundingCorners?: number, thickness?: number): void;
    getClipRectMin(): Vec2;
    getClipRectMax(): Vec2;
    // ... all non-skipped methods
}

export class IO {
    // No public constructor — only obtained via getIO()
    configFlags: number;
    displaySize: Vec2;
    deltaTime: number;
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

export function begin(name: string, p_open?: boolean | null, flags?: number):
    { result: boolean, p_open?: boolean };
export function end(): void;
export function getIO(): IO;
export function getWindowPos(): Vec2;
export function text(text: string): void;
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
```

### types.py Responsibilities

Central registry mapping JSON type descriptors to:
1. The C++ NAPI extraction expression (JS → C)
2. The C++ NAPI wrapping expression (C → JS)
3. The TypeScript type string

This is the only file that knows about conversions. Both `structs.py` and `functions.py`
import from `types.py`. If a type is unknown/unsupported, `types.py` returns `None` and the
caller skips that field/function with a comment in the generated output.

### structs.py Responsibilities

1. Filter structs: skip `ImVector_*`, skip forward-declared (except ImGuiContext)
2. For each struct: collect its methods by grouping functions on `original_class`
3. Generate ObjectWrap class with:
   - Constructor (owned path + borrowed path via External)
   - Destructor (delete or ImGui_DestroyContext for context)
   - Field accessors (get/set per field, using types.py)
   - Method bindings (for each grouped method, using types.py)
   - `static Wrap()` factory
   - `static Init(env, exports)` that sets up the class and registers on exports
4. Generate TypeScript class declaration

### functions.py Responsibilities

1. Filter functions: only `original_class == null`, apply skip rules
2. For each function: generate NAPI binding using types.py
3. Generate `InitFunctions(env, exports)`
4. Generate TypeScript function declarations

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

4. **ImVector_* fields** — silently skipped. If a struct field is of type `ImVector_*`, no
   accessor is generated. Document per-struct which fields are omitted.

5. **Struct constructor for borrow-only types** — `IO`, `DrawList`, `Style`, etc. must NOT
   expose a JS constructor. If `new imgui.IO()` is called, it would allocate a C struct but
   that struct is meaningless without the imgui context having set it up. The constructor
   should throw: `Napi::TypeError::New(env, "IO cannot be constructed directly")`.

6. **`ImGuiContext` destructor** — must call `ImGui_DestroyContext(ptr)`, NOT `delete ptr`.
   Calling `delete` on an imgui context will not run imgui's internal cleanup. This is the
   only struct with this requirement.

7. **InitStructs before InitFunctions** — function bindings call `StructWrap::Wrap()` which
   uses `StructWrap::constructor`. The constructor reference is set during `InitStructs`.
   Wrong order = segfault.

8. **`std::string` and multiple C calls** — if a function has two `const char*` args, store
   each as a separate named `std::string`. Do not reuse the same variable name.

9. **Default value `NULL` for pointer args** — JSON `default_value: "NULL"` means the C arg
   can be `nullptr`. In generated code: `info[n].IsUndefined() || info[n].IsNull() ? nullptr : ...`.

10. **Enum arguments** — enum types are `int` in C. Accept as `Napi::Number`, cast to the enum
    type with a C cast: `(ImGuiWindowFlags)info[n].As<Napi::Number>().Int32Value()`. TypeScript
    types them as `number` (the enum object values are already numbers from stage 1).

11. **`is_default_argument_helper` naming** — these shorter-arg variants may have the same base
    name as the Ex version (e.g., `ImDrawList_AddLine` is the helper, `ImDrawList_AddLineEx` is
    canonical). We expose `AddLine` as the JS name (stripping `Ex` suffix) but implement it
    using the Ex function body with defaults. Alternatively: use the Ex function body directly
    under the non-Ex name. Either way, `Ex` suffix never appears in the JS API.

12. **`ImTextureID` type** — confirmed in `dcimgui.h` line 377: `typedef ImU64 ImTextureID`.
    It is always a 64-bit unsigned integer, not `void*`. JS `number` is a 64-bit float and can
    represent integers exactly only up to 2^53. For backends that use GPU texture handles (which
    are typically small integers 0–N), `number` is safe in practice. For backends that store raw
    pointers as texture IDs (64-bit addresses), `number` will silently lose precision on high
    addresses. Use `Napi::BigInt` for correctness, or `Napi::Number` with documented caveat.
    Recommend `BigInt` for `ImTextureID` specifically; all other `ImU64` occurrences are rare
    enough to handle case-by-case.
