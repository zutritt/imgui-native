#include <napi.h>

#include "ref/bool.h"
#include "ref/callback.h"
#include "ref/double.h"
#include "ref/float.h"
#include "ref/int.h"
#include "ref/string.h"

void (*callback)(void* userData, int param) = nullptr;
void* userData = nullptr;

Napi::Object Init(Napi::Env env, Napi::Object exports) {
  BoolRef::Init(env, exports);
  IntRef::Init(env, exports);
  FloatRef::Init(env, exports);
  DoubleRef::Init(env, exports);
  StringRef::Init(env, exports);
  CallbackRef::Init(env, exports);

  exports["setCallback"] =
      Napi::Function::New(env, [](const Napi::CallbackInfo& info) {
        Napi::Env env = info.Env();

        Napi::ObjectReference* callbackRefRef = new Napi::ObjectReference();
        *callbackRefRef = Napi::Persistent(info[0].As<Napi::Object>());

        if (userData != nullptr) {
          delete static_cast<Napi::ObjectReference*>(userData);
        }

        userData = callbackRefRef;
        callback = [](void* userData, int someVar) {
          printf("[C++] Callback called with someVar=%d\n", someVar);

          Napi::ObjectReference* callbackRefRef =
              static_cast<Napi::ObjectReference*>(userData);

          CallbackRef* callbackRef =
              CallbackRef::Unwrap(callbackRefRef->Value());

          Napi::Env env = callbackRef->Env();
          Napi::HandleScope scope(env);

          callbackRef->GetCallback().Call({Napi::Number::New(env, someVar)});
        };

        return env.Null();
      });

  exports["callCallback"] =
      Napi::Function::New(env, [](const Napi::CallbackInfo& info) {
        Napi::Env env = info.Env();

        if (callback) {
          printf("[C++] Calling callback from C++\n");
          callback(userData, 42);
        }

        return env.Null();
      });

  return exports;
}

NODE_API_MODULE(addon, Init)
