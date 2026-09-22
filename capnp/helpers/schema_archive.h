#pragma once
#include <capnp/schema-parser.h>
#include <capnp/schema-loader.h>
#include <capnp/serialize.h>
#include <cstring>
namespace pycapnp {
inline kj::Array<capnp::word> exportSchemas(capnp::SchemaParser& parser) {
  auto schemas = parser.getAllLoaded();
  capnp::MallocMessageBuilder message;
  auto nodes = message.initRoot<capnp::List<capnp::schema::Node>>(schemas.size());
  for (unsigned int i = 0; i < schemas.size(); ++i) nodes.setWithCaveats(i, schemas[i].getProto());
  return capnp::messageToFlatArray(message);
}
class SchemaArchive {
  capnp::SchemaLoader loader;
public:
  SchemaArchive(const char* data, size_t size) {
    KJ_REQUIRE(size > 0 && size % sizeof(capnp::word) == 0, "invalid schema archive length");
    auto aligned = kj::heapArray<capnp::word>(size / sizeof(capnp::word));
    std::memcpy(aligned.begin(), data, size);
    capnp::FlatArrayMessageReader reader(aligned);
    for (auto node: reader.getRoot<capnp::List<capnp::schema::Node>>()) loader.load(node);
  }
  capnp::Schema get(uint64_t id) { return loader.get(id); }
};
}
