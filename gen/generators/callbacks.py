from builders.cpp import CppFile
from config import GEN_NAPI

_HEADER = """struct CallbackContext {
  Napi::FunctionReference func;
  Napi::Env env;
  std::string lastString;
  CallbackContext(Napi::Env e, Napi::Function f)
    : func(Napi::Persistent(f)), env(e) {}
};

static const char* TrampolineStringGetter(void* user_data, int idx) {
  auto* ctx = static_cast<CallbackContext*>(user_data);
  Napi::Value r = ctx->func.Call({Napi::Number::New(ctx->env, idx)});
  ctx->lastString = r.As<Napi::String>().Utf8Value();
  return ctx->lastString.c_str();
}

static bool TrampolineBoolGetter(void* user_data, int idx) {
  auto* ctx = static_cast<CallbackContext*>(user_data);
  Napi::Value r = ctx->func.Call({Napi::Number::New(ctx->env, idx)});
  return r.As<Napi::Boolean>().Value();
}

static void TrampolineVoidCallback(void* user_data) {
  auto* ctx = static_cast<CallbackContext*>(user_data);
  ctx->func.Call({});
}"""


def generate_callbacks(registry):
    f = CppFile()
    f.include('napi.h')
    f.blank()
    f.raw(_HEADER)
    (GEN_NAPI / 'callbacks.cpp').write_text(f.render())
