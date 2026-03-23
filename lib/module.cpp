#include <napi.h>
#include "gen/napi/enums.cpp"

Napi::Object Init(Napi::Env env, Napi::Object exports)
{
  InitEnums(env, exports);
  return exports;
}

NODE_API_MODULE(addon, Init)
