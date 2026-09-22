from pathlib import Path
import subprocess
from setuptools import Extension, setup
from Cython.Build import cythonize

root = Path(__file__).resolve().parents[2]
archives = list((root / "build").glob("temp*/capnproto/libcapnp-vendored.a"))
if archives:
    archive = archives[0]
else:
    build = root / "build/generated-capnproto"
    subprocess.run(
        ["cmake", "-S", str(root / "vendor/capnproto"), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"], check=True
    )
    subprocess.run(["cmake", "--build", str(build), "--parallel", "2"], check=True)
    archive = build / "libcapnp-vendored.a"
kwargs = dict(
    depends=["runtime.h", "accessors.h", "generated_consumer.h"],
    include_dirs=[str(root / "vendor/capnproto/src"), str(Path(__file__).parent)],
    extra_objects=[str(archive)],
    extra_compile_args=["-std=c++17", "-O3", "-g0"],
    language="c++",
)
setup(
    name="generated-experiment",
    ext_modules=cythonize(
        [
            Extension("generated_cython", ["generated_cython.pyx"], **kwargs),
            Extension("generated_native", ["generated_native.cpp"], **kwargs),
        ],
        compiler_directives={"language_level": 3},
    ),
)
