"""Generate typed, library-backed CPython bindings from Cap'n Proto schemas."""

import json
import argparse
import re
import shutil
import struct
from pathlib import Path
import capnp

parser = argparse.ArgumentParser(description="Generate typed CPython bindings for a Cap'n Proto root struct.")
parser.add_argument("--schema", required=True, type=Path)
parser.add_argument("--module", default="generated_native", help="Python extension module name")
parser.add_argument("--root", default="Event", help="Root struct, optionally qualified with dots")
parser.add_argument("-I", "--include", action="append", default=[], help="Schema import directory")
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "build")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.module):
    parser.error("--module must be an ASCII Python identifier")
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
module = capnp.load(str(args.schema.resolve()), imports=args.include)
root_module = module
for part in args.root.split("."):
    root_module = getattr(root_module, part)

schemas = []
contexts = []
ids = {}


def bound(t, context):
    if t.which() == "anyPointer" and t.anyPointer.which() == "parameter":
        p = t.anyPointer.parameter
        key = (int(p.scopeId), int(p.parameterIndex))
        if key not in context:
            raise ValueError("unbound generic parameter")
        return context[key]
    return t.which()


def brand(t, context):
    result = dict(context)
    if t.which() == "struct":
        for scope in t.struct.brand.scopes:
            if scope.which() == "bind":
                for j, binding in enumerate(scope.bind):
                    if binding.which() != "type":
                        raise ValueError("unbound generic")
                    k = bound(binding.type, context)
                    if k in ("struct", "list", "enum", "anyPointer"):
                        raise ValueError("complex generic binding unsupported")
                    result[int(scope.scopeId), j] = k
    return result


def add(schema, context=None):
    context = context or {}
    ident = (int(schema.node.id), tuple(sorted(context.items())) if schema.node.isGeneric else ())
    if ident in ids:
        return ids[ident]
    idx = ids[ident] = len(schemas)
    schemas.append(schema)
    contexts.append(context)
    for field in schema.fields.values():
        p = field.proto
        if p.which() == "group":
            add(field.schema, context)
            continue
        typ = p.slot.type
        child = field.schema if typ.which() in ("struct", "list") else None
        while typ.which() == "list":
            typ = typ.list.elementType
            child = child.elementType if typ.which() in ("struct", "list", "enum") else None
        if typ.which() == "struct":
            add(child, brand(typ, context))
    return idx


if root_module.schema.node.which() != "struct":
    raise ValueError("--root must select a struct")
add(root_module.schema)
cpp = [
    '#include "runtime.h"',
    f"constexpr int ROOT_WORDS={schemas[0].node.struct.dataWordCount},ROOT_POINTERS={schemas[0].node.struct.pointerCount};",
]
cp = [
    '#include "accessors.h"',
    "typedef struct { PyObject_HEAD Handle* h; Slot storage; } Object;",
    "static PyTypeObject types[" + str(len(schemas)) + "];",
    "static PyObject* make_native(int i, Handle* h) { auto* o=(Object*)types[i].tp_alloc(&types[i],0); if(!o)return nullptr;o->h=construct(&o->storage,h);if(!o->h){Py_DECREF(o);return nullptr;}return (PyObject*)o; }",
    "static void destroy(Object* o){destroy_handle(o->h,&o->storage); Py_TYPE(o)->tp_free((PyObject*)o);}",
    "static PyObject* which(Object* o, PyObject*){return union_name(o->h);}",
    "static PyObject* view_method(Object* o,PyObject* field){return view_field(o->h,field);}",
    "static PyObject* bytes_method(Object* o,PyObject*){return to_bytes(o->h);}",
    'static PyObject* init_method(Object* o,PyObject* args){PyObject* field;int n=-1;if(!PyArg_ParseTuple(args,"O|i",&field,&n))return nullptr;return init_field(o->h,field,n);}',
    'static PyMethodDef methods[]={{"view",(PyCFunction)view_method,METH_O,nullptr},{"which",(PyCFunction)which,METH_NOARGS,nullptr},{"to_bytes",(PyCFunction)bytes_method,METH_NOARGS,nullptr},{"init",(PyCFunction)init_method,METH_VARARGS,nullptr},{nullptr}};',
]
for i in range(len(schemas)):
    cpp += [f"void fill_{i}(capnp::_::StructBuilder b, PyObject* d);"]
cpp += ["PyObject* init_field(Handle*,PyObject*,int);", "PyObject* view_field(Handle*,PyObject*);"]
cpp += ["static const char* which_value(int schema, capnp::_::StructReader r) { switch(schema) {"]
for i, s in enumerate(schemas):
    if s.node.struct.discriminantCount:
        cpp += [f"case {i}: switch(r.getDataField<uint16_t>({s.node.struct.discriminantOffset})){{"]
        cpp += [
            f'case {f.proto.discriminantValue}: return "{name}";'
            for name, f in s.fields.items()
            if f.proto.discriminantValue != 65535
        ]
        cpp += ['default: throw std::runtime_error("unknown union discriminant");}']
cpp += [
    'default: throw std::runtime_error("struct has no union");}}',
    'PyObject* union_name(Handle* h){try{if(!h)throw std::runtime_error("uninitialized reader");return interned(which_value(h->schema,h->reader));}catch(...){return error();}}',
]
primitive = {
    "bool": "bool",
    "int8": "int8_t",
    "int16": "int16_t",
    "int32": "int32_t",
    "int64": "int64_t",
    "uint8": "uint8_t",
    "uint16": "uint16_t",
    "uint32": "uint32_t",
    "uint64": "uint64_t",
    "float32": "float",
    "float64": "double",
    "enum": "uint16_t",
}
size = {
    "void": "VOID",
    "bool": "BIT",
    "int8": "BYTE",
    "uint8": "BYTE",
    "int16": "TWO_BYTES",
    "uint16": "TWO_BYTES",
    "enum": "TWO_BYTES",
    "int32": "FOUR_BYTES",
    "uint32": "FOUR_BYTES",
    "float32": "FOUR_BYTES",
    "int64": "EIGHT_BYTES",
    "uint64": "EIGHT_BYTES",
    "float64": "EIGHT_BYTES",
    "struct": "INLINE_COMPOSITE",
}


def desc(t, schema=None, context=None):
    context = context or {}
    kind = bound(t, context)
    if kind == "struct":
        return (kind, add(schema, brand(t, context)))
    if kind == "enum":
        return (kind, schema.enumerants)
    if kind == "list":
        inner = t.list.elementType
        return (kind, desc(inner, schema.elementType if inner.which() in ("struct", "list", "enum") else None, context))
    if kind not in primitive and kind not in ("void", "text", "data"):
        raise ValueError(f"unsupported schema type: {kind}")
    return (kind, None)


def pyvalue(expr, k):
    if k == "bool":
        return f"PyBool_FromLong({expr})"
    if k.startswith("float"):
        return f"PyFloat_FromDouble({expr})"
    if k.startswith("uint") or k == "enum":
        return f"PyLong_FromUnsignedLongLong({expr})"
    return f"PyLong_FromLongLong({expr})"


def readptr(p, d, depth=0):
    k, v = d
    if k == "struct":
        return f"factory({v},new Handle(h->owner,{p}.getStruct(nullptr),{v}))"
    if k in ("text", "data"):
        c = "Text" if k == "text" else "Data"
        func = "PyUnicode_DecodeUTF8" if k == "text" else "PyBytes_FromStringAndSize"
        tail = ',"strict"' if k == "text" else ""
        return f"[&](){{auto x={p}.getBlob<capnp::{c}>(nullptr,0);return {func}((const char*)x.begin(),x.size(){tail});}}()"
    if k == "list":
        ek = v[0]
        es = size.get(ek, "POINTER")
        var = f"l{depth}"
        ix = f"j{depth}"
        if ek in primitive:
            val = pyvalue(f"{var}.getDataElement<{primitive[ek]}>({ix})", ek)
        elif ek == "void":
            val = "Py_NewRef(Py_None)"
        elif ek == "struct":
            val = f"factory({v[1]},new Handle(h->owner,{var}.getStructElement({ix}),{v[1]}))"
        else:
            val = readptr(f"{var}.getPointerElement({ix})", v, depth + 1)
        return f"[&]() -> PyObject* {{auto {var}={p}.getList(capnp::ElementSize::{es},nullptr); Owned out(PyList_New({var}.size())); if(!out.p)return nullptr; for(unsigned {ix}=0;{ix}<{var}.size();++{ix}){{auto* item={val};if(!item)return nullptr;PyList_SET_ITEM(out.p,{ix},item);}} return out.release();}}()"
    return "unsupported()"


def convert(v, k, enums=None):
    if k == "bool":
        return f"boolean({v})"
    if k.startswith("float"):
        return f"number({v})"
    if k == "enum":
        return f"enumerant({v}, {{{','.join(json.dumps(n) for n in enums)}}})"
    return f"integer<{primitive[k]}>({v})"


def writeptr(p, d, value, depth=0):
    k, v = d
    if k == "struct":
        s = schemas[v].node.struct
        return f"fill_{v}({p}.initStruct(capnp::_::StructSize({s.dataWordCount},{s.pointerCount})),{value});"
    if k in ("text", "data"):
        return f"set_{k}({p},{value});"
    if k == "list":
        ek = v[0]
        var = f"l{depth}"
        ix = f"j{depth}"
        seq = f"seq{depth}"
        if ek == "struct":
            s = schemas[v[1]].node.struct
            init = f"{p}.initStructList(n{depth},capnp::_::StructSize({s.dataWordCount},{s.pointerCount}))"
            put = f"fill_{v[1]}({var}.getStructElement({ix}),item);"
        else:
            init = f"{p}.initList(capnp::ElementSize::{size.get(ek, 'POINTER')},n{depth})"
            if ek in primitive:
                put = f"{var}.setDataElement<{primitive[ek]}>({ix},{convert('item', ek, v[1])});"
            elif ek == "void":
                put = ""
            else:
                put = writeptr(f"{var}.getPointerElement({ix})", v, "item", depth + 1)
        return f'{{Owned {seq}(PySequence_Tuple({value}));check({seq}.p);auto n{depth}=PyTuple_GET_SIZE({seq}.p);if(n{depth}>((1<<29)-1))throw std::runtime_error("list too large");auto {var}={init};for(unsigned {ix}=0;{ix}<n{depth};++{ix}){{auto* item=PyTuple_GET_ITEM({seq}.p,{ix});{put}}}}}'
    return 'throw std::runtime_error("unsupported pointer field");'


def clear_group(schema, context):
    # Groups share parent storage: reset only their fields, including union arm zero.
    statements = []
    if schema.node.struct.discriminantCount:
        statements.append(f"b.setDataField<uint16_t>({schema.node.struct.discriminantOffset},0);")
    for field in schema.fields.values():
        proto = field.proto
        if proto.discriminantValue not in (0, 65535):
            continue
        if proto.which() == "group":
            statements.extend(clear_group(field.schema, context))
        else:
            kind = bound(proto.slot.type, context)
            if kind in primitive:
                raw = {"float32": "uint32_t", "float64": "uint64_t"}.get(kind, primitive[kind])
                statements.append(f"b.setDataField<{raw}>({proto.slot.offset},0);")
            elif kind != "void":
                statements.append(f"b.getPointerField({proto.slot.offset}).clear();")
    return statements


coverage = []
initializers = []
views = []
for i, s in enumerate(schemas):
    getters = []
    setters = []
    props = []
    initializers.append([])
    views.append([])
    for j, (name, f) in enumerate(s.fields.items()):
        if name in {"which", "init", "view", "to_bytes"}:
            raise ValueError(f"field name conflicts with generated API: {s.node.displayName}.{name}")
        p = f.proto
        group = p.which() == "group"
        d = (
            ("struct", add(f.schema, contexts[i]))
            if group
            else desc(p.slot.type, f.schema if p.slot.type.which() in ("struct", "list", "enum") else None, contexts[i])
        )
        k, v = d
        if not group and p.slot.hadExplicitDefault and k in ("text", "data", "list", "struct", "anyPointer"):
            raise ValueError(f"explicit pointer default unsupported: {s.node.displayName}.{name}")
        checkunion = ""
        if p.discriminantValue != 65535:
            checkunion = f'if(h->reader.getDataField<uint16_t>({s.node.struct.discriminantOffset})!={p.discriminantValue})throw std::runtime_error("inactive union field");'
        if group:
            expr = f"group(h,{v})"
            write = f"fill_{v}(b,value);"
        elif k in primitive:
            default = getattr(p.slot.defaultValue, k)
            if k == "enum":
                default = default.raw if hasattr(default, "raw") else int(default)
            mask = (
                int.from_bytes(struct.pack("<f" if k == "float32" else "<d", default), "little")
                if k.startswith("float")
                else int(default)
            )
            expr = pyvalue(f"h->reader.getDataField<{primitive[k]}>({p.slot.offset},{mask}ULL)", k)
            write = f"b.setDataField<{primitive[k]}>({p.slot.offset},{convert('value', k, v)},{mask}ULL);"
        elif k == "void":
            expr = "Py_NewRef(Py_None)"
            write = ""
        else:
            expr = readptr(f"h->reader.getPointerField({p.slot.offset})", d)
            if k == "struct":
                ss = schemas[v].node.struct
                expr = f"child(h,{v},{p.slot.offset},{ss.dataWordCount},{ss.pointerCount})"
            write = writeptr(f"b.getPointerField({p.slot.offset})", d, "value")
        if k == "list":
            ek, ev = v
            es = size.get(ek, "POINTER")
            if ek in primitive:
                val = pyvalue(f"h->reader.getDataElement<{primitive[ek]}>(index)", ek)
                put = f"h->builder->setDataElement<{primitive[ek]}>(index,{convert('value', ek, ev)});"
            elif ek == "void":
                val = "Py_NewRef(Py_None)"
                put = ""
            elif ek == "struct":
                val = f"h->builder ? factory({ev},new Handle(h->owner,h->builder->getStructElement(index),{ev})) : factory({ev},new Handle(h->owner,h->reader.getStructElement(index),{ev}))"
                put = f"fill_{ev}(h->builder->getStructElement(index),value);"
            else:
                val = readptr("h->reader.getPointerElement(index)", v)
                put = writeptr("h->builder->getPointerElement(index)", v, "value")
            cpp += [
                f"PyObject* listget_{i}_{j}(ListState* h,unsigned index){{try{{return {val};}}catch(...){{return error();}}}}",
                f'int listset_{i}_{j}(ListState* h,unsigned index,PyObject* value){{try{{if(!h->builder)throw std::runtime_error("reader is immutable");{put}return 0;}}catch(...){{error();return -1;}}}}',
            ]
            pointer = f"h->builder->getPointerField({p.slot.offset})"
            if ek == "struct":
                ss = schemas[ev].node.struct
                get = f"{pointer}.getStructList(capnp::_::StructSize({ss.dataWordCount},{ss.pointerCount}),nullptr)"
                initlist = f"{pointer}.initStructList(n,capnp::_::StructSize({ss.dataWordCount},{ss.pointerCount}))"
            else:
                get = f"{pointer}.getList(capnp::ElementSize::{es},nullptr)"
                initlist = f"{pointer}.initList(capnp::ElementSize::{es},n)"
            read = f"h->reader.getPointerField({p.slot.offset}).getList(capnp::ElementSize::{es},nullptr)"
            cpp += [
                f'PyObject* view_{i}_{j}(Handle* h,bool initialize,int n){{try{{if(!h)throw std::runtime_error("uninitialized reader");if(!initialize){{{checkunion}}}if(initialize&&n<0)throw std::runtime_error("list needs size");if(h->builder)return wrap_list(ListState(h->owner,initialize?{initlist}:{get},listget_{i}_{j},listset_{i}_{j}));if(initialize)throw std::runtime_error("reader is immutable");return wrap_list(ListState(h->owner,{read},listget_{i}_{j},listset_{i}_{j}));}}catch(...){{return error();}}}}'
            ]
            views[i].append(f'if(PyUnicode_CompareWithASCIIString(name,"{name}")==0)return view_{i}_{j}(h,false,0);')
        fun = f"get_{i}_{j}"

        cpp += [
            f'PyObject* {fun}(Handle* h){{try{{if(!h)throw std::runtime_error("uninitialized reader");{checkunion}return {expr};}}catch(...){{return error();}}}}'
        ]
        cp += [
            f"static PyObject* prop_{i}_{j}(Object* o,void*){{return {fun}(o->h);}}",
            f"static int setprop_{i}_{j}(Object* o,PyObject* value,void*){{return set_{i}_{j}(o->h,value);}}",
        ]
        getters += [f'{{"{name}",(getter)prop_{i}_{j},(setter)setprop_{i}_{j},nullptr,nullptr}}']
        props += [(name, fun)]
        if p.discriminantValue != 65535:
            write = f"b.setDataField<uint16_t>({s.node.struct.discriminantOffset},{p.discriminantValue});" + write
        cpp += [
            f'int set_{i}_{j}(Handle* h,PyObject* value){{try{{if(!value)throw std::runtime_error("cannot delete field");auto b=writable(h);{write}return 0;}}catch(...){{error();return -1;}}}}'
        ]
        init = ""
        if k == "struct":
            ss = schemas[v].node.struct
            base = (
                "b"
                if group
                else f"b.getPointerField({p.slot.offset}).initStruct(capnp::_::StructSize({ss.dataWordCount},{ss.pointerCount}))"
            )
            init = (
                "".join(clear_group(f.schema, contexts[i])) if group else ""
            ) + f"return factory({v},new Handle(h->owner,{base},{v}));"
        elif k == "list":
            init = f"return view_{i}_{j}(h,true,n);"
        if init:
            if p.discriminantValue != 65535:
                init = f"b.setDataField<uint16_t>({s.node.struct.discriminantOffset},{p.discriminantValue});" + init
            initializers[i].append(f'if(PyUnicode_CompareWithASCIIString(name,"{name}")==0){{{init}}}')
        setters += [f"case {j}:{{{write}break;}}"]
    mapping = ",".join("{" + json.dumps(name) + "," + str(j) + "}" for j, name in enumerate(s.fields))
    cpp += [
        f'void fill_{i}(capnp::_::StructBuilder b,PyObject* d){{static const std::unordered_map<std::string_view,int> fields={{{mapping}}};RecursionGuard recursion;DictSnapshot snapshot(d);for(auto pair:snapshot.items){{auto* key=pair.first;auto* value=pair.second;Py_ssize_t len;const char* name=PyUnicode_AsUTF8AndSize(key,&len);check((void*)name);auto it=fields.find(std::string_view(name,len));if(it==fields.end())throw std::runtime_error("unknown field");switch(it->second){{',
        *setters,
        "}}}",
    ]
    cp += [f"static PyGetSetDef props_{i}[]={{" + ",".join(getters + ["{nullptr}"]) + "};"]
    coverage.append((i, str(s.node.displayName), props))
root = schemas[0].node.struct
cpp += [
    f"PyObject* new_message(){{try{{auto o=std::make_shared<Owner>();auto p=capnp::_::PointerHelpers<capnp::AnyPointer>::getInternalBuilder(o->builder->getRoot<capnp::AnyPointer>());return factory(0,new Handle(o,p.initStruct(capnp::_::StructSize({root.dataWordCount},{root.pointerCount})),0,true));}}catch(...){{return error();}}}}",
    'PyObject* init_field(Handle* h,PyObject* name,int n){try{if(!PyUnicode_Check(name))throw std::runtime_error("field name must be str");auto b=writable(h);switch(h->schema){',
]
for i, inits in enumerate(initializers):
    cpp += [f"case {i}:", *inits, "break;"]
cpp += [
    '}throw std::runtime_error("field cannot be initialized");}catch(...){return error();}}',
    'PyObject* view_field(Handle* h,PyObject* name){try{if(!PyUnicode_Check(name))throw std::runtime_error("field name must be str");if(!h)throw std::runtime_error("uninitialized reader");switch(h->schema){',
]
for i, cases in enumerate(views):
    cpp += [f"case {i}:", *cases, "break;"]
cpp += ['}throw std::runtime_error("not a list field");}catch(...){return error();}}']
cpp += [
    "PyObject* encode(PyObject* d){try{capnp::MallocMessageBuilder b;auto p=capnp::_::PointerHelpers<capnp::AnyPointer>::getInternalBuilder(b.getRoot<capnp::AnyPointer>());fill_0(p.initStruct(capnp::_::StructSize(ROOT_WORDS,ROOT_POINTERS)),d);auto words=capnp::messageToFlatArray(b);return PyBytes_FromStringAndSize((const char*)words.begin(),words.size()*8);}catch(...){return error();}}"
]
cp += [
    "static PyObject* read(PyObject*,PyObject* data){return parse(data);}",
    "static PyObject* write(PyObject*,PyObject* data){return encode(data);}",
    "static PyObject* create(PyObject*,PyObject*){return new_message();}",
    'static PyMethodDef api[]={{"new",create,METH_NOARGS,nullptr},{"from_bytes",read,METH_O,nullptr},{"from_dict",write,METH_O,nullptr},{nullptr}};',
    'static void cleanup(void*){clear_names();} static PyModuleDef module={PyModuleDef_HEAD_INIT,"generated_native",nullptr,-1,api,nullptr,nullptr,nullptr,cleanup};',
    'PyMODINIT_FUNC PyInit_generated_native(){if(!supported_interpreter())return nullptr;static bool initialized=false;if(initialized){PyErr_SetString(PyExc_ImportError,"native bindings cannot be reinitialized");return nullptr;}initialized=true;auto* m=PyModule_Create(&module);if(!m)return nullptr;',
]
for i, name, _ in coverage:
    cp += [
        f'types[{i}]=PyTypeObject{{PyVarObject_HEAD_INIT(nullptr,0)}};types[{i}].tp_name="generated_native.S{i}";types[{i}].tp_basicsize=sizeof(Object);types[{i}].tp_flags=Py_TPFLAGS_DEFAULT;types[{i}].tp_dealloc=(destructor)destroy;types[{i}].tp_getset=props_{i};types[{i}].tp_methods=methods;if(PyType_Ready(&types[{i}])<0)return nullptr;'
    ]
cp += ["set_factory(make_native);return m;}"]
cpp = [line.replace("factory(", "wrap(").replace("new Handle(", "Handle(") for line in cpp]
cp = [line.replace("generated_native", args.module) for line in cp]

(OUT / "accessors.h").write_text("\n".join(cpp) + "\n")
(OUT / f"{args.module}.cpp").write_text("\n".join(cp) + "\n")
(OUT / "coverage.json").write_text(json.dumps([(i, n, len(p)) for i, n, p in coverage], indent=2) + "\n")
shutil.copyfile(Path(__file__).with_name("runtime.h"), OUT / "runtime.h")
print(f"Generated {len(schemas)} structs, {sum(len(p) for _, _, p in coverage)} fields in {OUT}")
