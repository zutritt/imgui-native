#pragma once

#include <napi.h>

class StringRef : public Napi::ObjectWrap<StringRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  StringRef(const Napi::CallbackInfo& info);

  inline char* Data();
  inline size_t Capacity();

 private:
  std::string value;

  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& value);

  void Resize(const Napi::CallbackInfo& info);
};
