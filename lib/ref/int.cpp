#include "int.h"

Napi::Object IntRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func = DefineClass(
      env, "IntRef",
      {InstanceAccessor<&IntRef::GetValue, &IntRef::SetValue>("value")});
  Napi::FunctionReference* constructor = new Napi::FunctionReference();

  *constructor = Napi::Persistent(func);

  exports.Set("IntRef", func);
  env.SetInstanceData<Napi::FunctionReference>(constructor);

  return exports;
}

IntRef::IntRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<IntRef>(info) {
  if (info.Length() > 0) {
    this->value = info[0].As<Napi::Number>().Int32Value();
  }
}

int32_t IntRef::Value() { return this->value; }

int32_t* IntRef::Ptr() { return &this->value; }

Napi::Value IntRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), this->value);
}

void IntRef::SetValue(const Napi::CallbackInfo& info,
                      const Napi::Value& value) {
  this->value = value.As<Napi::Number>().Int32Value();
}
