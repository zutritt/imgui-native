#include "double.h"

Napi::Object DoubleRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func = DefineClass(
      env, "DoubleRef",
      {InstanceAccessor<&DoubleRef::GetValue, &DoubleRef::SetValue>("value")});
  Napi::FunctionReference* constructor = new Napi::FunctionReference();

  *constructor = Napi::Persistent(func);

  exports.Set("DoubleRef", func);
  env.SetInstanceData<Napi::FunctionReference>(constructor);

  return exports;
}

DoubleRef::DoubleRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<DoubleRef>(info) {
  if (info.Length() > 0) {
    this->value = info[0].As<Napi::Number>().DoubleValue();
  }
}

double DoubleRef::Value() { return this->value; }

double* DoubleRef::Ptr() { return &this->value; }

Napi::Value DoubleRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), this->value);
}

void DoubleRef::SetValue(const Napi::CallbackInfo& info,
                         const Napi::Value& value) {
  this->value = value.As<Napi::Number>().DoubleValue();
}
