#pragma once

#include <napi.h>

class BoolRef : public Napi::ObjectWrap<BoolRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  BoolRef(const Napi::CallbackInfo& info);

  bool Value();
  bool* Ptr();

 private:
  bool value;

  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& value);
};
