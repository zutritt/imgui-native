#include "float.h"

Napi::Object FloatRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func = DefineClass(
      env, "FloatRef",
      {InstanceAccessor<&FloatRef::GetValue, &FloatRef::SetValue>("value")});
  Napi::FunctionReference* constructor = new Napi::FunctionReference();

  *constructor = Napi::Persistent(func);

  exports.Set("FloatRef", func);
  env.SetInstanceData<Napi::FunctionReference>(constructor);

  return exports;
}

FloatRef::FloatRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<FloatRef>(info) {
  if (info.Length() > 0) {
    this->value = info[0].As<Napi::Number>().FloatValue();
  }
}

float FloatRef::Value() { return this->value; }

float* FloatRef::Ptr() { return &this->value; }

Napi::Value FloatRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), this->value);
}

void FloatRef::SetValue(const Napi::CallbackInfo& info,
                        const Napi::Value& value) {
  this->value = value.As<Napi::Number>().FloatValue();
}
