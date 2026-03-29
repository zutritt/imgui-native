#pragma once

#include <napi.h>

class CallbackRef : public Napi::ObjectWrap<CallbackRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  CallbackRef(const Napi::CallbackInfo& info);

  // Inline definition here so the body is visible in every translation unit
  // that calls this method. Defining inline functions in .cpp files is invalid.
  inline const Napi::FunctionReference& GetCallback() const {
    return this->callback;
  }

 private:
  Napi::FunctionReference callback;
};
