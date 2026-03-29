#pragma once
#include <napi.h>

#include <string>
#include <vector>

class StringListRef : public Napi::ObjectWrap<StringListRef> {
 public:
  static Napi::Object Init(Napi::Env env, Napi::Object exports);
  StringListRef(const Napi::CallbackInfo& info);

  const char* const* Data() const {
    return ptrs_.empty() ? nullptr : ptrs_.data();
  }
  int Count() const { return static_cast<int>(strings_.size()); }

 private:
  std::vector<std::string> strings_;
  std::vector<const char*> ptrs_;

  void RebuildPtrs();
  void LoadFromJsArray(const Napi::Array& arr);

  Napi::Value GetCount(const Napi::CallbackInfo& info);
  Napi::Value Update(const Napi::CallbackInfo& info);
};
