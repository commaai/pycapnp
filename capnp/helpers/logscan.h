#pragma once
#include <capnp/dynamic.h>
#include <capnp/serialize.h>
#include <kj/debug.h>
#include <Python.h>
#include <cstring>
#include <string>
#include <vector>

namespace pycapnp_scan {
struct Value {
  int type = 0;
  union { int64_t integer = 0; uint64_t unsignedInteger; double number; };
  std::string text;
  std::vector<Value> values;
  std::vector<double> numbers;
  std::vector<uint64_t> unsignedNumbers;
  std::vector<int64_t> signedNumbers;
  std::vector<std::string> strings;
};
using Row = std::vector<Value>;
using Rows = std::vector<Row>;
using Names = std::vector<std::vector<std::string>>;
// Immutable Python bytes stay pinned for the whole GIL-free operation. Copy only
// if an alternative Python allocator supplies a non-word-aligned address.
struct Input {
  kj::Array<capnp::word> owned;
  kj::ArrayPtr<const capnp::word> words;
  Input(const char* data, size_t size) {
    KJ_REQUIRE(size % sizeof(capnp::word) == 0, "truncated message stream");
    if (reinterpret_cast<uintptr_t>(data) % alignof(capnp::word) == 0) {
      words = kj::arrayPtr(reinterpret_cast<const capnp::word*>(data), size / sizeof(capnp::word));
    } else {
      owned = kj::heapArray<capnp::word>(size / sizeof(capnp::word));
      memcpy(owned.begin(), data, size);
      words = owned.asPtr();
    }
  }
};
inline std::vector<size_t> boundaries(const char* data, size_t size) {
  Input input(data, size);
  auto words = input.words;
  std::vector<size_t> offsets{0};
  const auto* pos = words.begin();
  while (pos != words.end()) {
    capnp::FlatArrayMessageReader reader(kj::arrayPtr(pos, size_t(words.end() - pos)));
    const auto* end = reader.getEnd();
    KJ_REQUIRE(end > pos, "empty frame");
    offsets.push_back(reinterpret_cast<const char*>(end) - reinterpret_cast<const char*>(words.begin()));
    pos = end;
  }
  return offsets;
}
inline Value convert(capnp::DynamicValue::Reader source) {
  Value value;
  switch (source.getType()) {
    case capnp::DynamicValue::VOID: break;
    case capnp::DynamicValue::BOOL: value.type=1; value.unsignedInteger=source.as<bool>(); break;
    case capnp::DynamicValue::INT: value.type=2; value.integer=source.as<int64_t>(); break;
    case capnp::DynamicValue::UINT: value.type=3; value.unsignedInteger=source.as<uint64_t>(); break;
    case capnp::DynamicValue::FLOAT: value.type=4; value.number=source.as<double>(); break;
    case capnp::DynamicValue::TEXT: { auto x=source.as<capnp::Text>(); value.type=5; value.text.assign(x.begin(),x.size()); break; }
    case capnp::DynamicValue::DATA: { auto x=source.as<capnp::Data>(); value.type=6; value.text.assign(reinterpret_cast<const char*>(x.begin()),x.size()); break; }
    case capnp::DynamicValue::ENUM: value.type=3; value.unsignedInteger=source.as<capnp::DynamicEnum>().getRaw(); break;
    case capnp::DynamicValue::LIST: {
      auto list=source.as<capnp::DynamicList>();
      auto type=list.getSchema().getElementType();
      if (type.isFloat32() || type.isFloat64()) {
        value.type=8;
        value.numbers.reserve(list.size());
        if (type.isFloat32()) {
          for (auto number : list.as<capnp::List<float>>()) value.numbers.push_back(number);
        } else {
          for (auto number : list.as<capnp::List<double>>()) value.numbers.push_back(number);
        }
        break;
      }
      value.type=7;
      value.values.reserve(list.size());
      for (auto item : list) value.values.push_back(convert(item));
      break;
    }
    default: KJ_FAIL_REQUIRE("unsupported projected field");
  }
  return value;
}
inline void appendScalar(Value& result, capnp::DynamicValue::Reader source) {
  switch (source.getType()) {
    case capnp::DynamicValue::UINT: result.type=9; result.unsignedNumbers.push_back(source.as<uint64_t>()); break;
    case capnp::DynamicValue::INT: result.type=10; result.signedNumbers.push_back(source.as<int64_t>()); break;
    case capnp::DynamicValue::FLOAT: result.type=8; result.numbers.push_back(source.as<double>()); break;
    case capnp::DynamicValue::BOOL: result.type=13; result.unsignedNumbers.push_back(source.as<bool>()); break;
    case capnp::DynamicValue::ENUM: result.type=9; result.unsignedNumbers.push_back(source.as<capnp::DynamicEnum>().getRaw()); break;
    case capnp::DynamicValue::TEXT: { result.type=11; auto v=source.as<capnp::Text>(); result.strings.emplace_back(v.begin(),v.size()); break; }
    case capnp::DynamicValue::DATA: { result.type=12; auto v=source.as<capnp::Data>(); result.strings.emplace_back(reinterpret_cast<const char*>(v.begin()),v.size()); break; }
    default: result.values.push_back(convert(source));
  }
}
inline Value readPath(capnp::DynamicValue::Reader source,
                      const std::vector<capnp::StructSchema::Field>& path, size_t index) {
  while (index < path.size() && source.getType() != capnp::DynamicValue::LIST)
    source = source.as<capnp::DynamicStruct>().get(path[index++]);
  if (index == path.size()) return convert(source);
  if (source.getType() == capnp::DynamicValue::LIST) {
    Value result;
    result.type = 7;
    auto list = source.as<capnp::DynamicList>();
    if (index + 1 == path.size() && !path[index].getType().isList() &&
        list.getSchema().getElementType().isStruct()) {
      for (auto item : list) appendScalar(result, item.as<capnp::DynamicStruct>().get(path[index]));
    } else {
      result.values.reserve(list.size());
      for (auto item : list) result.values.push_back(readPath(item, path, index));
    }
    return result;
  }
  return readPath(source.as<capnp::DynamicStruct>().get(path[index]), path, index + 1);
}
struct Request {
  std::vector<capnp::StructSchema::Field> fields;
  size_t node = 0, skip = 0;
};
struct Node { size_t parent; capnp::StructSchema::Field field; };
struct Plan {
  std::vector<Request> paths;
  std::vector<Node> nodes;
  std::vector<capnp::DynamicValue::Reader> cached;
  std::vector<bool> ready;
  std::vector<size_t> pending;
  capnp::StructSchema::Field selected;
  bool shared;
  Plan(capnp::StructSchema schema, const std::string& filter, const Names& names, bool shared)
      : selected(schema.getFieldByName(filter.c_str())), shared(shared) {
    KJ_REQUIRE(selected.getProto().getDiscriminantValue() != 65535, "filter must name a union field");
    for (const auto& name : names) {
      KJ_REQUIRE(!name.empty(), "empty field path");
      auto current = schema;
      Request path;
      for (size_t i = 0; i < name.size(); ++i) {
        auto field = current.getFieldByName(name[i].c_str());
        path.fields.push_back(field);
        auto type = field.getType();
        while (type.isList()) type = type.asList().getElementType();
        if (i + 1 < name.size()) current = type.asStruct();
        else KJ_REQUIRE(!type.isStruct() && !type.isAnyPointer(), "projection requires scalar or scalar-list leaves");
      }
      if (shared) {
        for (size_t i = 0; i + 1 < path.fields.size(); ++i) {
          size_t found = 0;
          for (size_t n = 0; n < nodes.size(); ++n) {
            if (nodes[n].parent == path.node && nodes[n].field == path.fields[i]) { found = n + 1; break; }
          }
          if (!found) { nodes.push_back({path.node, path.fields[i]}); found = nodes.size(); }
          path.node = found;
          path.skip = i + 1;
          if (path.fields[i].getType().isList()) break;
        }
      }
      paths.push_back(std::move(path));
    }
    cached.resize(nodes.size() + 1);
    ready.resize(nodes.size() + 1);
    pending.reserve(nodes.size());
  }
  void begin(capnp::DynamicStruct::Reader root) {
    std::fill(ready.begin(), ready.end(), false);
    cached[0] = capnp::DynamicValue::Reader(root);
    ready[0] = true;
  }
  capnp::DynamicValue::Reader get(size_t node) {
    pending.clear();
    size_t current = node;
    while (!ready[current]) {
      pending.push_back(current);
      current = nodes[current - 1].parent;
    }
    while (!pending.empty()) {
      current = pending.back();
      pending.pop_back();
      const auto& entry = nodes[current - 1];
      cached[current] = cached[entry.parent].as<capnp::DynamicStruct>().get(entry.field);
      ready[current] = true;
    }
    return cached[node];
  }
};

template <typename Sink>
inline void scan(const char* data, size_t size, capnp::StructSchema schema,
                 const std::string& filter, const Names& names, uint64_t limit, int nesting,
                 bool shared, Sink sink) {
  Plan plan(schema, filter, names, shared);
  Input input(data, size);
  auto words = input.words;
  capnp::ReaderOptions options;
  options.traversalLimitInWords = limit;
  options.nestingLimit = nesting;
  const auto* pos = words.begin();
  while (pos != words.end()) {
    capnp::FlatArrayMessageReader reader(kj::arrayPtr(pos, size_t(words.end() - pos)), options);
    pos = reader.getEnd();
    auto root = reader.getRoot<capnp::DynamicStruct>(schema);
    KJ_IF_MAYBE(active, root.which()) {
      if (*active != plan.selected) continue;
    } else { continue; }
    plan.begin(root);
    sink(plan);
  }
}

inline Rows project(const char* data, size_t size, capnp::StructSchema schema,
                    const std::string& filter, const Names& names, uint64_t limit, int nesting,
                    bool flat, bool shared) {
  Rows rows;
  if (flat) rows.emplace_back();
  scan(data,size,schema,filter,names,limit,nesting,shared,[&](Plan& plan) {
    Row owned;
    Row& row = flat ? rows.front() : owned;
    if (!flat) row.reserve(plan.paths.size());
    for (const auto& path : plan.paths) row.push_back(readPath(plan.get(path.node),path.fields,path.skip));
    if (!flat) rows.push_back(std::move(row));
  });
  return rows;
}

struct PyOwned {
  PyObject* value;
  explicit PyOwned(PyObject* value): value(value) {}
  ~PyOwned() { Py_XDECREF(value); }
  PyObject* release() { auto result=value; value=nullptr; return result; }
};
template <typename T>
inline PyObject* floatsPython(capnp::DynamicList::Reader source) {
  auto list=source.as<capnp::List<T>>();
  PyOwned result(PyList_New(list.size()));
  if (!result.value) return nullptr;
  for (unsigned i=0;i<list.size();++i) {
    auto value=PyFloat_FromDouble(list[i]);
    if (!value) return nullptr;
    PyList_SET_ITEM(result.value,i,value);
  }
  return result.release();
}
inline PyObject* convertPython(capnp::DynamicValue::Reader source) {
  switch (source.getType()) {
    case capnp::DynamicValue::VOID: Py_RETURN_NONE;
    case capnp::DynamicValue::BOOL: return PyBool_FromLong(source.as<bool>());
    case capnp::DynamicValue::INT: return PyLong_FromLongLong(source.as<int64_t>());
    case capnp::DynamicValue::UINT: return PyLong_FromUnsignedLongLong(source.as<uint64_t>());
    case capnp::DynamicValue::FLOAT: return PyFloat_FromDouble(source.as<double>());
    case capnp::DynamicValue::ENUM: return PyLong_FromUnsignedLong(source.as<capnp::DynamicEnum>().getRaw());
    case capnp::DynamicValue::TEXT: { auto v=source.as<capnp::Text>(); return PyUnicode_DecodeUTF8(v.begin(),v.size(),nullptr); }
    case capnp::DynamicValue::DATA: { auto v=source.as<capnp::Data>(); return PyBytes_FromStringAndSize(reinterpret_cast<const char*>(v.begin()),v.size()); }
    case capnp::DynamicValue::LIST: {
      auto list=source.as<capnp::DynamicList>();
      auto type=list.getSchema().getElementType();
      if (type.isFloat32()) return floatsPython<float>(list);
      if (type.isFloat64()) return floatsPython<double>(list);
      PyOwned result(PyList_New(list.size()));
      if (!result.value) return nullptr;
      for (unsigned i=0;i<list.size();++i) {
        auto value=convertPython(list[i]);
        if (!value) return nullptr;
        PyList_SET_ITEM(result.value,i,value);
      }
      return result.release();
    }
    default: KJ_FAIL_REQUIRE("unsupported projected field");
  }
}
inline PyObject* readPathPython(capnp::DynamicValue::Reader source,
                               const std::vector<capnp::StructSchema::Field>& path, size_t index) {
  while (index < path.size() && source.getType() != capnp::DynamicValue::LIST)
    source = source.as<capnp::DynamicStruct>().get(path[index++]);
  if (index == path.size()) return convertPython(source);
  if (source.getType() == capnp::DynamicValue::LIST) {
    auto list=source.as<capnp::DynamicList>();
    PyOwned result(PyList_New(list.size()));
    if (!result.value) return nullptr;
    for (unsigned i=0;i<list.size();++i) {
      auto value=readPathPython(list[i],path,index);
      if (!value) return nullptr;
      PyList_SET_ITEM(result.value,i,value);
    }
    return result.release();
  }
  return readPathPython(source.as<capnp::DynamicStruct>().get(path[index]),path,index+1);
}
struct PythonError {};
inline PyObject* projectPython(const char* data, size_t size, capnp::StructSchema schema,
                               const std::string& filter, const Names& names, uint64_t limit,
                               int nesting, bool shared) {
  PyOwned result(PyList_New(0));
  if (!result.value) return nullptr;
  try {
    scan(data,size,schema,filter,names,limit,nesting,shared,[&](Plan& plan) {
      PyOwned row(PyTuple_New(plan.paths.size()));
      if (!row.value) throw PythonError();
      for (size_t i=0;i<plan.paths.size();++i) {
        const auto& path=plan.paths[i];
        auto value=readPathPython(plan.get(path.node),path.fields,path.skip);
        if (!value) throw PythonError();
        PyTuple_SET_ITEM(row.value,i,value);
      }
      if (PyList_Append(result.value,row.value)<0) throw PythonError();
    });
  } catch (PythonError&) { return nullptr; }
  return result.release();
}
}
