#include "types.h"
#include "gen/napi/structs.h"

ImVec2 ExtractImVec2(const Napi::Value& v) {
  auto* w = Vec2Wrap::Unwrap(v.As<Napi::Object>());
  return w->value;
}

ImVec4 ExtractImVec4(const Napi::Value& v) {
  auto* w = Vec4Wrap::Unwrap(v.As<Napi::Object>());
  return w->value;
}

ImColor ExtractImColor(const Napi::Value& v) {
  auto* w = ColorWrap::Unwrap(v.As<Napi::Object>());
  return w->value;
}

ImTextureRef ExtractImTextureRef(const Napi::Value& v) {
  auto* w = TextureRefWrap::Unwrap(v.As<Napi::Object>());
  return w->value;
}
