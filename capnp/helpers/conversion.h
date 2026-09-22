#pragma once
#include <Python.h>
#include <capnp/dynamic.h>
#include <type_traits>

namespace pycapnp_conversion {
template <typename T> PyObject* primitiveList(capnp::DynamicList::Reader source) {
  auto values = source.as<capnp::List<T>>();
  PyObject* result = PyList_New(values.size());
  if (!result) return nullptr;
  try {
    for (unsigned i = 0; i < values.size(); ++i) {
      PyObject* value;
      if constexpr (std::is_same_v<T, bool>) value = PyBool_FromLong(values[i]);
      else if constexpr (std::is_floating_point_v<T>) value = PyFloat_FromDouble(values[i]);
      else if constexpr (std::is_signed_v<T>) value = PyLong_FromLongLong(values[i]);
      else value = PyLong_FromUnsignedLongLong(values[i]);
      if (!value) { Py_DECREF(result); return nullptr; }
      PyList_SET_ITEM(result, i, value);
    }
  } catch (...) {
    Py_DECREF(result);
    throw;
  }
  return result;
}
inline PyObject* primitiveList(capnp::DynamicList::Reader source) {
  switch (source.getSchema().getElementType().which()) {
    case capnp::schema::Type::BOOL: return primitiveList<bool>(source);
    case capnp::schema::Type::INT8: return primitiveList<int8_t>(source);
    case capnp::schema::Type::INT16: return primitiveList<int16_t>(source);
    case capnp::schema::Type::INT32: return primitiveList<int32_t>(source);
    case capnp::schema::Type::INT64: return primitiveList<int64_t>(source);
    case capnp::schema::Type::UINT8: return primitiveList<uint8_t>(source);
    case capnp::schema::Type::UINT16: return primitiveList<uint16_t>(source);
    case capnp::schema::Type::UINT32: return primitiveList<uint32_t>(source);
    case capnp::schema::Type::UINT64: return primitiveList<uint64_t>(source);
    case capnp::schema::Type::FLOAT32: return primitiveList<float>(source);
    case capnp::schema::Type::FLOAT64: return primitiveList<double>(source);
    default: return Py_NewRef(Py_None);
  }
}
}  // namespace pycapnp_conversion
