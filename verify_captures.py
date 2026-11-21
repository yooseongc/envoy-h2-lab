"""Verify lab captures using tshark PDML (per H2 frame)."""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def value(node, name):
    field = node.find(f".//field[@name='{name}']")
    return field.get("show") if field is not None else None


def inspect(folder, leg, protocol, total):
    port = {"front": 10000, "middle": 8080, "back": 8000}[leg]
    file = folder / f"{leg}.pcap"
    assert file.stat().st_size >= (25 if total else 24), file
    assert (folder / f"{leg}.done").exists(), f"{leg}: capture unfinished"
    assert "0 packets dropped by kernel" in (folder / f"{leg}.log").read_text()
    data = subprocess.check_output([
        "tshark", "-r", str(file), "-d", f"tcp.port=={port},{protocol}", "-T", "pdml"
    ])
    packets = ET.fromstring(data).findall("packet")
    connections = set()
    requests, responses = [], []
    for packet in packets:
        tcp = value(packet, "tcp.stream")
        if tcp is None:
            continue
        connections.add(tcp)
        base = dict(tcp_stream=int(tcp), frame=int(value(packet, "frame.number")),
                    time=float(value(packet, "frame.time_epoch")), src=value(packet, "ip.src"), dst=value(packet, "ip.dst"))
        # One TCP packet can contain several H2 frames; never zip packet-level fields.
        for proto in packet.findall(f"proto[@name='{protocol}']"):
            if protocol == "http2":
                headers = {value(h, "http2.header.name"): value(h, "http2.header.value")
                           for h in proto.findall(".//field[@name='http2.header']")}
                path, status = headers.get(":path"), headers.get(":status")
                row = dict(base, h2_stream=int(value(proto, "http2.streamid") or 0),
                           path=path, xff=headers.get("x-forwarded-for"))
            else:
                path = value(proto, "http.request.uri") if value(proto, "http.request.method") else None
                status = value(proto, "http.response.code")
                row = dict(base, path=path, xff=value(proto, "http.x_forwarded_for"))
            if path:
                requests.append(row)
            if status:
                responses.append(dict(base, status=status))
    assert len(requests) == len(responses) == total, (leg, len(requests), len(responses))
    assert all(r["status"] == "200" for r in responses), leg
    overlap = not total or max(r["time"] for r in requests) < min(r["time"] for r in responses)
    return dict(bytes=file.stat().st_size, packets=len(packets),
                tcp_connections=len(connections), requests=requests,
                successful_responses=len(responses),
                request_span_ms=round(1000 * (max(r["time"] for r in requests) -
                                            min(r["time"] for r in requests)), 3) if requests else 0,
                all_requests_before_first_response=overlap)


def verify(run, mode):
    folder = Path(run)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    clients = manifest.get("clients", ["client-a", "client-b"])
    expected = {f"/{folder.name}/{client}/{i}" for client in clients for i in range(manifest.get("count", 4))}
    total = len(expected)
    legs = {}
    for leg in ("front", "middle", "back"):
        absent = mode == "direct" and leg == "middle"
        is_h2 = (leg == "middle" and mode in ("h2","h2-keep")) or (leg == "back" and mode == "h2-keep")
        data = inspect(folder, leg, "http2" if is_h2 else "http",
                       0 if absent else total)
        assert {r["path"] for r in data["requests"]} == (set() if absent else expected), leg
        legs[leg] = data
    sources = {r["path"]: r["src"] for r in legs["front"]["requests"]}
    assert len(set(sources.values())) == len(clients), "client identities"
    if manifest:
        assert all(ip == clients[path.split("/")[2]] for path, ip in sources.items()), "front IP"
    middle = {r["path"]: r for r in legs["middle"]["requests"]}
    for path, row in middle.items():
        assert row["xff"] == sources[path], row
    distribution = {name: 0 for name in manifest.get("servers", {}).values()}
    replies = {}
    if manifest:
        replies = {r["path"]: r for r in json.loads((folder / "responses.json").read_text())}
        assert set(replies) == expected, "response paths"
    for row in legs["back"]["requests"]:
        path = row["path"]
        xff = sources[path] if mode == "direct" else sources[path] + ", " + middle[path]["src"]
        assert row["xff"] == xff, row
        if manifest:
            server = manifest["servers"][row["dst"]]
            assert replies[path]["server"] == server and replies[path]["server_ip"] == row["dst"], path
            if mode == "h2-keep":
                assert replies[path]["origin_protocol"] in ("HTTP/2","HTTP/2.0"), path
            distribution[server] += 1
    if mode in ("h2","h2-keep"):
        assert len({r["tcp_stream"] for r in middle.values()}) == 1, "H2 TCP sharing"
        assert len({r["h2_stream"] for r in middle.values()}) == total, "H2 stream IDs"
    connections = {leg: data["tcp_connections"] for leg, data in legs.items()}
    assert connections["front"] == total, connections
    if mode == "h1" and legs["middle"]["all_requests_before_first_response"]:
        assert connections["middle"] == total, connections
    summary = dict(tcp_connections=connections, h2_streams=total if mode in ("h2","h2-keep") else 0,
                   xff_matches=total, requests_by_server=distribution,
                   all_requests_overlap=all(d["all_requests_before_first_response"] for d in legs.values()))
    result = dict(run=folder.name, mode=mode, passed=True, legs=legs, summary=summary)
    (folder / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python verify_captures.py H2_RUN_FOLDER H1_RUN_FOLDER")
    for run, mode in zip(sys.argv[1:], ("h2", "h1")):
        result = verify(run, mode)
        print(result["run"], mode, "PASS", {leg: data["tcp_connections"] for leg, data in result["legs"].items()})
