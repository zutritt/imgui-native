#include "bool.h"

Napi::Object BoolRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func = DefineClass(
      env, "BoolRef",
      {InstanceAccessor<&BoolRef::GetValue, &BoolRef::SetValue>("value")});
  Napi::FunctionReference* constructor = new Napi::FunctionReference();

  *constructor = Napi::Persistent(func);

  exports.Set("BoolRef", func);
  env.SetInstanceData<Napi::FunctionReference>(constructor);

  return exports;
}

BoolRef::BoolRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<BoolRef>(info) {
  if (info.Length() > 0) {
    this->value = info[0].As<Napi::Boolean>().Value();
  }
}

bool BoolRef::Value() { return this->value; }

bool* BoolRef::Ptr() { return &this->value; }

Napi::Value BoolRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Boolean::New(info.Env(), this->value);
}

void BoolRef::SetValue(const Napi::CallbackInfo& info,
                       const Napi::Value& value) {
  this->value = value.As<Napi::Boolean>().Value();
}
