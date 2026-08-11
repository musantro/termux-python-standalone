#!/usr/bin/env bash
set -euo pipefail

python_bin=${1:-python}

if [[ ! -x "$python_bin" ]]; then
	printf 'Python executable is not executable: %s\n' "$python_bin" >&2
	exit 2
fi

"$python_bin" - <<'PY'
import ctypes
import platform
import sqlite3
import ssl
import sys
import sysconfig
import tempfile
import venv
from pathlib import Path

print(f"version: {sys.version.split()[0]}")
print(f"executable: {sys.executable}")
print(f"platform: {sysconfig.get_platform()}")
print(f"machine: {platform.machine()}")
print(f"sqlite: {sqlite3.sqlite_version}")
print(f"openssl: {ssl.OPENSSL_VERSION}")
print(f"ctypes: {ctypes.sizeof(ctypes.c_void_p) * 8}-bit")

with tempfile.TemporaryDirectory(prefix="termux-python-smoke-") as directory:
    venv_dir = Path(directory) / "venv"
    venv.EnvBuilder(with_pip=False, clear=True).create(venv_dir)
    venv_python = venv_dir / "bin" / "python"
    assert venv_python.exists(), venv_python
    print(f"venv: {venv_python}")
PY
