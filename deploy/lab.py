"""Offline lifecycle commands for the local Docker lab (Python standard library)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WORKERS = ROOT / ".stopped-workers.json"
HELPER = ROOT / "windows" / "save_capture.py"
WINDOWS = os.name == "nt"


def docker(*args, output=False):
    result = subprocess.run(["docker", *args], cwd=ROOT, check=True, text=True,
                            stdout=subprocess.PIPE if output else None)
    return result.stdout.strip() if output else None


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as data:
        for block in iter(lambda: data.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def install():
    manifest = json.loads((ROOT / "images.json").read_text())
    archive = ROOT / "images.tar.gz"
    if digest(archive) != manifest["sha256"]:
        raise ValueError("images.tar.gz checksum mismatch")
    platform = docker("version", "--format", "{{.Server.Os}}/{{.Server.Arch}}", output=True)
    if platform != manifest["platform"]:
        raise ValueError(f"Archive requires {manifest['platform']}; Docker engine is {platform}")
    docker("compose", "version")
    docker("load", "--input", str(archive))
    for tag, expected in manifest["images"].items():
        if docker("image", "inspect", "--format", "{{.Id}}", tag, output=True) != expected:
            raise ValueError(f"Unexpected image ID for {tag}")
    (ROOT / "captures").mkdir(exist_ok=True)


def health(port, path):
    try:
        with urlopen(f"http://127.0.0.1:{port}/{path}", timeout=2) as r:
            return json.load(r)
    except (OSError, ValueError):
        return {}


def helper_matches():
    info = health(8766, "health")
    return (info.get("service") == "envoy-h2-save" and info.get("version") == 4
            and Path(info.get("root", "")) == ROOT / "captures")


def start_helper():
    if helper_matches():
        return
    if not WINDOWS and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        print("Headless session: capture files are in", ROOT / "captures")
        return
    import tkinter
    process = subprocess.Popen([sys.executable, str(HELPER)], cwd=ROOT,
                               creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0,
                               start_new_session=not WINDOWS, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if helper_matches():
            return
        if process.poll() is not None:
            break
        time.sleep(.15)
    raise RuntimeError("Save dialog helper could not bind to 127.0.0.1:8766")


def check_project():
    containers = docker("ps", "-aq", "--filter", "label=com.docker.compose.project=envoy-h2-lab",
                        "--filter", "label=com.docker.compose.service=ui", output=True).split()
    for cid in containers:
        mounts = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", cid, output=True))
        directory = mounts.get("com.docker.compose.project.working_dir")
        if directory and Path(directory).resolve() != ROOT:
            raise ValueError(f"Another copy of the lab owns this Compose project: {directory}")


def worker_ids(running=False):
    return docker("ps", "-q" if running else "-aq", "--no-trunc", "--filter",
                  "label=lab.project=envoy-h2-lab", output=True).split()


def start():
    check_project()
    (ROOT / "captures").mkdir(exist_ok=True)
    docker("compose", "up", "-d", "--pull", "never", "--no-build")
    if WORKERS.exists():
        restore = sorted(set(json.loads(WORKERS.read_text())) & set(worker_ids()))
        if restore:
            docker("start", *restore)
        WORKERS.unlink()
    for _ in range(60):
        if "clients" in health(8765, "topology"):
            start_helper()
            print("UI: http://127.0.0.1:8765")
            return
        time.sleep(.5)
    raise RuntimeError("UI startup timed out; inspect docker compose logs ui")


def stop():
    check_project()
    running = worker_ids(running=True)
    if running:
        previous = json.loads(WORKERS.read_text()) if WORKERS.exists() else []
        temp = WORKERS.with_suffix(".tmp")
        temp.write_text(json.dumps(sorted(set(previous + running))))
        temp.replace(WORKERS)
    docker("compose", "stop")
    if running:
        docker("stop", *running)
    if helper_matches():
        if WINDOWS:
            command = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                       "Where-Object { $_.CommandLine -match ([regex]::Escape($env:LAB_SAVE_HELPER) + "
                       "'\"?\\s*$') } | ForEach-Object { Stop-Process -Id $_.ProcessId }")
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                           env={**os.environ, "LAB_SAVE_HELPER": str(HELPER)}, check=True)
        else:
            import signal
            for entry in Path("/proc").glob("[0-9]*/cmdline"):
                try:
                    args = entry.read_bytes().rstrip(b"\0").split(b"\0")
                    if len(args) == 2 and os.fsdecode(args[1]) == str(HELPER):
                        os.kill(int(entry.parent.name), signal.SIGTERM)
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "start", "stop"))
    try:
        {"install": install, "start": start, "stop": stop}[parser.parse_args().action]()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
