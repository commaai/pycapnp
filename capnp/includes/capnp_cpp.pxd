# schema.capnp.cpp.pyx
# distutils: language = c++
cdef extern from "capnp/helpers/checkCompiler.h":
    pass

from capnp.helpers.non_circular cimport (
    c_reraise_kj_exception as reraise_kj_exception,
)
from capnp.includes.schema_cpp cimport (
    Node, Data, Field as SchemaField, Enumerant as SchemaEnumerant, MessageBuilder, MessageReader, ReaderOptions,
)
from capnp.includes.types cimport *

cdef extern from "capnp/common.h" namespace " ::capnp":
    enum Void:
        VOID " ::capnp::VOID"
    cdef cppclass MessageSize nogil:
        uint64_t wordCount
        uint capCount

cdef extern from "capnp/common.h":
    int CAPNP_VERSION_MAJOR
    int CAPNP_VERSION_MINOR
    int CAPNP_VERSION_MICRO
    int CAPNP_VERSION

cdef extern from "kj/string.h" namespace " ::kj":
    cdef cppclass StringPtr nogil:
        StringPtr()
        StringPtr(char *)
        StringPtr(char *, size_t)
        char* cStr()
        size_t size()
        char* begin()
    cdef cppclass String nogil:
        char* cStr()
        size_t size()
        char* begin()

cdef extern from "kj/exception.h" namespace " ::kj":
    cdef cppclass Exception nogil:
        Exception(Exception)
        char* getFile()
        int getLine()
        int getType()
        StringPtr getDescription()

cdef extern from "kj/string-tree.h" namespace " ::kj":
    cdef cppclass StringTree nogil:
        String flatten()

cdef extern from "kj/common.h" namespace " ::kj":
    cdef cppclass Maybe[T] nogil:
        T& orDefault(T&)
    cdef cppclass ArrayPtr[T] nogil:
        ArrayPtr()
        ArrayPtr(T *, size_t size)
        T* begin()
        size_t size()
        T& operator[](size_t index)

cdef extern from "capnp/schema.h" namespace " ::capnp":
    cdef cppclass SchemaType" ::capnp::Type" nogil:
        cbool isList()
        cbool isEnum()
        cbool isStruct()
        cbool isData()

        StructSchema asStruct() except +reraise_kj_exception
        EnumSchema asEnum() except +reraise_kj_exception
        ListSchema asList() except +reraise_kj_exception

    cdef cppclass Schema nogil:
        Node.Reader getProto() except +reraise_kj_exception
        StructSchema asStruct() except +reraise_kj_exception
        EnumSchema asEnum() except +reraise_kj_exception
        ConstSchema asConst() except +reraise_kj_exception
        Schema getDependency(uint64_t id) except +reraise_kj_exception

    cdef cppclass StructSchema(Schema) nogil:
        cppclass Field nogil:
            SchemaField.Reader getProto()
            StructSchema getContainingStruct()
            uint getIndex()
            SchemaType getType()

        cppclass FieldList nogil:
            uint size()
            Field operator[](uint index)

        cppclass FieldSubset nogil:
            uint size()
            Field operator[](uint index)

        FieldList getFields()
        FieldSubset getUnionFields()
        FieldSubset getNonUnionFields()

        Field getFieldByName(char * name) except +reraise_kj_exception

        cbool operator == (StructSchema)

    cdef cppclass EnumSchema nogil:
        cppclass Enumerant nogil:
            SchemaEnumerant.Reader getProto()
            EnumSchema getContainingEnum()
            uint16_t getOrdinal()

        cppclass EnumerantList nogil:
            uint size()
            Enumerant operator[](uint index)

        EnumerantList getEnumerants()
        Enumerant getEnumerantByName(char * name)
        Node.Reader getProto()

    cdef cppclass ListSchema nogil:
        SchemaType getElementType()


    cdef cppclass ConstSchema:
        pass

cdef extern from "capnp/dynamic.h" namespace " ::capnp":
    cdef cppclass DynamicValueForward" ::capnp::DynamicValue" nogil:
        cppclass Reader nogil:
            pass
        cppclass Builder nogil:
            pass

    enum Type:
        TYPE_UNKNOWN " ::capnp::DynamicValue::UNKNOWN"
        TYPE_VOID " ::capnp::DynamicValue::VOID"
        TYPE_BOOL " ::capnp::DynamicValue::BOOL"
        TYPE_INT " ::capnp::DynamicValue::INT"
        TYPE_UINT " ::capnp::DynamicValue::UINT"
        TYPE_FLOAT " ::capnp::DynamicValue::FLOAT"
        TYPE_TEXT " ::capnp::DynamicValue::TEXT"
        TYPE_DATA " ::capnp::DynamicValue::DATA"
        TYPE_LIST " ::capnp::DynamicValue::LIST"
        TYPE_ENUM " ::capnp::DynamicValue::ENUM"
        TYPE_STRUCT " ::capnp::DynamicValue::STRUCT"

    cdef cppclass DynamicStruct nogil:
        cppclass Reader nogil:
            DynamicValueForward.Reader get(char *) except +reraise_kj_exception
            DynamicValueForward.Reader getByField"get"(StructSchema.Field) except +reraise_kj_exception
            bint has(char *) except +reraise_kj_exception
            StructSchema getSchema()
            Maybe[StructSchema.Field] which()
            MessageSize totalSize()

    cdef cppclass DynamicStruct_Builder" ::capnp::DynamicStruct::Builder" nogil:
        # Need to flatten this class out, since nested C++ classes cause havoc with cython fused types
        DynamicStruct_Builder()
        DynamicStruct_Builder(DynamicStruct_Builder &)
        DynamicValueForward.Builder get(char *) except +reraise_kj_exception
        DynamicValueForward.Builder getByField"get"(StructSchema.Field) except +reraise_kj_exception
        bint has(char *) except +reraise_kj_exception
        void set(char *, DynamicValueForward.Reader) except +reraise_kj_exception
        void setByField"set"(StructSchema.Field, DynamicValueForward.Reader) except +reraise_kj_exception
        DynamicValueForward.Builder init(char *, uint size) except +reraise_kj_exception
        DynamicValueForward.Builder init(char *) except +reraise_kj_exception
        StructSchema getSchema()
        Maybe[StructSchema.Field] which()
        DynamicStruct.Reader asReader()
        MessageSize totalSize()

cdef extern from "capnp/dynamic.h" namespace " ::capnp":
    cdef cppclass DynamicEnum nogil:
        uint16_t getRaw()
        Maybe[EnumSchema.Enumerant] getEnumerant()

    cdef cppclass DynamicList nogil:
        cppclass Reader nogil:
            DynamicValueForward.Reader operator[](uint) except +reraise_kj_exception
            uint size()
        cppclass Builder nogil:
            Builder()
            Builder(Builder &)
            DynamicValueForward.Builder operator[](uint) except +reraise_kj_exception
            uint size()
            void set(uint index, DynamicValueForward.Reader value) except +reraise_kj_exception
            DynamicValueForward.Builder init(uint index, uint size) except +reraise_kj_exception
            StructSchema getStructElementType'getSchema().getStructElementType'()
            DynamicList.Reader asReader() except +reraise_kj_exception

cdef extern from "capnp/dynamic.h" namespace " ::capnp":
    cdef cppclass DynamicValue nogil:
        cppclass Reader nogil:
            Reader()
            Reader(Void value)
            Reader(cbool value)
            Reader(char value)
            Reader(short value)
            Reader(int value)
            Reader(long value)
            Reader(long long value)
            Reader(unsigned char value)
            Reader(unsigned short value)
            Reader(unsigned int value)
            Reader(unsigned long value)
            Reader(unsigned long long value)
            Reader(float value)
            Reader(double value)
            Reader(char* value)
            Reader(StringPtr value)
            Reader(DynamicList.Reader& value)
            Reader(DynamicEnum value)
            Reader(DynamicStruct.Reader& value)
            Type getType()
            int64_t asInt"as<int64_t>"()
            uint64_t asUint"as<uint64_t>"()
            bint asBool"as<bool>"()
            double asDouble"as<double>"()
            StringPtr asText"as< ::capnp::Text>"()
            DynamicList.Reader asList"as< ::capnp::DynamicList>"()
            DynamicStruct.Reader asStruct"as< ::capnp::DynamicStruct>"()
            DynamicEnum asEnum"as< ::capnp::DynamicEnum>"()
            Data.Reader asData"as< ::capnp::Data>"()

        cppclass Builder nogil:
            Type getType()
            int64_t asInt"as<int64_t>"()
            uint64_t asUint"as<uint64_t>"()
            bint asBool"as<bool>"()
            double asDouble"as<double>"()
            StringPtr asText"as< ::capnp::Text>"()
            DynamicList.Builder asList"as< ::capnp::DynamicList>"()
            DynamicStruct_Builder asStruct"as< ::capnp::DynamicStruct>"()
            DynamicEnum asEnum"as< ::capnp::DynamicEnum>"()
            Data.Builder asData"as< ::capnp::Data>"()


cdef extern from "capnp/schema-parser.h" namespace " ::capnp":
    cdef cppclass ParsedSchema(Schema) nogil:
        ParsedSchema getNested(char * name) except +reraise_kj_exception
    cdef cppclass SchemaParser nogil:
        SchemaParser()
        ParsedSchema parseDiskFile(char * displayName, char * diskPath, ArrayPtr[StringPtr] importPath)
