#include "result.h"
#include <pybind11/pybind11.h>
#include <stdint.h>
namespace py = pybind11;
extern "C" {

int project(const unsigned char *, size_t, Result *);
}
static py::tuple one(py::bytes data) {
  Result result;
  if (!project(reinterpret_cast<const unsigned char *>(
                   PyBytes_AS_STRING(data.ptr())),
               PyBytes_GET_SIZE(data.ptr()), &result))
    throw py::value_error("invalid or unsupported CarState message");
  return py::make_tuple(result.timestamp, bool(result.valid), result.speed,
                        result.angle, result.wheel, result.gear);
}
PYBIND11_MODULE(_wire_pybind, m) {
  m.def("one", &one, py::arg("data").noconvert());
  m.def("batch", [](py::list rows) {
    py::list output(rows.size());
    size_t i = 0;
    for (py::handle row : rows) {
      if (!PyBytes_Check(row.ptr()))
        throw py::type_error("bytes required");
      output[i++] = one(py::reinterpret_borrow<py::bytes>(row));
    }
    return output;
  });
}
