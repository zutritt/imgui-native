#pragma once

#include <napi.h>

class DoubleRef : public Napi::ObjectWrap<DoubleRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  DoubleRef(const Napi::CallbackInfo& info);

  inline double Value();
  inline double* Ptr();

 private:
  double value;

  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& value);
};
