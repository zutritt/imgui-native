#include "string_list.h"

#include <stdexcept>

Napi::Object StringListRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func =
      DefineClass(env, "StringListRef",
                  {
                      InstanceMethod<&StringListRef::Update>("update"),
                      InstanceAccessor<&StringListRef::GetCount>("count"),
                  });
  exports.Set("StringListRef", func);
  return exports;
}

StringListRef::StringListRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<StringListRef>(info) {
  if (info.Length() > 0 && info[0].IsArray()) {
    LoadFromJsArray(info[0].As<Napi::Array>());
  }
}

void StringListRef::LoadFromJsArray(const Napi::Array& arr) {
  strings_.clear();
  uint32_t len = arr.Length();
  strings_.reserve(len);
  for (uint32_t i = 0; i < len; ++i) {
    strings_.push_back(arr.Get(i).As<Napi::String>().Utf8Value());
  }
  RebuildPtrs();
}

void StringListRef::RebuildPtrs() {
  ptrs_.clear();
  ptrs_.reserve(strings_.size());
  for (const auto& s : strings_) {
    ptrs_.push_back(s.c_str());
  }
}

Napi::Value StringListRef::GetCount(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), Count());
}

Napi::Value StringListRef::Update(const Napi::CallbackInfo& info) {
  if (info.Length() > 0 && info[0].IsArray()) {
    LoadFromJsArray(info[0].As<Napi::Array>());
  }
  return info.Env().Undefined();
}
