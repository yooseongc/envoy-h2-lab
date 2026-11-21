"""Write the captured frames and the run's TLS secrets to one Wireshark file."""
import base64
from datetime import datetime, timezone
import ipaddress
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import yaml


def export_trace(folder, leg):
    dest = folder / f"{leg}-decrypted.pcapng"
    temp = dest.with_suffix(".tmp")
    try:
        subprocess.run(["editcap", "-F", "pcapng", "--inject-secrets",
                        f"tls,{folder / 'proxy.keys'}", str(folder / f"{leg}.pcap"), str(temp)],
                       check=True, capture_output=True, timeout=60)
        temp.replace(dest)
        return dest.name
    finally:
        temp.unlink(missing_ok=True)

def followed_streams(source, port, tls, keyfile):
    layer = "tls" if tls else "tcp"
    command = ["tshark", "-n", "-r", str(source)]
    if tls:
        command += ["-d", f"tcp.port=={port},tls", "-o", f"tls.keylog_file:{keyfile}"]
    fields = subprocess.check_output(command + ["-T", "fields", "-e", "frame.number",
                                       "-e", "frame.time_epoch", "-e", layer + ".stream"],
                                     timeout=60, text=True)
    timestamps = {}
    indices = set()
    for line in fields.splitlines():
        number, timestamp, streams = line.split("\t")
        timestamps[number] = timestamp
        indices.update(i for i in streams.split(",") if i.isdigit())
    for index in sorted(indices, key=int):
        output = subprocess.check_output(command + ["-q", "-z", f"follow,{layer},yaml,{index}"],
                                         timeout=60)
        # BaseLoader preserves decimal timestamps and the base64 payload verbatim.
        stream = yaml.load(output, Loader=yaml.BaseLoader) or {}
        if stream.get("packets"):
            for packet in stream["packets"]:
                packet["timestamp"] = timestamps[packet["packet"]]
            yield stream


def remove_connect(stream):
    """Remove just the two CONNECT header blocks before decoding the tunnel."""
    headers = [bytearray(), bytearray()]
    complete = set()
    payloads = []
    for packet in stream["packets"]:
        side = int(packet["peer"])
        if side not in complete:
            headers[side].extend(base64.b64decode(packet["data"]))
            header, separator, payload = headers[side].partition(b"\r\n\r\n")
            if not separator:
                continue
            if not header.startswith((b"CONNECT ", b"HTTP/1.")):
                return False
            complete.add(side)
            if not payload:
                continue
            packet["data"] = base64.b64encode(payload).decode()
        payloads.append(packet)
    stream["packets"] = payloads
    return len(complete) == 2 and bool(payloads)


def write_tcp(stream, server_port, dest, display_port):
    peers = stream["peers"]
    server = next(i for i, peer in enumerate(peers) if int(peer["port"]) == server_port)
    client = 1 - server
    addresses = [ipaddress.ip_address(peers[i]["host"]) for i in (client, server)]
    records = []
    for packet in stream["packets"]:
        # In text2pcap I uses the specified source/destination; O reverses them.
        direction = "I" if int(packet["peer"]) == client else "O"
        data = "".join(packet["data"].split())
        seconds, fraction = packet["timestamp"].split(".")
        date = datetime.fromtimestamp(int(seconds), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        # Split on base64 quartets to stay inside IP and text2pcap packet limits.
        for offset in range(0, len(data), 16000):
            records.append(f"{direction} {date}.{fraction}Z {data[offset:offset + 16000]}\n")
    incoming = dest.with_suffix(".txt")
    incoming.write_text("".join(records), encoding="ascii")
    subprocess.run(["text2pcap", "-q", "-r", r"(?<dir>[IO]) (?<time>[0-9T:Z.-]+) (?<data>[A-Za-z0-9+/=]+)",
                    "-b", "64", "-t", "ISO", "-m", "16000",
                    f"-{addresses[0].version}", ",".join(map(str, addresses)),
                    "-T", f"{peers[client]['port']},{display_port}", "-N", "Decrypted TCP reconstruction",
                    str(incoming), str(dest)], check=True, capture_output=True, timeout=60)
    incoming.unlink()


def export_plaintext(folder, leg, port, tls, connect, inner_tls):
    """Reframe application bytes for Follow TCP; retain original wire capture separately."""
    keyfile = folder / "proxy.keys"
    with TemporaryDirectory(dir=folder) as directory:
        work = Path(directory)
        traces = []
        for index, stream in enumerate(followed_streams(folder / f"{leg}.pcap", port, tls, keyfile)):
            if connect and not remove_connect(stream):
                continue
            if inner_tls:
                tunnel = work / f"tunnel-{index}.pcapng"
                write_tcp(stream, port, tunnel, 443)
                streams = followed_streams(tunnel, 443, True, keyfile)
            else:
                streams = [stream]
            for application in streams:
                trace = work / f"plain-{len(traces)}.pcapng"
                # Use the HTTP service port so Wireshark recognizes H1 and the H2 preface.
                write_tcp(application, 443 if inner_tls else port, trace, 80)
                traces.append(trace)
        if traces:
            merged = work / "merged.pcapng"
            subprocess.run(["mergecap", "-w", str(merged), *map(str, traces)], check=True, timeout=60)
            name = f"{leg}-plaintext.pcapng"
            merged.replace(folder / name)
            return name
