"""Drive a local ioGAS 8.3 through its gRPC server (localhost only; no data leaves the machine).

How it works (LOG.md 2026-11-05, ioGAS automation probes 1 and 2):
- ioGAS started with the launch flag `-gaslink2` (listed as "unsupported" in GAS.jar `config/help.txt`) serves
  gRPC on 127.0.0.1:<serverPort> (25000 by default, from `gaslink2.ini`).
- The `.proto` files ship inside GAS.jar. `ensure_stubs()` extracts them and generates Python stubs into
  `.cache/iogas_grpc/` (gitignored), so no IMDEX file is copied into the repo.
- The ioGAS desktop launcher (ioGAS-64.exe) allows one instance only, so `start_server()` runs the bundled JRE
  directly. That instance reads the same licence file as the desktop app.

Typical use:
    with IoGAS() as g:                    # reuses a running server or starts one (and stops it afterwards)
        g.open_gas("x.gas")               # open data from a .gas (needed for Save As in a workflow)
        g.run_workflow("wf.xml")          # returns {"columns": [...], "files": [...]}
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from importlib import import_module
from pathlib import Path

from src.paths import ROOT

IOGAS_HOME = Path(os.environ.get("IOGAS_HOME", r"C:\Program Files\IMDEX\ioGAS-64.8.3"))
STUB_DIR = ROOT / ".cache" / "iogas_grpc"
PROTOS = ["gas-common", "gaslink-common", "gaslink2", "server", "classification", "controller"]
DEFAULT_PORT = 25000
SERVER_FLAGS = ["-gaslink2", "-notracker", "-nogaslink", "-noacquire"]


class IoGASError(RuntimeError):
    pass


def jar_path(home: Path = IOGAS_HOME) -> Path:
    p = Path(home) / "libs" / "GAS.jar"
    if not p.exists():
        raise FileNotFoundError(f"ioGAS not found at {home} (set IOGAS_HOME)")
    return p


def server_port() -> int:
    """serverPort from the user's gaslink2.ini, else 25000."""
    ini = Path(os.environ.get("APPDATA", "")) / "ioGAS" / "userConfig" / "gaslink2.ini"
    if ini.exists():
        for line in ini.read_text(errors="replace").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "serverPort" and v.strip().isdigit():
                return int(v.strip())
    return DEFAULT_PORT


def ensure_stubs(home: Path = IOGAS_HOME, out: Path = STUB_DIR) -> Path:
    """Generate Python gRPC stubs from the protos in the local GAS.jar (once per jar version)."""
    jar = jar_path(home)
    stamp = f"{jar.stat().st_size}:{int(jar.stat().st_mtime)}"
    if (out / "STAMP").exists() and (out / "STAMP").read_text() == stamp:
        return out
    import grpc_tools
    from grpc_tools import protoc

    if out.exists():
        shutil.rmtree(out)
    src = out / "proto"
    src.mkdir(parents=True)
    with zipfile.ZipFile(jar) as z:
        for name in PROTOS:
            (src / f"{name}.proto").write_bytes(z.read(f"proto/{name}.proto"))
    well_known = Path(grpc_tools.__file__).parent / "_proto"
    args = ["protoc", f"-I{src}", f"-I{well_known}", f"--python_out={out}", f"--grpc_python_out={out}"]
    rc = protoc.main(args + [str(src / f"{n}.proto") for n in PROTOS])
    if rc != 0:
        raise IoGASError(f"protoc failed ({rc})")
    (out / "STAMP").write_text(stamp)
    return out


def _stubs():
    d = str(ensure_stubs())
    if d not in sys.path:
        sys.path.insert(0, d)  # generated modules import each other by bare name
    return import_module("gas_common_pb2"), import_module("server_pb2_grpc")


def is_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def start_server(port: int | None = None, home: Path = IOGAS_HOME, timeout: float = 120,
                 log: Path | None = None) -> subprocess.Popen:
    """Start a second ioGAS window with the gRPC server on, and wait until the port answers."""
    port = port or server_port()
    if is_listening(port):
        raise IoGASError(f"port {port} already in use")
    home = Path(home)
    jvm = (home / "jvmArgs.properties").read_text().split("=", 1)[1].split()
    cmd = [str(home / "jre" / "bin" / "java.exe"), *jvm, "-Xmx6g", f"-Dinstall4j.appDir={home}",
           "-cp", str(jar_path(home)), "net.ioglobal.gas.main.Main", "-appdir", str(home), "-brand", "ioGAS",
           *SERVER_FLAGS]
    out = open(log, "w") if log else subprocess.DEVNULL
    proc = subprocess.Popen(cmd, cwd=home, stdout=out, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise IoGASError(f"ioGAS exited early with code {proc.returncode}")
        if is_listening(port):
            return proc
        time.sleep(1)
    proc.kill()
    raise IoGASError(f"ioGAS gRPC server did not start within {timeout:.0f} s")


class IoGAS:
    """Client for the ioGAS gRPC `Server` service. As a context manager it starts ioGAS only if needed."""

    def __init__(self, port: int | None = None, start: bool = True, log: Path | None = None):
        self.port = port or server_port()
        self._start, self._log, self.proc = start, log, None
        self._c, sg = _stubs()
        import grpc
        self._channel = grpc.insecure_channel(f"127.0.0.1:{self.port}")
        self._stub = sg.ServerStub(self._channel)

    def __enter__(self):
        if not is_listening(self.port):
            if not self._start:
                raise IoGASError(f"no ioGAS gRPC server on port {self.port}")
            self.proc = start_server(self.port, log=self._log)
        return self

    def __exit__(self, *exc):
        self._channel.close()
        if self.proc is not None:
            self.proc.kill()  # test instance only; it holds no user work
            self.proc.wait(timeout=30)

    def _check(self, what: str, status: int):
        name = self._c.ReturnCode.Name(status)
        if name != "success":
            raise IoGASError(f"{what}: {name}")

    def open_gas(self, path: str | Path, timeout: float = 120):
        r = self._stub.OpenGASFile(self._c.File(fileName=str(Path(path).resolve())), timeout=timeout)
        self._check(f"OpenGASFile {path}", r.status)

    def open_csv(self, path: str | Path, timeout: float = 120):
        """Open a CSV. Note: a workflow 'Save As' fails on data opened this way (use open_gas)."""
        r = self._stub.OpenCSVFile(self._c.File(fileName=str(Path(path).resolve())), timeout=timeout)
        self._check(f"OpenCSVFile {path}", r.status)
        return r.specialColumns

    def run_workflow(self, path: str | Path, timeout: float = 600) -> dict:
        """Run a workflow file. Raises if any operation failed; returns created columns and exported files."""
        r = self._stub.RunWorkflow(self._c.File(fileName=str(Path(path).resolve())), timeout=timeout)
        self._check(f"RunWorkflow {path}", r.status)
        return {"columns": list(r.outputColumns), "files": list(r.filenames)}
