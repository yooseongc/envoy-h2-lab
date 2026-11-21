"""Manage one run-scoped reverse mitmproxy inside its network namespace."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

folder, upstream, mode, insecure, keylog = sys.argv[1:]
folder = Path(folder)
with tempfile.TemporaryDirectory() as conf:
    env = os.environ.copy()
    if keylog == "yes":
        env["SSLKEYLOGFILE"] = str(folder / "proxy.keys")
    listener = "regular" if mode == "forward" else "reverse:" + upstream
    command = ["mitmdump", "--mode", listener, "--listen-port", "8082",
               "--set", "confdir=" + conf, "--set", "keep_host_header=true"]
    if mode == "reverse":
        env["LAB_REVERSE_ROUTES"] = str(folder / "reverse-routes.json")
        command.extend(["-s", "/lab/mitm_routes.py", "--set", "connection_strategy=lazy",
                        "--set", "upstream_cert=false"])
    if (folder/"origin-trust.pem").exists():
        command.extend(["--set", "ssl_verify_upstream_trusted_ca=" + str(folder/"origin-trust.pem")])
    if insecure == "yes":
        command.append("--ssl-insecure")
    with (folder / "mitm.log").open("wb") as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 90
            ready = folder / "mitm.ready"
            while proc.poll() is None and time.monotonic() < deadline and not (folder / "mitm.stop").exists():
                if not ready.exists() and Path(conf, "mitmproxy-ca-cert.pem").is_file():
                    try:
                        with socket.create_connection(("127.0.0.1",8082),timeout=.2):
                            pass
                    except OSError:
                        pass
                    else:
                        shutil.copyfile(Path(conf,"mitmproxy-ca-cert.pem"),folder/"client-ca.pem")
                        ready.touch()
                time.sleep(.1)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            (folder / "mitm.done").touch()
