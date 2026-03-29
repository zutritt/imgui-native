#pragma once

#include <napi.h>

class IntRef : public Napi::ObjectWrap<IntRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  IntRef(const Napi::CallbackInfo& info);

  int32_t Value();
  int32_t* Ptr();

 private:
  int32_t value;

  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& value);
};
