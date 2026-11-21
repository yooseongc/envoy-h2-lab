"""Fixed client program sent to existing lab workers, including older images."""
import http.client
import json
from h2.exceptions import H2Error
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

client, url, tls_mode, start, count, hop, port, protocol, via, keyfile, ca, wire_scheme, proxy_transport = sys.argv[1:]
target = urlsplit(url)
context = ssl.create_default_context()
if ca:
    context.load_verify_locations(cadata=ca)
if keyfile:
    context.keylog_filename = keyfile
if protocol == "HTTP/2":
    context.set_alpn_protocols(["h2"])
if tls_mode == "skip":
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE


def h2_status(sock, path):
    from h2.config import H2Configuration
    from h2.connection import H2Connection
    from h2.events import ConnectionTerminated, ResponseReceived, StreamReset
    session = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    session.initiate_connection()
    session.send_headers(1, [(":method","GET"), (":scheme",wire_scheme),
                             (":authority",target.netloc), (":path",path)], end_stream=True)
    sock.sendall(session.data_to_send())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        data = sock.recv(65536)
        if not data:
            break
        for event in session.receive_data(data):
            if isinstance(event, ResponseReceived) and event.stream_id == 1:
                return int(dict(event.headers)[":status"])
            if isinstance(event, (StreamReset, ConnectionTerminated)):
                raise ValueError("HTTP/2 stream closed before response")
        pending = session.data_to_send()
        if pending:
            sock.sendall(pending)
    raise ValueError("HTTP/2 응답 헤더를 받지 못했습니다.")


def send(number):
    connection = http.client.HTTPConnection(target.hostname, target.port or (443 if target.scheme == "https" else 80), timeout=10)
    tunnel = http.client.HTTPConnection("envoy", 10001, timeout=10)
    tunnel.set_tunnel(hop, int(port))
    time.sleep(max(0, float(start) - time.time()))
    began = time.monotonic()
    row = dict(client=client, request=number)
    try:
        tunnel.connect()
        connection.sock, tunnel.sock = tunnel.sock, None
        row["envoy_ip"] = connection.sock.getpeername()[0]
        if proxy_transport == "tls":
            proxy_context = ssl.create_default_context(cadata=ca)
            if tls_mode == "skip":
                proxy_context.check_hostname = False
                proxy_context.verify_mode = ssl.CERT_NONE
            proxy_context.set_alpn_protocols(["http/1.1"])
            if keyfile:
                proxy_context.keylog_filename = keyfile
            connection.sock = proxy_context.wrap_socket(connection.sock, server_hostname="mitm")
        if via == "forward":
            proxy = http.client.HTTPConnection(hop, int(port), timeout=10)
            proxy.set_tunnel(target.hostname, target.port or (443 if target.scheme == "https" else 80))
            proxy.sock = connection.sock
            proxy._tunnel()  # Second CONNECT, inside the Envoy tunnel.
        if wire_scheme == "https":
            if proxy_transport == "tls":
                from urllib3.util.ssltransport import SSLTransport
                connection.sock = SSLTransport(connection.sock, context, server_hostname=target.hostname)
            else:
                connection.sock = context.wrap_socket(connection.sock, server_hostname=target.hostname)
            if protocol == "HTTP/2" and connection.sock.selected_alpn_protocol() != "h2":
                raise ValueError("서버가 ALPN에서 HTTP/2를 선택하지 않았습니다.")
        path = target.path or "/"
        if target.query:
            path += "?" + target.query
        if protocol == "HTTP/2":
            row["status"] = h2_status(connection.sock, path)
            row["response_protocol"] = "HTTP/2"
        else:
            connection.request("GET", path, headers={"Host":target.netloc})
            with connection.getresponse() as response:
                row["status"] = response.status
                row["response_protocol"] = {10:"HTTP/1.0",11:"HTTP/1.1"}.get(response.version, str(response.version))
    except (OSError, http.client.HTTPException, ValueError, H2Error) as error:
        row["error"] = str(error)
    finally:
        connection.close()
        tunnel.close()
    row["elapsed_ms"] = round((time.monotonic() - began) * 1000)
    return row


with ThreadPoolExecutor(max_workers=int(count)) as pool:
    print(json.dumps(list(pool.map(send, range(int(count))))))
