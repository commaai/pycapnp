#pragma once
#include <Python.h>
#include <cstring>
#include <capnp/dynamic.h>
#include <capnp/any.h>

namespace pycapnp_bulk {
inline capnp::DynamicStruct::Reader structReader(capnp::DynamicValue::Reader value) {
  return value.as<capnp::DynamicStruct>();
}
inline capnp::DynamicStruct::Builder structBuilder(capnp::DynamicValue::Builder value) {
  return value.as<capnp::DynamicStruct>();
}
inline capnp::DynamicList::Reader listReader(capnp::DynamicValue::Reader value) {
  return value.as<capnp::DynamicList>();
}
inline capnp::DynamicList::Builder listBuilder(capnp::DynamicValue::Builder value) {
  return value.as<capnp::DynamicList>();
}
inline PyObject* canFrame(capnp::DynamicStruct::Reader frame, capnp::StructSchema::Field address,
                          capnp::StructSchema::Field dat, capnp::StructSchema::Field src) {
  auto a = frame.get(address).as<uint32_t>();
  auto d = frame.get(dat).as<capnp::Data>();
  auto s = frame.get(src).as<uint8_t>();
  PyObject* data = PyBytes_FromStringAndSize(reinterpret_cast<const char*>(d.begin()), d.size());
  if (!data) return nullptr;
  PyObject* addr = PyLong_FromUnsignedLong(a);
  PyObject* source = PyLong_FromUnsignedLong(s);
  PyObject* result = PyTuple_New(3);
  if (!addr || !source || !result) {
    Py_XDECREF(addr); Py_XDECREF(source); Py_XDECREF(result); Py_DECREF(data);
    return nullptr;
  }
  PyTuple_SET_ITEM(result, 0, addr);
  PyTuple_SET_ITEM(result, 1, data);
  PyTuple_SET_ITEM(result, 2, source);
  return result;
}
template <typename T> PyObject* readFloats(capnp::DynamicList::Reader source) {
  auto values = source.as<capnp::List<T>>();
  PyObject* result = PyList_New(values.size());
  if (!result) return nullptr;
  for (unsigned i = 0; i < values.size(); ++i) {
    PyObject* value = PyFloat_FromDouble(values[i]);
    if (!value) { Py_DECREF(result); return nullptr; }
    PyList_SET_ITEM(result, i, value);
  }
  return result;
}
inline PyObject* floats(capnp::DynamicList::Reader source) {
  auto type = source.getSchema().getElementType();
  KJ_REQUIRE(type.isFloat32() || type.isFloat64(), "expected Float32 or Float64 list");
  return type.isFloat32() ? readFloats<float>(source) : readFloats<double>(source);
}
inline bool littleEndian() { unsigned short value = 1; return *reinterpret_cast<char*>(&value) == 1; }
inline const char* floatPointer(capnp::DynamicList::Reader source, size_t* size, bool* wide) {
  auto type = source.getSchema().getElementType();
  KJ_REQUIRE(type.isFloat32() || type.isFloat64(), "expected Float32 or Float64 list");
  *wide = type.isFloat64();
  capnp::AnyList::Reader raw = *wide ? capnp::AnyList::Reader(source.as<capnp::List<double>>())
                                    : capnp::AnyList::Reader(source.as<capnp::List<float>>());
  if (!littleEndian() || raw.getElementSize() != (*wide ? capnp::ElementSize::EIGHT_BYTES : capnp::ElementSize::FOUR_BYTES)) return nullptr;
  auto bytes = raw.getRawBytes();
  *size = source.size() * (*wide ? sizeof(double) : sizeof(float));
  if (bytes.size() != *size) return nullptr;
  return *size ? reinterpret_cast<const char*>(bytes.begin()) : "";
}
template <typename T> int writeFloats(capnp::DynamicList::Builder target, PyObject* source) {
  auto values = target.as<capnp::List<T>>();
  if (PyObject_CheckBuffer(source)) {
    Py_buffer buffer;
    if (PyObject_GetBuffer(source, &buffer, PyBUF_FORMAT | PyBUF_C_CONTIGUOUS) < 0) return -1;
    bool f32 = buffer.format && std::strcmp(buffer.format, "f") == 0 && buffer.itemsize == 4;
    bool f64 = buffer.format && std::strcmp(buffer.format, "d") == 0 && buffer.itemsize == 8;
    if ((!f32 && !f64) || buffer.ndim != 1 || buffer.len / buffer.itemsize != values.size()) {
      PyBuffer_Release(&buffer);
      PyErr_SetString(PyExc_ValueError, "expected matching one-dimensional native float buffer");
      return -1;
    }
    size_t rawSize = 0;
    bool wide = false;
    const char* raw = floatPointer(target.asReader(), &rawSize, &wide);
    if (raw && ((f32 && !wide) || (f64 && wide))) {
      std::memmove(const_cast<char*>(raw), buffer.buf, rawSize);
      PyBuffer_Release(&buffer);
      return 0;
    }
    // Differing-width views may alias target storage. Snapshot before conversion,
    // otherwise the first write can overwrite later source elements.
    PyObject* snapshot = PyBytes_FromStringAndSize(static_cast<const char*>(buffer.buf), buffer.len);
    PyBuffer_Release(&buffer);
    if (!snapshot) return -1;
    const char* data = PyBytes_AS_STRING(snapshot);
    for (unsigned i = 0; i < values.size(); ++i) {
      if (f32) { float value; std::memcpy(&value, data + i * 4, 4); values.set(i, static_cast<T>(value)); }
      else { double value; std::memcpy(&value, data + i * 8, 8); values.set(i, static_cast<T>(value)); }
    }
    Py_DECREF(snapshot);
    return 0;
  }
  PyObject* seq = PySequence_Tuple(source);
  if (!seq) return -1;
  if (PyTuple_GET_SIZE(seq) != values.size()) {
    Py_DECREF(seq); PyErr_SetString(PyExc_ValueError, "list length mismatch"); return -1;
  }
  for (unsigned i = 0; i < values.size(); ++i) {
    double value = PyFloat_AsDouble(PyTuple_GET_ITEM(seq, i));
    if (value == -1 && PyErr_Occurred()) { Py_DECREF(seq); return -1; }
    values.set(i, static_cast<T>(value));
  }
  Py_DECREF(seq);
  return 0;
}
template <typename T> PyObject* floatBytes(capnp::DynamicList::Reader source) {
  auto values = source.as<capnp::List<T>>();
  PyObject* result = PyBytes_FromStringAndSize(nullptr, values.size() * sizeof(T));
  if (!result) return nullptr;
  char* data = PyBytes_AS_STRING(result);
  for (unsigned i = 0; i < values.size(); ++i) {
    T value = values[i];
    std::memcpy(data + i * sizeof(T), &value, sizeof(T));
  }
  return result;
}
inline PyObject* floatBuffer(capnp::DynamicList::Reader source) {
  auto type = source.getSchema().getElementType();
  KJ_REQUIRE(type.isFloat32() || type.isFloat64(), "expected Float32 or Float64 list");
  PyObject* bytes = type.isFloat32() ? floatBytes<float>(source) : floatBytes<double>(source);
  if (!bytes) return nullptr;
  PyObject* view = PyMemoryView_FromObject(bytes);
  Py_DECREF(bytes);
  if (!view) return nullptr;
  PyObject* result = PyObject_CallMethod(view, "cast", "s", type.isFloat32() ? "f" : "d");
  Py_DECREF(view);
  return result;
}
inline PyObject* setFloats(capnp::DynamicList::Builder target, PyObject* source) {
  auto type = target.getSchema().getElementType();
  KJ_REQUIRE(type.isFloat32() || type.isFloat64(), "expected Float32 or Float64 list");
  int status = type.isFloat32() ? writeFloats<float>(target, source) : writeFloats<double>(target, source);
  if (status < 0) return nullptr;
  Py_RETURN_NONE;
}
}
