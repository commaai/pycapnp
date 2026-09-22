"Build the bundled capnp distribution"

import subprocess
import os
import shutil
import sys


def build_libcapnp(bundle_dir, build_dir):  # noqa: C901
    """
    Build capnproto
    """
    bundle_dir = os.path.abspath(bundle_dir)
    capnp_dir = os.path.join(bundle_dir, "capnproto-c++")
    build_dir = os.path.abspath(build_dir)
    tmp_dir = os.path.join(capnp_dir, "build")

    # Clean the tmp build directory every time
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.mkdir(tmp_dir)

    cxxflags = os.environ.get("CXXFLAGS", None)
    ldflags = os.environ.get("LDFLAGS", None)
    os.environ["CXXFLAGS"] = (cxxflags or "") + " -O2 -DNDEBUG"
    os.environ["LDFLAGS"] = ldflags or ""

    # Enable ninja for compilation if available
    build_type = []
    if shutil.which("ninja"):
        build_type = ["-G", "Ninja"]

    if not shutil.which("cmake"):
        raise RuntimeError("Could not find cmake in your path!")

    args = [
        "cmake",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=1",
        "-DBUILD_TESTING=OFF",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DWITH_OPENSSL=OFF",
        "-DCMAKE_INSTALL_PREFIX:PATH={}".format(build_dir),
        capnp_dir,
    ]
    args.extend(build_type)
    conf = subprocess.Popen(args, cwd=tmp_dir, stdout=sys.stdout)
    returncode = conf.wait()
    if returncode != 0:
        raise RuntimeError("CMake failed {}".format(returncode))

    # Run build through cmake
    args = [
        "cmake",
        "--build",
        ".",
        "--target",
        "install",
    ]
    build = subprocess.Popen(args, cwd=tmp_dir, stdout=sys.stdout)
    returncode = build.wait()
    if cxxflags is None:
        del os.environ["CXXFLAGS"]
    else:
        os.environ["CXXFLAGS"] = cxxflags
    if ldflags is None:
        del os.environ["LDFLAGS"]
    else:
        os.environ["LDFLAGS"] = ldflags
    if returncode != 0:
        raise RuntimeError("capnproto compilation failed: {}".format(returncode))
