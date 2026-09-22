#pragma once
#include <Python.h>

typedef PyObject* (*CapnpGetAttr)(PyObject*, PyObject*);

// Keep private APIs and direct type-slot access out of unsupported builds.
// Current Cython is single-interpreter; future per-module state must not share
// these process-global callback slots.
#if !defined(PYPY_VERSION) && !defined(Py_LIMITED_API) && !defined(Py_GIL_DISABLED) && \
    (!defined(CYTHON_USE_MODULE_STATE) || !CYTHON_USE_MODULE_STATE) && \
    PY_VERSION_HEX >= 0x030C0000 && PY_VERSION_HEX < 0x030F0000
#define PYCAPNP_FAST_ATTR_SUPPORTED 1
#else
#define PYCAPNP_FAST_ATTR_SUPPORTED 0
#endif

inline bool supportsCapnpFastGetAttr() { return PYCAPNP_FAST_ATTR_SUPPORTED; }

#if PYCAPNP_FAST_ATTR_SUPPORTED
inline PyObject* optionalCapnpGetAttr(PyObject* obj, PyObject* name) {
  return _PyObject_GenericGetAttrWithDict(obj, name, nullptr, 1);
}

// Separate reader/builder slots keep the successful method/descriptor path in
// native code. Only missing schema fields enter Cython, avoiding its object
// return/refcount machinery on every _get_by_field/_set_by_field method lookup.
// Installation runs once per type during the GIL-held extension initialization;
// the extension's module state owns both types and the Cython callbacks.
template <unsigned Kind> struct CapnpAttributeSlot {
  inline static PyTypeObject* exactType = nullptr;
  inline static CapnpGetAttr original = nullptr;
  inline static CapnpGetAttr missingField = nullptr;

  static PyObject* get(PyObject* obj, PyObject* name) {
    // Delegate before looking up subclass descriptors: a descriptor may have
    // observable side effects, including raising AttributeError.
    if (Py_TYPE(obj) != exactType) return original(obj, name);
    PyObject* result = optionalCapnpGetAttr(obj, name);
    if (result != nullptr || PyErr_Occurred() != nullptr) return result;
    return missingField(obj, name);
  }

  static void install(PyObject* type, CapnpGetAttr fallback) {
    auto* requestedType = reinterpret_cast<PyTypeObject*>(type);
    if (exactType == requestedType && requestedType->tp_getattro == get) {
      missingField = fallback;
      return;
    }
    exactType = requestedType;
    original = exactType->tp_getattro;
    missingField = fallback;
    exactType->tp_getattro = get;
    PyType_Modified(exactType);
  }
};

inline void installCapnpReaderGetAttr(PyObject* type, CapnpGetAttr fallback) {
  CapnpAttributeSlot<0>::install(type, fallback);
}
inline void installCapnpBuilderGetAttr(PyObject* type, CapnpGetAttr fallback) {
  CapnpAttributeSlot<1>::install(type, fallback);
}

#else
inline void installCapnpReaderGetAttr(PyObject*, CapnpGetAttr) {}
inline void installCapnpBuilderGetAttr(PyObject*, CapnpGetAttr) {}
#endif
#undef PYCAPNP_FAST_ATTR_SUPPORTED
