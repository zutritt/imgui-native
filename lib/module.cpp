#include <napi.h>
#include "dcimgui.h"
#include "imgui.h"

#include "types.h"
#include "types.cpp"
#include "refs.h"
#include "refs.cpp"
#include "gen/napi/callbacks.cpp"
#include "gen/napi/structs.h"
#include "gen/napi/structs.cpp"
#include "gen/napi/functions.cpp"
#include "gen/napi/enums.cpp"

Napi::Object Init(Napi::Env env, Napi::Object exports)
{
  InitRefs(env, exports);
  InitStructs(env, exports);
  InitFunctions(env, exports);
  InitEnums(env, exports);
  return exports;
}

NODE_API_MODULE(addon, Init)
