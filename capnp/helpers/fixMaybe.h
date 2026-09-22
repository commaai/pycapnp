#include "kj/common.h"
#include <stdexcept>

template<typename T>
T fixMaybe(::kj::Maybe<T> val) {
  KJ_IF_MAYBE(new_val, val) {
    return *new_val;
  } else {
    throw std::invalid_argument("Member was null.");
  }
}

inline bool tryWhich(::capnp::DynamicStruct::Reader reader, ::capnp::StructSchema::Field* field) {
  KJ_IF_MAYBE(value, reader.which()) {
    *field = *value;
    return true;
  }
  return false;
}
