"""Local companion for the lab UI's PCAP save buttons."""
import json
import os
import re
import shutil
import socket
import tempfile
import tkinter as tk
from tkinter import filedialog
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CAPTURES = Path(__file__).resolve().parents[1] / "captures"
ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}


def downloads_folder():
    if os.name != 'nt':
        path = Path.home() / 'Downloads'
        return path if path.is_dir() else Path.home()
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
        try:
            path, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
        except FileNotFoundError:
            return Path.home() / "Downloads"
    return Path(os.path.expandvars(path))


def save_capture(run, leg):
    if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", run) or leg not in ("front","middle","back","client.keys","proxy.keys","flows.mitm","middle-decrypted.pcapng","back-decrypted.pcapng"):
        raise ValueError("잘못된 캡처 이름입니다.")
    folder = CAPTURES / run
    pcap = leg in ("front","middle","back")
    source = folder / (leg+".pcap" if pcap else leg)
    marker = folder / (leg+".done" if pcap else "url-result.json")
    if not marker.is_file() or not source.is_file():
        raise ValueError("완료된 캡처를 찾을 수 없습니다.")
    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        selected = filedialog.asksaveasfilename(
            parent=window, title="실험 파일 다른 이름으로 저장", initialdir=str(downloads_folder()),
            initialfile=f"{run}-{source.name}", defaultextension=source.suffix,
            filetypes=[(source.name,"*"+source.suffix)], confirmoverwrite=True)
    finally:
        window.destroy()
    if not selected:
        return None
    target = Path(selected)
    if target.suffix.lower() != source.suffix:
        raise ValueError(f"{source.suffix} 확장자로 저장하세요.")
    if source.resolve() == target.resolve():
        return str(source)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data):
        payload = json.dumps(data).encode()
        self.send_response(code)
        origin = self.headers.get("Origin")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        return (self.path in ("/save", "/save-as") and self.headers.get("Host") == "127.0.0.1:8766"
                and self.headers.get("Origin") in ORIGINS)

    def do_OPTIONS(self):
        self.reply(200 if self.allowed() else 403, {})

    def do_GET(self):
        self.reply(200, {"service": "envoy-h2-save", "root": str(CAPTURES), "version": 4}) if self.path == "/health" and self.headers.get("Host") == "127.0.0.1:8766" else self.reply(404, {})

    def do_POST(self):
        if not self.allowed() or self.headers.get_content_type() != "application/json":
            return self.reply(403, {})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 512:
                raise ValueError("invalid request length")
            data = json.loads(self.rfile.read(size))
            path = save_capture(data["run"], data["leg"])
        except (ValueError, KeyError, TypeError, OSError, tk.TclError) as error:
            return self.reply(400, {"error": str(error)})
        self.reply(200, {"path": path})


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1", 8766), Handler, bind_and_activate=False) as server:
        server.allow_reuse_address = False
        if os.name == 'nt':
            server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        server.server_bind()
        server.server_activate()
        server.serve_forever()
