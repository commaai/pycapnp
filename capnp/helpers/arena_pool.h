#pragma once
#include <capnp/message.h>
#include <memory>
#include <vector>
#include <cstring>

// This helper is GIL-confined; every acquire/release occurs in a Python owner.
namespace pycapnp {
struct ArenaState {
  unsigned int words, capacity, parked = 0;
  std::vector<kj::Array<capnp::word>> available;
  ArenaState(unsigned int words, unsigned int capacity): words(words), capacity(capacity) { available.reserve(capacity); }
  kj::Array<capnp::word> take() {
    if (available.empty()) {
      auto buffer = kj::heapArray<capnp::word>(words);
      std::memset(buffer.begin(), 0, buffer.size() * sizeof(capnp::word));
      return buffer;
    }
    auto result = kj::mv(available.back());
    available.pop_back();
    return result;
  }
  void give(kj::Array<capnp::word>&& buffer) {
    if (available.size() + parked < capacity) available.push_back(kj::mv(buffer));
  }
};
struct ArenaLease {
  std::shared_ptr<ArenaState> state;
  kj::Array<capnp::word> buffer;
  explicit ArenaLease(std::shared_ptr<ArenaState> state): state(state), buffer(state->take()) {}
  ~ArenaLease() { state->give(kj::mv(buffer)); }
};
// Base destruction is reversed: MallocMessageBuilder zeros its used words before
// ArenaLease returns the buffer. The shared state outlives the Python pool.
class PooledBuilder final: private ArenaLease, public capnp::MallocMessageBuilder {
public:
  explicit PooledBuilder(std::shared_ptr<ArenaState> state):
      ArenaLease(state), capnp::MallocMessageBuilder(ArenaLease::buffer.asPtr()) {}
};
class ArenaPool {
  std::shared_ptr<ArenaState> state;
  bool recycleBuilder, resetArena;
  std::vector<void*> storage;
  std::vector<PooledBuilder*> ready;
public:
  ArenaPool(unsigned int words, unsigned int capacity, bool recycleBuilder, bool resetArena):
      state(std::make_shared<ArenaState>(words, capacity)), recycleBuilder(recycleBuilder), resetArena(resetArena) {
    storage.reserve(capacity);
    ready.reserve(capacity);
  }
  ~ArenaPool() {
    for (auto* ptr: ready) { --state->parked; delete ptr; }
    for (void* ptr: storage) ::operator delete(ptr);
  }
  size_t cachedBufferBytes() const { return (state->available.size() + ready.size()) * state->words * sizeof(capnp::word); }
  capnp::MessageBuilder* acquire() {
    if (!ready.empty()) { auto* ptr = ready.back(); ready.pop_back(); --state->parked; return ptr; }
    if (storage.empty()) return new PooledBuilder(state);
    void* ptr = storage.back();
    storage.pop_back();
    try { return new (ptr) PooledBuilder(state); }
    catch (...) { ::operator delete(ptr); throw; }
  }
  void release(capnp::MessageBuilder* message) {
    auto* ptr = static_cast<PooledBuilder*>(message);
    if (resetArena && ready.size() < state->capacity && ptr->resetSingleSegment()) {
      ++state->parked;
      while (state->available.size() + state->parked > state->capacity) state->available.pop_back();
      ready.push_back(ptr);
      return;
    }
    if (!recycleBuilder || storage.size() >= state->capacity) { delete ptr; return; }
    ptr->~PooledBuilder();
    storage.push_back(ptr);
  }
};
}
