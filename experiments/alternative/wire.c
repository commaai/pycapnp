/* Experimental bounded-depth CarState projection, little-endian wire encoding.
 */
#define PY_SSIZE_T_CLEAN
#include "layout.h"
#include "result.h"
#include <Python.h>
#include <stdint.h>
#include <string.h>
typedef struct {
  const unsigned char *p;
  size_t n;
} Segment;
typedef struct {
  Segment segments[512];
  size_t count, budget;
  const unsigned char *raw;
} Message;
typedef struct {
  Segment seg;
  size_t start, data, pointers;
} Struct;
static uint64_t load(const unsigned char *p, size_t n) {
  uint64_t v = 0;
  for (size_t i = 0; i < n; i++)
    v |= (uint64_t)p[i] << (8 * i);
  return v;
}
static int framing(const unsigned char *p, size_t n, Message *m) {
  if (n < 8)
    return 0;
  uint64_t count = load(p, 4) + 1;
  if (count > (n - 4) / 4)
    return 0;
  size_t at = ((count + 2) & ~(size_t)1) * 4;
  if (at > n)
    return 0;
  m->count = count;
  m->raw = p;
  m->budget = 8 * 1024 * 1024;
  for (size_t i = 0; i < count; i++) {
    uint64_t len = load(p + 4 + 4 * i, 4) * 8;
    if (len > n - at)
      return 0;
    if (i < 512)
      m->segments[i] = (Segment){p + at, len};
    at += len;
  }
  return at == n;
}
static Segment segment(Message *m, size_t id) {
  if (id < 512)
    return m->segments[id];
  size_t at = ((m->count + 2) & ~(size_t)1) * 4;
  for (size_t i = 0; i < id; i++)
    at += load(m->raw + 4 + 4 * i, 4) * 8;
  return (Segment){m->raw + at, load(m->raw + 4 + 4 * id, 4) * 8};
}
static int pointer(Message *m, Segment s, size_t at, Segment *target,
                   size_t *position, uint64_t *tag) {
  if (at > s.n || s.n - at < 8)
    return 0;
  uint64_t w = load(s.p + at, 8);
  if (!w) {
    *target = s;
    *position = 0;
    *tag = 0;
    return 1;
  }
  size_t start = 0;
  int absolute = 0;
  if ((w & 3) == 2) {
    uint64_t id = w >> 32;
    size_t pad = ((w >> 3) & 0x1fffffff) * 8;
    if (id >= m->count)
      return 0;
    s = segment(m, id);
    size_t size = (w & 4) ? 16 : 8;
    if (pad > s.n || size > s.n - pad)
      return 0;
    if (w & 4) {
      uint64_t far = load(s.p + pad, 8);
      w = load(s.p + pad + 8, 8);
      if ((far & 7) != 2 || (w & 0xfffffffc) != 0 || (far >> 32) >= m->count)
        return 0;
      start = ((far >> 3) & 0x1fffffff) * 8;
      s = segment(m, far >> 32);
      absolute = 1;
    } else {
      at = pad;
      w = load(s.p + at, 8);
    }
  }
  if ((w & 3) > 1)
    return 0;
  if (!absolute) {
    int64_t off = (int32_t)(uint32_t)w;
    off >>= 2;
    int64_t pos = (int64_t)at + 8 + off * 8;
    if (pos < 0)
      return 0;
    start = (size_t)pos;
  }
  if (start > s.n)
    return 0;
  *target = s;
  *position = start;
  *tag = w;
  return 1;
}
static int resolve(Message *m, Segment s, size_t at, Struct *out) {
  size_t start;
  uint64_t w;
  if (!pointer(m, s, at, &s, &start, &w) || (w & 3) != 0)
    return 0;
  size_t data = ((w >> 32) & 65535) * 8, pointers = (w >> 48) * 8;
  if (start > s.n || data + pointers > s.n - start)
    return 0;
  size_t cost = (data + pointers) / 8;
  if (cost > m->budget)
    return 0;
  m->budget -= cost;
  *out = (Struct){s, start, data, pointers};
  return 1;
}
static int child(Message *m, Struct s, size_t index, Struct *out) {
  if (index >= s.pointers / 8) {
    *out = (Struct){s.seg, 0, 0, 0};
    return 1;
  }
  return resolve(m, s.seg, s.start + s.data + index * 8, out);
}
static uint64_t scalar(Struct s, size_t offset, size_t size, uint64_t def) {
  return (offset <= s.data && size <= s.data - offset
              ? load(s.seg.p + s.start + offset, size)
              : 0) ^
         def;
}
static double real(Struct s, size_t offset, uint32_t def) {
  uint32_t bits = scalar(s, offset, 4, def);
  float f;
  memcpy(&f, &bits, 4);
  return f;
}
static int project_car(Message *m, Struct event, Result *out) {
  Struct car, wheels;
  if (scalar(event, DISCRIMINANT_OFFSET, 2, 0) != CAR_DISCRIMINANT)
    return 0;
  if (!child(m, event, CAR_POINTER, &car) ||
      !child(m, car, WHEEL_POINTER, &wheels))
    return 0;
  out->timestamp = scalar(event, TIME_OFFSET, 8, TIME_DEFAULT);
  out->valid =
      ((scalar(event, VALID_OFFSET / 8, 1, 0) >> (VALID_OFFSET % 8)) & 1) ^
      VALID_DEFAULT;
  out->speed = real(car, SPEED_OFFSET, SPEED_DEFAULT);
  out->angle = real(car, ANGLE_OFFSET, ANGLE_DEFAULT);
  out->wheel = real(wheels, WHEEL_OFFSET, WHEEL_DEFAULT);
  out->gear = scalar(car, GEAR_OFFSET, 2, GEAR_DEFAULT);
  return 1;
}
int project(const unsigned char *p, size_t n, Result *out) {
  Message m;
  Struct event;
  if (!framing(p, n, &m) || !resolve(&m, m.segments[0], 0, &event))
    return 0;
  return project_car(&m, event, out);
}
static PyObject *values_tuple(size_t count, PyObject **items) {
  for (size_t i = 0; i < count; i++)
    if (!items[i]) {
      for (size_t j = 0; j < count; j++)
        Py_XDECREF(items[j]);
      return NULL;
    }
  PyObject *out = PyTuple_New(count);
  if (!out) {
    for (size_t i = 0; i < count; i++)
      Py_DECREF(items[i]);
    return NULL;
  }
  for (size_t i = 0; i < count; i++) {
    PyTuple_SET_ITEM(out, i, items[i]);
  }
  return out;
}
PyObject *result_tuple(Result r) {
  PyObject *items[6] = {PyLong_FromUnsignedLongLong(r.timestamp),
                        PyBool_FromLong(r.valid),
                        PyFloat_FromDouble(r.speed),
                        PyFloat_FromDouble(r.angle),
                        PyFloat_FromDouble(r.wheel),
                        PyLong_FromUnsignedLong(r.gear)};
  return values_tuple(6, items);
}
PyObject *one(PyObject *self, PyObject *arg) {
  (void)self;
  if (!PyBytes_Check(arg)) {
    PyErr_SetString(PyExc_TypeError, "bytes required");
    return NULL;
  }
  Result r;
  if (!project((unsigned char *)PyBytes_AS_STRING(arg), PyBytes_GET_SIZE(arg),
               &r)) {
    PyErr_SetString(PyExc_ValueError,
                    "invalid or unsupported CarState message");
    return NULL;
  }
  return result_tuple(r);
}
static PyObject *batch(PyObject *self, PyObject *arg) {
  PyObject *seq = PySequence_Fast(arg, "sequence required");
  if (!seq)
    return NULL;
  Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
  PyObject *out = PyList_New(n);
  if (!out) {
    Py_DECREF(seq);
    return NULL;
  }
  for (Py_ssize_t i = 0; i < n; i++) {
    PyObject *item = one(self, PySequence_Fast_GET_ITEM(seq, i));
    if (!item) {
      Py_DECREF(out);
      Py_DECREF(seq);
      return NULL;
    }
    PyList_SET_ITEM(out, i, item);
  }
  Py_DECREF(seq);
  return out;
}
typedef struct {
  Segment seg;
  size_t start, count, stride, data, pointers, kind;
} List;
static int list(Message *m, Struct parent, size_t index, List *out) {
  if (index >= parent.pointers / 8) {
    *out = (List){parent.seg, 0, 0, 0, 0, 0, 8};
    return 1;
  }
  Segment s;
  size_t start;
  uint64_t w;
  if (!pointer(m, parent.seg, parent.start + parent.data + index * 8, &s,
               &start, &w))
    return 0;
  if (!w) {
    *out = (List){s, 0, 0, 0, 0, 0, 8};
    return 1;
  }
  if ((w & 3) != 1)
    return 0;
  size_t kind = (w >> 32) & 7, count = w >> 35, bytes = 0, stride = 0, data = 0,
         pointers = 0;
  if (kind == 7) {
    if (start > s.n || s.n - start < 8 || count > (s.n - start - 8) / 8)
      return 0;
    uint64_t tag = load(s.p + start, 8);
    if (tag & 3)
      return 0;
    size_t words = count;
    count = (tag >> 2) & 0x3fffffff;
    data = ((tag >> 32) & 65535) * 8;
    pointers = (tag >> 48) * 8;
    stride = data + pointers;
    if (stride && count > words / (stride / 8))
      return 0;
    start += 8;
    bytes = words * 8;
  } else {
    static const size_t sizes[] = {0, 0, 1, 2, 4, 8, 8};
    stride = sizes[kind];
    bytes = kind == 1 ? (count + 7) / 8 : count * stride;
    data = kind == 6 ? 0 : stride;
    pointers = kind == 6 ? 8 : 0;
  }
  /* Bound materialization even for zero-sized lists; this is an explicit
   * experiment limit. */
  if (count > 1000000 || start > s.n || bytes > s.n - start)
    return 0;
  size_t cost = (bytes + 7) / 8;
  if (!stride && count > cost)
    cost = count;
  if (cost > m->budget)
    return 0;
  m->budget -= cost;
  *out = (List){s, start, count, stride, data, pointers, kind};
  return 1;
}
static Struct element(List l, size_t i) {
  return (Struct){l.seg, l.start + i * l.stride, l.data, l.pointers};
}
static PyObject *floats(Message *m, Struct s, size_t slot) {
  List l;
  if (!list(m, s, slot, &l) || (l.kind != 8 && l.kind != 4 && l.kind != 5 &&
                                !(l.kind == 7 && l.data >= 4))) {
    PyErr_SetString(PyExc_ValueError, "invalid float list");
    return NULL;
  }
  PyObject *out = PyList_New(l.count);
  if (!out)
    return NULL;
  for (size_t i = 0; i < l.count; i++) {
    PyObject *v = PyFloat_FromDouble(real(element(l, i), 0, 0));
    if (!v) {
      Py_DECREF(out);
      return NULL;
    }
    PyList_SET_ITEM(out, i, v);
  }
  return out;
}
static int boolean(Struct s, size_t offset, unsigned def) {
  return ((scalar(s, offset / 8, 1, 0) >> (offset % 8)) & 1) ^ def;
}
static PyObject *project_event(PyObject *self, PyObject *arg) {
  if (!PyBytes_Check(arg)) {
    PyErr_SetString(PyExc_TypeError, "bytes required");
    return NULL;
  }
  Message m;
  Struct event, body, nested;
  List l;
  if (!framing((unsigned char *)PyBytes_AS_STRING(arg), PyBytes_GET_SIZE(arg),
               &m) ||
      !resolve(&m, m.segments[0], 0, &event))
    goto invalid;
  unsigned kind = scalar(event, DISCRIMINANT_OFFSET, 2, 0);
  (void)self;
  if (kind == CAR_DISCRIMINANT) {
    Result r;
    if (!project_car(&m, event, &r))
      goto invalid;
    return result_tuple(r);
  }
  uint64_t timestamp = scalar(event, TIME_OFFSET, 8, TIME_DEFAULT);
  PyObject *valid =
      boolean(event, VALID_OFFSET, VALID_DEFAULT) ? Py_True : Py_False;
  if (kind == CAN_DISCRIMINANT) {
    if (!list(&m, event, CAR_POINTER, &l) || (l.kind == 1))
      goto invalid;
    PyObject *frames = PyList_New(l.count);
    if (!frames)
      return NULL;
    for (size_t i = 0; i < l.count; i++) {
      Struct f = element(l, i);
      List data;
      if (!list(&m, f, CAN_DAT, &data) || (data.kind != 8 && data.kind != 2)) {
        Py_DECREF(frames);
        goto invalid;
      }
      PyObject *items[3] = {
          PyLong_FromUnsignedLong(
              scalar(f, CAN_ADDRESS, 4, CAN_ADDRESS_DEFAULT)),
          PyBytes_FromStringAndSize((const char *)data.seg.p + data.start,
                                    data.count),
          PyLong_FromUnsignedLong(scalar(f, CAN_SRC, 1, CAN_SRC_DEFAULT))};
      PyObject *v = values_tuple(3, items);
      if (!v) {
        Py_DECREF(frames);
        return NULL;
      }
      PyList_SET_ITEM(frames, i, v);
    }
    PyObject *items[3] = {PyLong_FromUnsignedLongLong(timestamp),
                          Py_NewRef(valid), frames};
    return values_tuple(3, items);
  }
  if (!child(&m, event, CAR_POINTER, &body))
    goto invalid;
  if (kind == CONTROL_DISCRIMINANT) {
    if (!child(&m, body, CONTROL_ACTUATORS, &nested))
      goto invalid;
    PyObject *items[5] = {PyLong_FromUnsignedLongLong(timestamp),
                          Py_NewRef(valid),
                          PyBool_FromLong(boolean(body, CONTROL_ENABLED,
                                                  CONTROL_ENABLED_DEFAULT)),
                          PyFloat_FromDouble(real(nested, ACTUATORS_ACCEL,
                                                  ACTUATORS_ACCEL_DEFAULT)),
                          PyFloat_FromDouble(real(nested, ACTUATORS_TORQUE,
                                                  ACTUATORS_TORQUE_DEFAULT))};
    return values_tuple(5, items);
  }
  if (kind == PLAN_DISCRIMINANT) {
    PyObject *speeds = floats(&m, body, PLAN_SPEEDS);
    if (!speeds)
      return NULL;
    PyObject *accels = floats(&m, body, PLAN_ACCELS);
    if (!accels) {
      Py_DECREF(speeds);
      return NULL;
    }
    PyObject *items[5] = {PyLong_FromUnsignedLongLong(timestamp),
                          Py_NewRef(valid), speeds, accels,
                          PyBool_FromLong(boolean(body, PLAN_SHOULDSTOP,
                                                  PLAN_SHOULDSTOP_DEFAULT))};
    return values_tuple(5, items);
  }
  if (kind == MODEL_DISCRIMINANT) {
    if (!child(&m, body, MODEL_POSITION, &nested))
      goto invalid;
    PyObject *x = floats(&m, nested, POSITION_X);
    if (!x)
      return NULL;
    if (!list(&m, body, MODEL_LEADSV3, &l) || (l.kind == 1)) {
      Py_DECREF(x);
      goto invalid;
    }
    PyObject *leads = PyList_New(l.count);
    if (!leads) {
      Py_DECREF(x);
      return NULL;
    }
    for (size_t i = 0; i < l.count; i++) {
      PyObject *v = floats(&m, element(l, i), LEAD_X);
      if (!v) {
        Py_DECREF(x);
        Py_DECREF(leads);
        return NULL;
      }
      PyList_SET_ITEM(leads, i, v);
    }
    if (!child(&m, body, MODEL_META, &nested)) {
      Py_DECREF(x);
      Py_DECREF(leads);
      goto invalid;
    }
    PyObject *items[5] = {
        PyLong_FromUnsignedLongLong(timestamp), Py_NewRef(valid), x, leads,
        PyLong_FromUnsignedLong(scalar(nested, META_LANECHANGESTATE, 2,
                                       META_LANECHANGESTATE_DEFAULT))};
    return values_tuple(5, items);
  }
invalid:
  PyErr_SetString(PyExc_ValueError, "invalid or unsupported event");
  return NULL;
}
static void store(unsigned char *p, uint64_t value, size_t n) {
  for (size_t i = 0; i < n; i++)
    p[i] = (unsigned char)(value >> (i * 8));
}
static void setreal(unsigned char *p, double value, uint32_t def) {
  float f = (float)value;
  uint32_t bits;
  memcpy(&bits, &f, 4);
  store(p, bits ^ def, 4);
}
int parse_car(PyObject *arg, Result *result) {
  if (!PyTuple_Check(arg) || PyTuple_GET_SIZE(arg) != 6) {
    PyErr_SetString(PyExc_TypeError, "six-element projection tuple required");
    return 0;
  }
  uint64_t timestamp = PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(arg, 0));
  if (PyErr_Occurred())
    return 0;
  int valid = PyObject_IsTrue(PyTuple_GET_ITEM(arg, 1));
  if (valid < 0)
    return 0;
  double speed = PyFloat_AsDouble(PyTuple_GET_ITEM(arg, 2));
  if (PyErr_Occurred())
    return 0;
  double angle = PyFloat_AsDouble(PyTuple_GET_ITEM(arg, 3));
  if (PyErr_Occurred())
    return 0;
  double wheel = PyFloat_AsDouble(PyTuple_GET_ITEM(arg, 4));
  if (PyErr_Occurred())
    return 0;
  unsigned long gear = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(arg, 5));
  if (PyErr_Occurred())
    return 0;
  if (gear > 65535) {
    PyErr_SetString(PyExc_OverflowError, "enum does not fit uint16");
    return 0;
  }
  *result =
      (Result){timestamp, speed, angle, wheel, (unsigned)valid, (unsigned)gear};
  return 1;
}
PyObject *write_car(PyObject *self, PyObject *arg) {
  (void)self;
  Result result;
  if (!parse_car(arg, &result))
    return NULL;
  uint64_t timestamp = result.timestamp;
  unsigned valid = result.valid, gear = result.gear;
  double speed = result.speed, angle = result.angle, wheel = result.wheel;
  size_t event = 1, car = event + EVENT_DATA + EVENT_POINTERS,
         wheels = car + CAR_DATA + CAR_POINTERS;
  size_t words = wheels + WHEELS_DATA + WHEELS_POINTERS;
  PyObject *out = PyBytes_FromStringAndSize(NULL, (words + 1) * 8);
  if (!out)
    return NULL;
  unsigned char *buf = (unsigned char *)PyBytes_AS_STRING(out);
  memset(buf, 0, (words + 1) * 8);
  store(buf + 4, words, 4);
  unsigned char *seg = buf + 8;
  store(seg, EVENT_DATA << 32 | EVENT_POINTERS << 48, 8);
  unsigned char *e = seg + event * 8, *c = seg + car * 8, *w = seg + wheels * 8;
  store(e + TIME_OFFSET, timestamp ^ TIME_DEFAULT, 8);
  store(e + DISCRIMINANT_OFFSET, CAR_DISCRIMINANT, 2);
  e[VALID_OFFSET / 8] |= (valid ^ VALID_DEFAULT) << (VALID_OFFSET % 8);
  size_t cp = event + EVENT_DATA + CAR_POINTER,
         wp = car + CAR_DATA + WHEEL_POINTER;
  store(seg + cp * 8, (car - cp - 1) << 2 | CAR_DATA << 32 | CAR_POINTERS << 48,
        8);
  store(seg + wp * 8,
        (wheels - wp - 1) << 2 | WHEELS_DATA << 32 | WHEELS_POINTERS << 48, 8);
  setreal(c + SPEED_OFFSET, speed, SPEED_DEFAULT);
  setreal(c + ANGLE_OFFSET, angle, ANGLE_DEFAULT);
  setreal(w + WHEEL_OFFSET, wheel, WHEEL_DEFAULT);
  store(c + GEAR_OFFSET, gear ^ GEAR_DEFAULT, 2);
  return out;
}
static unsigned char *write_event_header(PyObject *out, size_t words,
                                         uint64_t timestamp, int valid,
                                         unsigned kind) {
  unsigned char *buf = (unsigned char *)PyBytes_AS_STRING(out);
  memset(buf, 0, (words + 1) * 8);
  store(buf + 4, words, 4);
  unsigned char *seg = buf + 8;
  store(seg, EVENT_DATA << 32 | EVENT_POINTERS << 48, 8);
  unsigned char *e = seg + 8;
  store(e + TIME_OFFSET, timestamp ^ TIME_DEFAULT, 8);
  store(e + DISCRIMINANT_OFFSET, kind, 2);
  e[VALID_OFFSET / 8] |= (valid ^ VALID_DEFAULT) << (VALID_OFFSET % 8);
  return seg;
}
static void list_pointer(unsigned char *seg, size_t slot, size_t target,
                         unsigned kind, size_t count) {
  store(seg + slot * 8,
        ((target - slot - 1) << 2) | 1 | ((uint64_t)kind << 32) |
            ((uint64_t)count << 35),
        8);
}
static PyObject *write_plan(PyObject *self, PyObject *arg) {
  (void)self;
  if (!PyTuple_Check(arg) || PyTuple_GET_SIZE(arg) != 5) {
    PyErr_SetString(PyExc_TypeError, "five-element plan projection required");
    return NULL;
  }
  uint64_t timestamp = PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(arg, 0));
  if (PyErr_Occurred())
    return NULL;
  int valid = PyObject_IsTrue(PyTuple_GET_ITEM(arg, 1)),
      stop = PyObject_IsTrue(PyTuple_GET_ITEM(arg, 4));
  if (valid < 0 || stop < 0)
    return NULL;
  PyObject *speeds = PySequence_Tuple(PyTuple_GET_ITEM(arg, 2));
  if (!speeds)
    return NULL;
  PyObject *accels = PySequence_Tuple(PyTuple_GET_ITEM(arg, 3));
  if (!accels) {
    Py_DECREF(speeds);
    return NULL;
  }
  size_t ns = PySequence_Fast_GET_SIZE(speeds),
         na = PySequence_Fast_GET_SIZE(accels);
  if (ns > 1000000 || na > 1000000) {
    Py_DECREF(speeds);
    Py_DECREF(accels);
    PyErr_SetString(PyExc_ValueError, "list exceeds experimental limit");
    return NULL;
  }
  size_t body = 1 + EVENT_DATA + EVENT_POINTERS,
         s = body + PLAN_DATA + PLAN_POINTERS, a = s + (ns + 1) / 2,
         words = a + (na + 1) / 2;
  PyObject *out = PyBytes_FromStringAndSize(NULL, (words + 1) * 8);
  if (!out) {
    Py_DECREF(speeds);
    Py_DECREF(accels);
    return NULL;
  }
  unsigned char *seg =
      write_event_header(out, words, timestamp, valid, PLAN_DISCRIMINANT);
  size_t bp = 1 + EVENT_DATA + CAR_POINTER;
  store(seg + bp * 8,
        (body - bp - 1) << 2 | PLAN_DATA << 32 | PLAN_POINTERS << 48, 8);
  seg[body * 8 + PLAN_SHOULDSTOP / 8] |= (stop ^ PLAN_SHOULDSTOP_DEFAULT)
                                         << (PLAN_SHOULDSTOP % 8);
  list_pointer(seg, body + PLAN_DATA + PLAN_SPEEDS, s, 4, ns);
  list_pointer(seg, body + PLAN_DATA + PLAN_ACCELS, a, 4, na);
  for (size_t i = 0; i < ns; i++) {
    double value = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(speeds, i));
    if (PyErr_Occurred())
      goto error;
    setreal(seg + s * 8 + i * 4, value, 0);
  }
  for (size_t i = 0; i < na; i++) {
    double value = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(accels, i));
    if (PyErr_Occurred())
      goto error;
    setreal(seg + a * 8 + i * 4, value, 0);
  }
  Py_DECREF(speeds);
  Py_DECREF(accels);
  return out;
error:
  Py_DECREF(out);
  Py_DECREF(speeds);
  Py_DECREF(accels);
  return NULL;
}
static PyObject *write_can(PyObject *self, PyObject *arg) {
  (void)self;
  if (!PyTuple_Check(arg) || PyTuple_GET_SIZE(arg) != 3) {
    PyErr_SetString(PyExc_TypeError, "three-element CAN projection required");
    return NULL;
  }
  uint64_t timestamp = PyLong_AsUnsignedLongLong(PyTuple_GET_ITEM(arg, 0));
  if (PyErr_Occurred())
    return NULL;
  int valid = PyObject_IsTrue(PyTuple_GET_ITEM(arg, 1));
  if (valid < 0)
    return NULL;
  PyObject *frames = PySequence_Tuple(PyTuple_GET_ITEM(arg, 2));
  if (!frames)
    return NULL;
  size_t count = PySequence_Fast_GET_SIZE(frames);
  if (count > 1000000) {
    Py_DECREF(frames);
    PyErr_SetString(PyExc_ValueError, "list exceeds experimental limit");
    return NULL;
  }
  size_t start = 1 + EVENT_DATA + EVENT_POINTERS,
         stride = CAN_DATA + CAN_POINTERS, blob = start + 1 + count * stride,
         words = blob;
  for (size_t i = 0; i < count; i++) {
    PyObject *frame = PySequence_Fast_GET_ITEM(frames, i);
    if (!PyTuple_Check(frame) || PyTuple_GET_SIZE(frame) != 3 ||
        !PyBytes_Check(PyTuple_GET_ITEM(frame, 1))) {
      PyErr_SetString(PyExc_TypeError,
                      "CAN frame must be (address, bytes, src)");
      Py_DECREF(frames);
      return NULL;
    }
    size_t size = PyBytes_GET_SIZE(PyTuple_GET_ITEM(frame, 1));
    if (size > 1000000 || words + (size + 7) / 8 > 8 * 1024 * 1024) {
      PyErr_SetString(PyExc_ValueError, "Data exceeds experimental limit");
      Py_DECREF(frames);
      return NULL;
    }
    words += (size + 7) / 8;
  }
  PyObject *out = PyBytes_FromStringAndSize(NULL, (words + 1) * 8);
  if (!out) {
    Py_DECREF(frames);
    return NULL;
  }
  unsigned char *seg =
      write_event_header(out, words, timestamp, valid, CAN_DISCRIMINANT);
  list_pointer(seg, 1 + EVENT_DATA + CAR_POINTER, start, 7, count * stride);
  store(seg + start * 8, (count << 2) | CAN_DATA << 32 | CAN_POINTERS << 48, 8);
  for (size_t i = 0; i < count; i++) {
    PyObject *frame = PySequence_Fast_GET_ITEM(frames, i),
             *data = PyTuple_GET_ITEM(frame, 1);
    unsigned long address = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(frame, 0));
    if (PyErr_Occurred())
      goto error;
    unsigned long src = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(frame, 2));
    if (PyErr_Occurred())
      goto error;
    if (address > UINT32_MAX || src > 255) {
      PyErr_SetString(PyExc_OverflowError, "CAN integer out of range");
      goto error;
    }
    size_t at = start + 1 + i * stride, size = PyBytes_GET_SIZE(data);
    store(seg + at * 8 + CAN_ADDRESS, address ^ CAN_ADDRESS_DEFAULT, 4);
    store(seg + at * 8 + CAN_SRC, src ^ CAN_SRC_DEFAULT, 1);
    list_pointer(seg, at + CAN_DATA + CAN_DAT, blob, 2, size);
    memcpy(seg + blob * 8, PyBytes_AS_STRING(data), size);
    blob += (size + 7) / 8;
  }
  Py_DECREF(frames);
  return out;
error:
  Py_DECREF(out);
  Py_DECREF(frames);
  return NULL;
}
static PyMethodDef methods[] = {{"write_car", write_car, METH_O, NULL},
                                {"write_can", write_can, METH_O, NULL},
                                {"write_plan", write_plan, METH_O, NULL},
                                {"event", project_event, METH_O, NULL},
                                {"one", one, METH_O, NULL},
                                {"batch", batch, METH_O, NULL},
                                {NULL, NULL, 0, NULL}};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "wire", NULL, -1,
                                    methods};
PyMODINIT_FUNC PyInit_wire(void) { return PyModule_Create(&module); }
