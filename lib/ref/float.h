#pragma once

#include <napi.h>

class FloatRef : public Napi::ObjectWrap<FloatRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  FloatRef(const Napi::CallbackInfo& info);

  inline float Value();
  inline float* Ptr();

 private:
  float value;

  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& value);
};
