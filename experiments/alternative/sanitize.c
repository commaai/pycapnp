/* Embed Python so the sanitizer exercises list/tuple creation and failure
 * cleanup too. */
#include "wire.c"
#include <stdio.h>
#include <stdlib.h>
static uint64_t state = 19;
static uint64_t random64(void) {
  state ^= state << 13;
  state ^= state >> 7;
  state ^= state << 17;
  return state;
}
int main(int argc, char **argv) {
  if (argc != 2)
    return 2;
  FILE *f = fopen(argv[1], "rb");
  if (!f)
    return 2;
  unsigned char *seeds[100];
  size_t sizes[100];
  size_t count = 0;
  while (count < 100) {
    uint64_t size;
    if (fread(&size, 8, 1, f) != 1)
      break;
    if (size > 10000000)
      return 2;
    seeds[count] = malloc(size);
    sizes[count] = size;
    if (fread(seeds[count], size, 1, f) != 1)
      return 2;
    count++;
  }
  fclose(f);
  if (!count)
    return 2;
  Py_Initialize();
  for (size_t i = 0; i < 100000; i++) {
    size_t index = random64() % count, n = sizes[index];
    PyObject *data = PyBytes_FromStringAndSize((char *)seeds[index], n);
    if (!data)
      return 3;
    unsigned char *p = (unsigned char *)PyBytes_AS_STRING(data);
    for (size_t j = 0, changes = 1 + random64() % 5; j < changes; j++)
      p[random64() % n] = random64();
    PyObject *out = project_event(NULL, data);
    if(out) {
      Message message; Struct root;
      if(framing(p,n,&message) && resolve(&message,message.segments[0],0,&root)) {
        unsigned kind=scalar(root,DISCRIMINANT_OFFSET,2,0);
        PyObject *encoded=kind==CAR_DISCRIMINANT?write_car(NULL,out):kind==CAN_DISCRIMINANT?write_can(NULL,out):kind==PLAN_DISCRIMINANT?write_plan(NULL,out):NULL;
        Py_XDECREF(encoded);
      }
    }
    Py_XDECREF(out);
    PyErr_Clear();
    Result result;
    project(p, n, &result);
    Py_DECREF(data);
  }
  for (size_t i = 0; i < count; i++)
    free(seeds[i]);
  Py_Finalize();
  puts("ASan/UBSan: 100000 mixed-type mutations completed");
  return 0;
}
