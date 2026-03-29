#include "string.h"

Napi::Object StringRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func = DefineClass(
      env, "StringRef",
      {InstanceMethod<&StringRef::Resize>("resize"),
       InstanceAccessor<&StringRef::GetValue, &StringRef::SetValue>("value")});
  Napi::FunctionReference* constructor = new Napi::FunctionReference();

  *constructor = Napi::Persistent(func);

  exports["StringRef"] = func;
  env.SetInstanceData<Napi::FunctionReference>(constructor);

  return exports;
}

StringRef::StringRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<StringRef>(info) {
  if (info.Length() > 0) {
    this->value = info[0].As<Napi::String>().Utf8Value();
  }
}

char* StringRef::Data() { return this->value.data(); }

size_t StringRef::Capacity() { return this->value.capacity(); }

Napi::Value StringRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::String::New(info.Env(), this->value);
}

void StringRef::SetValue(const Napi::CallbackInfo& info,
                         const Napi::Value& value) {
  this->value = value.As<Napi::String>().Utf8Value();
}

void StringRef::Resize(const Napi::CallbackInfo& info) {
  if (info.Length() == 0) {
    Napi::TypeError::New(info.Env(), "Expected at least 1 argument")
        .ThrowAsJavaScriptException();
  }

  if (info[0].IsBigInt()) {
    bool lossless;
    size_t newSize = info[0].As<Napi::BigInt>().Uint64Value(&lossless);

    this->value.resize(newSize);
    return;
  }

  if (info[0].IsNumber()) {
    size_t newSize = info[0].As<Napi::Number>().Uint32Value();

    this->value.resize(newSize);
    return;
  }

  Napi::TypeError::New(info.Env(), "Expected a number or bigint as argument")
      .ThrowAsJavaScriptException();
}
