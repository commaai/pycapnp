#pragma once
#include <stdint.h>
typedef struct {
  uint64_t timestamp;
  double speed, angle, wheel;
  unsigned valid, gear;
} Result;
