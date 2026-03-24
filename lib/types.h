#pragma once
#include <napi.h>
#include "dcimgui.h"

ImVec2 ExtractImVec2(const Napi::Value& v);
ImVec4 ExtractImVec4(const Napi::Value& v);
ImColor ExtractImColor(const Napi::Value& v);
ImTextureRef ExtractImTextureRef(const Napi::Value& v);
