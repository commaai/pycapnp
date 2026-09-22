#pragma once
#include <Python.h>
#include <capnp/message.h>
#include <capnp/serialize.h>
#include <capnp/any.h>
#include <memory>
#include <stdexcept>
#include <limits>
#include <cstring>
#include <initializer_list>
#include <unordered_map>
#include <string_view>
#include <vector>
struct Owned { PyObject* p; explicit Owned(PyObject* p):p(p){} ~Owned(){Py_XDECREF(p);} PyObject* release(){auto* v=p;p=nullptr;return v;} };
void check(void* p){if(!p)throw std::runtime_error("Python conversion failed");}
PyObject* error(){try{throw;}catch(const kj::Exception& e){PyErr_SetString(PyExc_ValueError,e.getDescription().cStr());}catch(const std::bad_alloc&){PyErr_NoMemory();}catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());}return nullptr;}
// Retain a stable snapshot before any __float__/__index__/iterator callback can mutate input.
struct DictSnapshot {
  std::vector<std::pair<PyObject*,PyObject*>> items;
  explicit DictSnapshot(PyObject* d){
    if(!PyDict_Check(d))throw std::runtime_error("expected dict");
    items.reserve(PyDict_Size(d));
    PyObject *key,*value;Py_ssize_t pos=0;
    while(PyDict_Next(d,&pos,&key,&value)){items.emplace_back(key,value);Py_INCREF(key);Py_INCREF(value);}
  }
  DictSnapshot(const DictSnapshot&)=delete;
  ~DictSnapshot(){for(auto pair:items){Py_DECREF(pair.first);Py_DECREF(pair.second);}}
};
PyObject* unsupported(){PyErr_SetString(PyExc_NotImplementedError,"any pointer unsupported");return nullptr;}
struct Owner {
  kj::Array<capnp::word> words;
  PyObject* pinned = nullptr;
  std::unique_ptr<capnp::FlatArrayMessageReader> reader;
  std::unique_ptr<capnp::MallocMessageBuilder> builder;
  Owner(PyObject* data) { auto* p=PyBytes_AS_STRING(data);auto n=PyBytes_GET_SIZE(data);static bool copy_input=getenv("GENERATED_COPY_INPUT")!=nullptr;if(!copy_input&&PyBytes_CheckExact(data)&&reinterpret_cast<uintptr_t>(p)%8==0){reader=std::make_unique<capnp::FlatArrayMessageReader>(kj::arrayPtr(reinterpret_cast<const capnp::word*>(p),n/8));pinned=Py_NewRef(data);}else{words=kj::heapArray<capnp::word>(n/8);memcpy(words.begin(),p,n);reader=std::make_unique<capnp::FlatArrayMessageReader>(words.asPtr());} }
  ~Owner(){reader.reset();Py_XDECREF(pinned);}
  Owner():builder(std::make_unique<capnp::MallocMessageBuilder>()){}
};
struct Handle {
  std::shared_ptr<Owner> owner;capnp::_::StructReader reader;int schema;
  std::unique_ptr<capnp::_::StructBuilder> builder;
  Handle(std::shared_ptr<Owner> o,capnp::_::StructReader r,int s):owner(std::move(o)),reader(r),schema(s){}
  Handle(std::shared_ptr<Owner> o,capnp::_::StructBuilder b,int s):owner(std::move(o)),reader(b.asReader()),schema(s),builder(std::make_unique<capnp::_::StructBuilder>(b)){}
};
struct Slot {alignas(Handle) unsigned char bytes[sizeof(Handle)];};
Handle* construct(Slot* s,Handle* h) noexcept {try{static bool heap=getenv("GENERATED_HEAP_HANDLE")!=nullptr;return heap ? new Handle(std::move(*h)) : new(s->bytes) Handle(std::move(*h));}catch(const std::bad_alloc&){PyErr_NoMemory();return nullptr;}}
void destroy_handle(Handle* h,Slot* s){if(!h)return;if(h==reinterpret_cast<Handle*>(s->bytes))h->~Handle();else delete h;}
static PyObject* (*factory)(int,Handle*);
void set_factory(PyObject* (*f)(int,Handle*)){factory=f;}
PyObject* wrap(int i,Handle&& h){return factory(i,&h);}
PyObject* parse(PyObject* data){try{if(!PyBytes_Check(data))throw std::runtime_error("expected bytes");auto n=PyBytes_GET_SIZE(data);if(n%8)throw std::runtime_error("unaligned message length");auto o=std::make_shared<Owner>(data);auto p=capnp::_::PointerHelpers<capnp::AnyPointer>::getInternalReader(o->reader->getRoot<capnp::AnyPointer>());return wrap(0,Handle(o,p.getStruct(nullptr),0));}catch(...){return error();}}
bool boolean(PyObject* v){if(!PyBool_Check(v))throw std::runtime_error("expected bool");return v==Py_True;}
double number(PyObject* v){auto n=PyFloat_AsDouble(v);if(PyErr_Occurred())throw std::runtime_error("expected number");return n;}
template<class T>T integer(PyObject* v){if(!PyLong_Check(v))throw std::runtime_error("expected integer");if constexpr(std::is_signed<T>::value){auto n=PyLong_AsLongLong(v);if(PyErr_Occurred()||n<std::numeric_limits<T>::min()||n>std::numeric_limits<T>::max())throw std::runtime_error("integer out of range");return n;}else{auto n=PyLong_AsUnsignedLongLong(v);if(PyErr_Occurred()||n>std::numeric_limits<T>::max())throw std::runtime_error("integer out of range");return n;}}
uint16_t enumerant(PyObject* v,std::initializer_list<const char*> names){if(PyLong_Check(v))return integer<uint16_t>(v);unsigned i=0;for(auto name:names){if(PyUnicode_CompareWithASCIIString(v,name)==0)return i;++i;}throw std::runtime_error("unknown enumerant");}
void set_text(capnp::_::PointerBuilder b,PyObject* v){Py_ssize_t n;auto p=PyUnicode_AsUTF8AndSize(v,&n);check((void*)p);b.setBlob<capnp::Text>(capnp::Text::Reader(p,n));}
void set_data(capnp::_::PointerBuilder b,PyObject* v){if(!PyBytes_Check(v))throw std::runtime_error("expected bytes");b.setBlob<capnp::Data>(capnp::Data::Reader((const capnp::byte*)PyBytes_AS_STRING(v),PyBytes_GET_SIZE(v)));}

capnp::_::StructBuilder writable(Handle* h){if(!h||!h->builder)throw std::runtime_error("reader is immutable");return *h->builder;}
PyObject* to_bytes(Handle* h){try{writable(h);if(h->schema==0){auto words=capnp::messageToFlatArray(*h->owner->builder);return PyBytes_FromStringAndSize((const char*)words.begin(),words.size()*8);}capnp::MallocMessageBuilder copy;auto p=capnp::_::PointerHelpers<capnp::AnyPointer>::getInternalBuilder(copy.getRoot<capnp::AnyPointer>());p.setStruct(h->reader);auto words=capnp::messageToFlatArray(copy);return PyBytes_FromStringAndSize((const char*)words.begin(),words.size()*8);}catch(...){return error();}}
PyObject* child(Handle* h,int schema,unsigned offset,unsigned data,unsigned pointers){if(h->builder)return wrap(schema,Handle(h->owner,h->builder->getPointerField(offset).getStruct(capnp::_::StructSize(data,pointers),nullptr),schema));return wrap(schema,Handle(h->owner,h->reader.getPointerField(offset).getStruct(nullptr),schema));}
PyObject* group(Handle* h,int schema){if(h->builder)return wrap(schema,Handle(h->owner,*h->builder,schema));return wrap(schema,Handle(h->owner,h->reader,schema));}

static std::unordered_map<std::string_view,PyObject*> union_names;
PyObject* interned(const char* name){static bool uncached=getenv("GENERATED_UNCACHED_UNION")!=nullptr;if(uncached)return PyUnicode_FromString(name);auto it=union_names.find(name);if(it==union_names.end()){auto* s=PyUnicode_InternFromString(name);if(!s)return nullptr;Owned temporary(s);it=union_names.emplace(name,s).first;temporary.release();}return Py_NewRef(it->second);}
void clear_names(){for(auto item:union_names)Py_DECREF(item.second);union_names.clear();}

// Optional lazy view: eager field properties remain optimized for complete materialization.
struct ListState {
  std::shared_ptr<Owner> owner;
  capnp::_::ListReader reader;
  std::unique_ptr<capnp::_::ListBuilder> builder;
  PyObject* (*get)(ListState*,unsigned);
  int (*set)(ListState*,unsigned,PyObject*);
  ListState(std::shared_ptr<Owner> o,capnp::_::ListReader r,decltype(get) g,decltype(set) s):owner(std::move(o)),reader(r),get(g),set(s){}
  ListState(std::shared_ptr<Owner> o,capnp::_::ListBuilder b,decltype(get) g,decltype(set) s):owner(std::move(o)),reader(b.asReader()),builder(std::make_unique<capnp::_::ListBuilder>(b)),get(g),set(s){}
};
struct ListObject {PyObject_HEAD ListState* state;};
static PyTypeObject list_type={PyVarObject_HEAD_INIT(nullptr,0)};
static Py_ssize_t list_len(ListObject* o){return o->state->reader.size();}
static PyObject* list_get(ListObject* o,Py_ssize_t i){if(i<0||i>=list_len(o)){PyErr_SetString(PyExc_IndexError,"list index");return nullptr;}return o->state->get(o->state,i);}
static int list_set(ListObject* o,Py_ssize_t i,PyObject* value){if(i<0||i>=list_len(o)){PyErr_SetString(PyExc_IndexError,"list index");return -1;}if(!value){PyErr_SetString(PyExc_TypeError,"cannot delete element");return -1;}return o->state->set(o->state,i,value);}
static void list_destroy(ListObject* o){delete o->state;Py_TYPE(o)->tp_free((PyObject*)o);}
PyObject* wrap_list(ListState&& state){
  static PySequenceMethods sequence={};
  static bool ready=false;
  if(!ready){
    list_type.tp_name="generated.ListView";list_type.tp_basicsize=sizeof(ListObject);list_type.tp_flags=Py_TPFLAGS_DEFAULT;
    list_type.tp_dealloc=(destructor)list_destroy;sequence.sq_length=(lenfunc)list_len;sequence.sq_item=(ssizeargfunc)list_get;sequence.sq_ass_item=(ssizeobjargproc)list_set;list_type.tp_as_sequence=&sequence;
    if(PyType_Ready(&list_type)<0)return nullptr;ready=true;
  }
  auto* o=(ListObject*)list_type.tp_alloc(&list_type,0);if(!o)return nullptr;
  try{o->state=new ListState(std::move(state));}catch(...){Py_DECREF(o);throw;}return (PyObject*)o;
}
