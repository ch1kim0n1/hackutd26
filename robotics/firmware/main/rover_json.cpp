#include "rover_json.h"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace rover::json {

void Value::set(const char* key, Value v) {
  if (type != Type::kObject) {
    type = Type::kObject;
    object.clear();
  }
  for (auto& kv : object) {
    if (kv.first == key) { kv.second = std::move(v); return; }
  }
  object.emplace_back(key, std::move(v));
}

const Value* Value::find(const char* key) const {
  if (type != Type::kObject) return nullptr;
  for (const auto& kv : object) {
    if (kv.first == key) return &kv.second;
  }
  return nullptr;
}

namespace {

struct Parser {
  const char* p;
  const char* end;
  size_t pos = 0;
  bool ok = true;

  explicit Parser(const std::string& s) : p(s.data()), end(s.data() + s.size()) {}

  char peek() const { return p < end ? *p : '\0'; }
  char get() { return p < end ? *p++ : '\0'; }
  bool consume(char c) { if (peek() == c) { ++p; return true; } return false; }
  void ws() { while (p < end && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) ++p; }

  bool literal(const char* word) {
    size_t n = std::strlen(word);
    if (static_cast<size_t>(end - p) < n || std::strncmp(p, word, n) != 0) return false;
    p += n;
    return true;
  }

  bool parseString(std::string& out) {
    if (!consume('"')) return false;
    out.clear();
    while (p < end) {
      char c = get();
      if (c == '"') return true;
      if (c == '\\') {
        if (p >= end) return false;
        char e = get();
        switch (e) {
          case '"': out += '"'; break;
          case '\\': out += '\\'; break;
          case '/': out += '/'; break;
          case 'b': out += '\b'; break;
          case 'f': out += '\f'; break;
          case 'n': out += '\n'; break;
          case 'r': out += '\r'; break;
          case 't': out += '\t'; break;
          case 'u': {
            // Decode \uXXXX (BMP only; surrogates -> U+FFFD).
            if (end - p < 4) return false;
            unsigned cp = 0;
            for (int i = 0; i < 4; ++i) {
              char h = get();
              cp <<= 4;
              if (h >= '0' && h <= '9') cp += h - '0';
              else if (h >= 'a' && h <= 'f') cp += h - 'a' + 10;
              else if (h >= 'A' && h <= 'F') cp += h - 'A' + 10;
              else return false;
            }
            if (cp >= 0xD800 && cp <= 0xDFFF) cp = 0xFFFD;
            if (cp < 0x80) {
              out += static_cast<char>(cp);
            } else if (cp < 0x800) {
              out += static_cast<char>(0xC0 | (cp >> 6));
              out += static_cast<char>(0x80 | (cp & 0x3F));
            } else {
              out += static_cast<char>(0xE0 | (cp >> 12));
              out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
              out += static_cast<char>(0x80 | (cp & 0x3F));
            }
            break;
          }
          default: return false;
        }
      } else {
        if (static_cast<unsigned char>(c) < 0x20) return false; // raw control chars illegal
        out += c;
      }
    }
    return false;
  }

  bool parseNumber(double& out) {
    const char* start = p;
    if (peek() == '-') ++p;
    if (peek() == '0') {
      ++p;
    } else if (peek() >= '1' && peek() <= '9') {
      while (peek() >= '0' && peek() <= '9') ++p;
    } else {
      return false;
    }
    if (peek() == '.') {
      ++p;
      if (!(peek() >= '0' && peek() <= '9')) return false;
      while (peek() >= '0' && peek() <= '9') ++p;
    }
    if (peek() == 'e' || peek() == 'E') {
      ++p;
      if (peek() == '+' || peek() == '-') ++p;
      if (!(peek() >= '0' && peek() <= '9')) return false;
      while (peek() >= '0' && peek() <= '9') ++p;
    }
    out = std::strtod(std::string(start, p - start).c_str(), nullptr);
    return true;
  }

  bool parseValue(Value& out) {
    ws();
    switch (peek()) {
      case 'n': if (literal("null")) { out = Value::makeNull(); return true; } return false;
      case 't': if (literal("true")) { out = Value::makeBool(true); return true; } return false;
      case 'f': if (literal("false")) { out = Value::makeBool(false); return true; } return false;
      case '"': { std::string s; if (!parseString(s)) return false; out = Value::makeString(std::move(s)); return true; }
      case '[': {
        ++p; out = Value::makeArray(); ws();
        if (consume(']')) return true;
        while (true) {
          Value item;
          if (!parseValue(item)) return false;
          out.array.push_back(std::move(item));
          ws();
          if (consume(']')) return true;
          if (!consume(',')) return false;
        }
      }
      case '{': {
        ++p; out = Value::makeObject(); ws();
        if (consume('}')) return true;
        while (true) {
          ws();
          std::string key;
          if (!parseString(key)) return false;
          ws();
          if (!consume(':')) return false;
          Value val;
          if (!parseValue(val)) return false;
          out.set(key.c_str(), std::move(val));
          ws();
          if (consume('}')) return true;
          if (!consume(',')) return false;
        }
      }
      default:
        if (peek() == '-' || (peek() >= '0' && peek() <= '9')) {
          double n;
          if (!parseNumber(n)) return false;
          out = Value::makeNumber(n);
          return true;
        }
        return false;
    }
  }
};

void serializeInto(const Value& v, std::string& out) {
  switch (v.type) {
    case Value::Type::kNull: out += "null"; break;
    case Value::Type::kBool: out += v.boolean ? "true" : "false"; break;
    case Value::Type::kNumber: {
      char buf[32];
      double ip;
      if (std::modf(v.number, &ip) == 0.0 && v.number >= -9007199254740992.0 &&
          v.number <= 9007199254740992.0) {
        std::snprintf(buf, sizeof(buf), "%lld", static_cast<long long>(v.number));
      } else {
        std::snprintf(buf, sizeof(buf), "%.9g", v.number);
      }
      out += buf;
      break;
    }
    case Value::Type::kString: {
      out += '"';
      for (char c : v.str) {
        switch (c) {
          case '"': out += "\\\""; break;
          case '\\': out += "\\\\"; break;
          case '\b': out += "\\b"; break;
          case '\f': out += "\\f"; break;
          case '\n': out += "\\n"; break;
          case '\r': out += "\\r"; break;
          case '\t': out += "\\t"; break;
          default:
            if (static_cast<unsigned char>(c) < 0x20) {
              char esc[8];
              std::snprintf(esc, sizeof(esc), "\\u%04x", c);
              out += esc;
            } else {
              out += c;
            }
        }
      }
      out += '"';
      break;
    }
    case Value::Type::kArray:
      out += '[';
      for (size_t i = 0; i < v.array.size(); ++i) {
        if (i) out += ',';
        serializeInto(v.array[i], out);
      }
      out += ']';
      break;
    case Value::Type::kObject:
      out += '{';
      for (size_t i = 0; i < v.object.size(); ++i) {
        if (i) out += ',';
        serializeInto(Value::makeString(v.object[i].first), out);
        out += ':';
        serializeInto(v.object[i].second, out);
      }
      out += '}';
      break;
  }
}

} // namespace

bool parse(const std::string& text, Value& out, size_t* errorPos) {
  Parser p(text);
  p.ws();
  if (!p.parseValue(out)) {
    if (errorPos) *errorPos = static_cast<size_t>(p.p - text.data());
    return false;
  }
  p.ws();
  if (p.p != p.end) {
    if (errorPos) *errorPos = static_cast<size_t>(p.p - text.data());
    return false;
  }
  return true;
}

std::string serialize(const Value& v) {
  std::string out;
  out.reserve(128);
  serializeInto(v, out);
  return out;
}

} // namespace rover::json
