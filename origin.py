import asyncio
import json
import socket
import subprocess
import tempfile
from pathlib import Path

from hypercorn.asyncio import serve
from hypercorn.config import Config


async def origin(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    headers = {k.decode().lower(): v.decode("latin1") for k, v in scope["headers"]}
    await asyncio.sleep(0.6)
    path = scope["raw_path"].decode("ascii")
    if scope["query_string"] and "?" not in path:
        path += "?" + scope["query_string"].decode("ascii")
    fields = dict(server=socket.gethostname(), server_ip=scope["server"][0],
                  client=headers.get("x-lab-client"), path=path, xff=headers.get("x-forwarded-for"),
                  origin_protocol="HTTP/" + scope["http_version"],
                  reverse_received=headers.get("x-reverse-protocol"), peer=scope["client"][0])
    body = json.dumps(fields).encode()
    await send({"type":"http.response.start", "status":200,
                "headers":[(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type":"http.response.body", "body":body})


if __name__ == "__main__":
    config = Config()
    with tempfile.TemporaryDirectory() as directory:
        config.certfile = directory + "/origin.pem"
        config.keyfile = directory + "/origin.key"
        address = socket.gethostbyname(socket.gethostname())
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "365", "-subj", f"/CN=origin-{address}", "-addext",
                        f"subjectAltName=DNS:origin,IP:{address}", "-keyout", config.keyfile,
                        "-out", config.certfile], check=True)
        Path("/tmp/lab-origin.pem").write_bytes(Path(config.certfile).read_bytes())
        config.bind = ["0.0.0.0:8443"]
        config.insecure_bind = ["0.0.0.0:8000"]
        asyncio.run(serve(origin, config))
