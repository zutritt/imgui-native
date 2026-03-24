#include "refs.h"
#include <string>

Napi::FunctionReference BoolRef::constructor;
Napi::FunctionReference IntRef::constructor;
Napi::FunctionReference FloatRef::constructor;
Napi::FunctionReference DoubleRef::constructor;
Napi::FunctionReference StringRef::constructor;

BoolRef::BoolRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap<BoolRef>(info) {
  value = info.Length() > 0 ? info[0].As<Napi::Boolean>().Value() : false;
}
Napi::Value BoolRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Boolean::New(info.Env(), value);
}
void BoolRef::SetValue(const Napi::CallbackInfo& info, const Napi::Value& val) {
  value = val.As<Napi::Boolean>().Value();
}
Napi::Object BoolRef::Init(Napi::Env env, Napi::Object exports) {
  auto fn = DefineClass(env, "BoolRef", {
    InstanceAccessor<&BoolRef::GetValue, &BoolRef::SetValue>("value"),
  });
  constructor = Napi::Persistent(fn);
  constructor.SuppressDestruct();
  exports.Set("BoolRef", fn);
  return exports;
}

IntRef::IntRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap<IntRef>(info) {
  value = info.Length() > 0 ? info[0].As<Napi::Number>().Int32Value() : 0;
}
Napi::Value IntRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), value);
}
void IntRef::SetValue(const Napi::CallbackInfo& info, const Napi::Value& val) {
  value = val.As<Napi::Number>().Int32Value();
}
Napi::Object IntRef::Init(Napi::Env env, Napi::Object exports) {
  auto fn = DefineClass(env, "IntRef", {
    InstanceAccessor<&IntRef::GetValue, &IntRef::SetValue>("value"),
  });
  constructor = Napi::Persistent(fn);
  constructor.SuppressDestruct();
  exports.Set("IntRef", fn);
  return exports;
}

FloatRef::FloatRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap<FloatRef>(info) {
  value = info.Length() > 0 ? info[0].As<Napi::Number>().FloatValue() : 0.0f;
}
Napi::Value FloatRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), value);
}
void FloatRef::SetValue(const Napi::CallbackInfo& info, const Napi::Value& val) {
  value = val.As<Napi::Number>().FloatValue();
}
Napi::Object FloatRef::Init(Napi::Env env, Napi::Object exports) {
  auto fn = DefineClass(env, "FloatRef", {
    InstanceAccessor<&FloatRef::GetValue, &FloatRef::SetValue>("value"),
  });
  constructor = Napi::Persistent(fn);
  constructor.SuppressDestruct();
  exports.Set("FloatRef", fn);
  return exports;
}

DoubleRef::DoubleRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap<DoubleRef>(info) {
  value = info.Length() > 0 ? info[0].As<Napi::Number>().DoubleValue() : 0.0;
}
Napi::Value DoubleRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::Number::New(info.Env(), value);
}
void DoubleRef::SetValue(const Napi::CallbackInfo& info, const Napi::Value& val) {
  value = val.As<Napi::Number>().DoubleValue();
}
Napi::Object DoubleRef::Init(Napi::Env env, Napi::Object exports) {
  auto fn = DefineClass(env, "DoubleRef", {
    InstanceAccessor<&DoubleRef::GetValue, &DoubleRef::SetValue>("value"),
  });
  constructor = Napi::Persistent(fn);
  constructor.SuppressDestruct();
  exports.Set("DoubleRef", fn);
  return exports;
}

StringRef::StringRef(const Napi::CallbackInfo& info) : Napi::ObjectWrap<StringRef>(info) {
  size_t sz = info.Length() > 0 ? (size_t)info[0].As<Napi::Number>().Uint32Value() : 256;
  buffer.resize(sz, '\0');
}
Napi::Value StringRef::GetValue(const Napi::CallbackInfo& info) {
  return Napi::String::New(info.Env(), buffer.c_str());
}
void StringRef::SetValue(const Napi::CallbackInfo& info, const Napi::Value& val) {
  std::string s = val.As<Napi::String>().Utf8Value();
  size_t n = std::min(s.size(), buffer.size() - 1);
  memcpy(buffer.data(), s.data(), n);
  buffer[n] = '\0';
}
Napi::Object StringRef::Init(Napi::Env env, Napi::Object exports) {
  auto fn = DefineClass(env, "StringRef", {
    InstanceAccessor<&StringRef::GetValue, &StringRef::SetValue>("value"),
  });
  constructor = Napi::Persistent(fn);
  constructor.SuppressDestruct();
  exports.Set("StringRef", fn);
  return exports;
}

void InitRefs(Napi::Env env, Napi::Object exports) {
  BoolRef::Init(env, exports);
  IntRef::Init(env, exports);
  FloatRef::Init(env, exports);
  DoubleRef::Init(env, exports);
  StringRef::Init(env, exports);
}
