#include "layout.h"
#include "result.h"
#include <Python.h>
#include <capnp/any.h>
#include <capnp/message.h>
#include <capnp/serialize.h>
#include <cstring>
#include <exception>
#include <new>
extern "C" {
PyObject *result_tuple(Result);
int parse_car(PyObject *, Result *);
PyObject *one(PyObject *, PyObject *);
PyObject *write_car(PyObject *, PyObject *);
}
static PyObject *failure() {
  try {
    throw;
  } catch (const kj::Exception &e) {
    PyErr_SetString(PyExc_ValueError, e.getDescription().cStr());
  } catch (const std::bad_alloc &) {
    PyErr_NoMemory();
  } catch (const std::exception &e) {
    PyErr_SetString(PyExc_RuntimeError, e.what());
  } catch (...) {
    PyErr_SetString(PyExc_RuntimeError, "unknown native exception");
  }
  return nullptr;
}
static PyObject *read_library(PyObject *, PyObject *data) {
  if (!PyBytes_Check(data)) {
    PyErr_SetString(PyExc_TypeError, "bytes required");
    return nullptr;
  }
  size_t size = PyBytes_GET_SIZE(data);
  if (size % 8) {
    PyErr_SetString(PyExc_ValueError, "word-aligned framing required");
    return nullptr;
  }
  auto *bytes = PyBytes_AS_STRING(data);
  try {
    kj::Array<capnp::word> aligned;
    const capnp::word *words = reinterpret_cast<const capnp::word *>(bytes);
    if (reinterpret_cast<uintptr_t>(bytes) % 8) {
      aligned = kj::heapArray<capnp::word>(size / 8);
      memcpy(aligned.begin(), bytes, size);
      words = aligned.begin();
    }
    capnp::FlatArrayMessageReader reader(kj::arrayPtr(words, size / 8));
    if (reader.getEnd() != words + size / 8) {
      PyErr_SetString(PyExc_ValueError, "trailing bytes");
      return nullptr;
    }
    auto root = capnp::_::PointerHelpers<capnp::AnyPointer>::getInternalReader(
                    reader.getRoot<capnp::AnyPointer>())
                    .getStruct(nullptr);
    if (root.getDataField<uint16_t>(DISCRIMINANT_OFFSET / 2) !=
        CAR_DISCRIMINANT) {
      PyErr_SetString(PyExc_ValueError, "carState required");
      return nullptr;
    }
    auto car = root.getPointerField(CAR_POINTER).getStruct(nullptr);
    auto wheels = car.getPointerField(WHEEL_POINTER).getStruct(nullptr);
    Result out{root.getDataField<uint64_t>(TIME_OFFSET / 8, TIME_DEFAULT),
               car.getDataField<float>(SPEED_OFFSET / 4, SPEED_DEFAULT),
               car.getDataField<float>(ANGLE_OFFSET / 4, ANGLE_DEFAULT),
               wheels.getDataField<float>(WHEEL_OFFSET / 4, WHEEL_DEFAULT),
               root.getDataField<bool>(VALID_OFFSET, VALID_DEFAULT),
               car.getDataField<uint16_t>(GEAR_OFFSET / 2, GEAR_DEFAULT)};
    return result_tuple(out);
  } catch (...) {
    return failure();
  }
}
static void fill(capnp::MessageBuilder &builder, Result r) {
  auto root = capnp::_::PointerHelpers<capnp::AnyPointer>::getInternalBuilder(
                  builder.getRoot<capnp::AnyPointer>())
                  .initStruct(capnp::_::StructSize(EVENT_DATA, EVENT_POINTERS));
  root.setDataField<uint64_t>(TIME_OFFSET / 8, r.timestamp, TIME_DEFAULT);
  root.setDataField<bool>(VALID_OFFSET, r.valid, VALID_DEFAULT);
  root.setDataField<uint16_t>(DISCRIMINANT_OFFSET / 2, CAR_DISCRIMINANT);
  auto car = root.getPointerField(CAR_POINTER)
                 .initStruct(capnp::_::StructSize(CAR_DATA, CAR_POINTERS));
  car.setDataField<float>(SPEED_OFFSET / 4, r.speed, SPEED_DEFAULT);
  car.setDataField<float>(ANGLE_OFFSET / 4, r.angle, ANGLE_DEFAULT);
  car.setDataField<uint16_t>(GEAR_OFFSET / 2, r.gear, GEAR_DEFAULT);
  auto wheels =
      car.getPointerField(WHEEL_POINTER)
          .initStruct(capnp::_::StructSize(WHEELS_DATA, WHEELS_POINTERS));
  wheels.setDataField<float>(WHEEL_OFFSET / 4, r.wheel, WHEEL_DEFAULT);
}
static constexpr size_t WORDS = 1 + EVENT_DATA + EVENT_POINTERS + CAR_DATA +
                                CAR_POINTERS + WHEELS_DATA + WHEELS_POINTERS;
static PyObject *write_library_result(Result result) {
  try {
    capnp::MallocMessageBuilder builder(WORDS);
    fill(builder, result);
    auto words = capnp::messageToFlatArray(builder);
    return PyBytes_FromStringAndSize(
        reinterpret_cast<const char *>(words.begin()), words.size() * 8);
  } catch (...) {
    return failure();
  }
}
static PyObject *write_library(PyObject *, PyObject *arg) {
  Result result;
  if (!parse_car(arg, &result))
    return nullptr;
  return write_library_result(result);
}
static PyObject *write_library_flat(PyObject *, PyObject *arg) {
  Result result;
  if (!parse_car(arg, &result))
    return nullptr;
  PyObject *out = PyBytes_FromStringAndSize(nullptr, (WORDS + 1) * 8);
  if (!out)
    return nullptr;
  auto *bytes = PyBytes_AS_STRING(out);
  memset(bytes, 0, (WORDS + 1) * 8);
  // Same exact size knowledge as the direct writer; no allocation/copy after
  // the final bytes.
  for (size_t i = 0; i < 4; i++)
    bytes[4 + i] = (WORDS >> (i * 8)) & 255;
  try {
    if (reinterpret_cast<uintptr_t>(bytes) % 8) {
      Py_DECREF(out);
      return write_library_result(result);
    }
    capnp::FlatMessageBuilder builder(
        kj::arrayPtr(reinterpret_cast<capnp::word *>(bytes + 8), WORDS));
    fill(builder, result);
    builder.requireFilled();
    return out;
  } catch (...) {
    Py_DECREF(out);
    return failure();
  }
}
static PyMethodDef methods[] = {
    {"read_direct", one, METH_O, nullptr},
    {"read_library", read_library, METH_O, nullptr},
    {"write_direct", write_car, METH_O, nullptr},
    {"write_library", write_library, METH_O, nullptr},
    {"write_library_flat", write_library_flat, METH_O, nullptr},
    {nullptr, nullptr, 0, nullptr}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "library_control", nullptr,
                             -1, methods};
PyMODINIT_FUNC PyInit_library_control() { return PyModule_Create(&module); }
