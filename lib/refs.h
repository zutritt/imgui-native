#pragma once
#include <napi.h>

class BoolRef : public Napi::ObjectWrap<BoolRef> {
public:
  static Napi::FunctionReference constructor;
  bool value;
  bool* Ptr() { return &value; }
  BoolRef(const Napi::CallbackInfo& info);
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
private:
  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& val);
};

class IntRef : public Napi::ObjectWrap<IntRef> {
public:
  static Napi::FunctionReference constructor;
  int value;
  int* Ptr() { return &value; }
  IntRef(const Napi::CallbackInfo& info);
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
private:
  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& val);
};

class FloatRef : public Napi::ObjectWrap<FloatRef> {
public:
  static Napi::FunctionReference constructor;
  float value;
  float* Ptr() { return &value; }
  FloatRef(const Napi::CallbackInfo& info);
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
private:
  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& val);
};

class DoubleRef : public Napi::ObjectWrap<DoubleRef> {
public:
  static Napi::FunctionReference constructor;
  double value;
  double* Ptr() { return &value; }
  DoubleRef(const Napi::CallbackInfo& info);
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
private:
  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& val);
};

class StringRef : public Napi::ObjectWrap<StringRef> {
public:
  static Napi::FunctionReference constructor;
  std::string buffer;
  char* Data() { return buffer.data(); }
  size_t Size() const { return buffer.size(); }
  StringRef(const Napi::CallbackInfo& info);
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
private:
  Napi::Value GetValue(const Napi::CallbackInfo& info);
  void SetValue(const Napi::CallbackInfo& info, const Napi::Value& val);
};

void InitRefs(Napi::Env env, Napi::Object exports);
