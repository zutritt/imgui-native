#pragma once

#include <napi.h>

class CallbackRef : public Napi::ObjectWrap<CallbackRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  CallbackRef(const Napi::CallbackInfo& info);

  inline const Napi::FunctionReference& GetCallback() const;

 private:
  Napi::FunctionReference callback;
};
