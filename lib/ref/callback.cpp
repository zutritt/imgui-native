#include "callback.h"

Napi::Object CallbackRef::Init(Napi::Env env, Napi::Object exports) {
  Napi::Function func = DefineClass(env, "CallbackRef", {});
  Napi::FunctionReference* constructor = new Napi::FunctionReference();

  *constructor = Napi::Persistent(func);

  exports["CallbackRef"] = func;
  env.SetInstanceData<Napi::FunctionReference>(constructor);

  return exports;
}

CallbackRef::CallbackRef(const Napi::CallbackInfo& info)
    : Napi::ObjectWrap<CallbackRef>(info) {
  if (info.Length() > 0) {
    this->callback = Napi::Persistent(info[0].As<Napi::Function>());
  }
}
