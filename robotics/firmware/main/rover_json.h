#pragma once
// Minimal JSON codec for the rover serial protocol.
// Pure C++17, no exceptions, no heap-heavy DOM beyond what messages need.
// Supports the full JSON grammar on parse; serialize covers objects,
// arrays, strings, numbers, bools, null.

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace rover::json {

struct Value {
  enum class Type : uint8_t { kNull, kBool, kNumber, kString, kArray, kObject };

  Type type = Type::kNull;
  bool boolean = false;
  double number = 0.0;
  std::string str;
  std::vector<Value> array;
  std::vector<std::pair<std::string, Value>> object;

  static Value makeNull() { return {}; }
  static Value makeBool(bool b) { Value v; v.type = Type::kBool; v.boolean = b; return v; }
  static Value makeNumber(double n) { Value v; v.type = Type::kNumber; v.number = n; return v; }
  static Value makeString(std::string s) { Value v; v.type = Type::kString; v.str = std::move(s); return v; }
  static Value makeArray() { Value v; v.type = Type::kArray; return v; }
  static Value makeObject() { Value v; v.type = Type::kObject; return v; }

  void set(const char* key, Value v);
  const Value* find(const char* key) const;
  bool isNull() const { return type == Type::kNull; }
  double asNumber(double fallback = 0.0) const { return type == Type::kNumber ? number : fallback; }
  bool asBool(bool fallback = false) const { return type == Type::kBool ? boolean : fallback; }
  const std::string& asString() const { return str; }
};

// Parses a complete JSON document. Returns false on malformed input.
bool parse(const std::string& text, Value& out, size_t* errorPos = nullptr);

// Serializes compact JSON (no whitespace). Numbers that are integral print
// without a decimal point.
std::string serialize(const Value& v);

} // namespace rover::json
