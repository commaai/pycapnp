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
