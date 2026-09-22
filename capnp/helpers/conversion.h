#pragma once
#include <Python.h>
#include <capnp/dynamic.h>
#include <type_traits>
#include <limits>

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
template <typename T> bool fillPrimitive(capnp::DynamicList::Builder target, PyObject* source) {
  auto values = target.as<capnp::List<T>>();
  for (unsigned i = 0; i < values.size(); ++i) {
    PyObject* item = PySequence_Fast_GET_ITEM(source, i);
    T value;
    if constexpr (std::is_same_v<T, bool>) {
      if (!PyBool_Check(item)) return false;
      value = item == Py_True;
    } else if constexpr (std::is_floating_point_v<T>) {
      if (!PyFloat_CheckExact(item)) return false;
      value = static_cast<T>(PyFloat_AS_DOUBLE(item));
    } else if constexpr (std::is_signed_v<T>) {
      if (!PyLong_CheckExact(item)) return false;
      auto wide = PyLong_AsLongLong(item);
      if (wide == -1 && PyErr_Occurred()) { PyErr_Clear(); return false; }
      if (wide < std::numeric_limits<T>::min() || wide > std::numeric_limits<T>::max()) return false;
      value = static_cast<T>(wide);
    } else {
      if (!PyLong_CheckExact(item)) return false;
      auto wide = PyLong_AsUnsignedLongLong(item);
      if (wide == static_cast<unsigned long long>(-1) && PyErr_Occurred()) { PyErr_Clear(); return false; }
      if (wide > std::numeric_limits<T>::max()) return false;
      value = static_cast<T>(wide);
    }
    values.set(i, value);
  }
  return true;
}
inline bool fillPrimitive(capnp::DynamicList::Builder target, PyObject* source) {
  // Only exact built-in sequences reach this internal helper. On a coercion or
  // range mismatch, the existing dynamic setter repeats the valid prefix and
  // preserves its original conversion rules, partial-write behavior, and error.
  KJ_REQUIRE((PyList_CheckExact(source) || PyTuple_CheckExact(source)) &&
             PySequence_Fast_GET_SIZE(source) == target.size(), "invalid primitive input");
  switch (target.getSchema().getElementType().which()) {
    case capnp::schema::Type::BOOL: return fillPrimitive<bool>(target, source);
    case capnp::schema::Type::INT8: return fillPrimitive<int8_t>(target, source);
    case capnp::schema::Type::INT16: return fillPrimitive<int16_t>(target, source);
    case capnp::schema::Type::INT32: return fillPrimitive<int32_t>(target, source);
    case capnp::schema::Type::INT64: return fillPrimitive<int64_t>(target, source);
    case capnp::schema::Type::UINT8: return fillPrimitive<uint8_t>(target, source);
    case capnp::schema::Type::UINT16: return fillPrimitive<uint16_t>(target, source);
    case capnp::schema::Type::UINT32: return fillPrimitive<uint32_t>(target, source);
    case capnp::schema::Type::UINT64: return fillPrimitive<uint64_t>(target, source);
    case capnp::schema::Type::FLOAT32: return fillPrimitive<float>(target, source);
    case capnp::schema::Type::FLOAT64: return fillPrimitive<double>(target, source);
    default: return false;
  }
}
}  // namespace pycapnp_conversion
