#pragma once
#include <Python.h>

typedef PyObject* (*CapnpGetAttr)(PyObject*, PyObject*);

inline CapnpGetAttr installCapnpGetAttr(PyObject* type, CapnpGetAttr getter) {
  auto* tp = reinterpret_cast<PyTypeObject*>(type);
  auto original = tp->tp_getattro;
  tp->tp_getattro = getter;
  PyType_Modified(tp);
  return original;
}

// This private CPython API is version-gated. Unsupported interpreters retain
// Cython's original attribute slot and never call the fallback helper.
inline bool supportsCapnpFastGetAttr() {
#if !defined(PYPY_VERSION) && !defined(Py_LIMITED_API) && !defined(Py_GIL_DISABLED) && PY_VERSION_HEX >= 0x030C0000 && PY_VERSION_HEX < 0x030F0000
  return true;
#else
  return false;
#endif
}
inline PyObject* optionalCapnpGetAttr(PyObject* obj, PyObject* name) {
#if !defined(PYPY_VERSION) && !defined(Py_LIMITED_API) && !defined(Py_GIL_DISABLED) && PY_VERSION_HEX >= 0x030C0000 && PY_VERSION_HEX < 0x030F0000
  return _PyObject_GenericGetAttrWithDict(obj, name, nullptr, 1);
#else
  return PyObject_GenericGetAttr(obj, name);
#endif
}
