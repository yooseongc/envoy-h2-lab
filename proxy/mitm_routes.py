"""Route each reverse-proxy request by its HTTP/1 Host or HTTP/2 :authority."""
import json
import os
from pathlib import Path

from mitmproxy import http

routes = json.loads(Path(os.environ["LAB_REVERSE_ROUTES"]).read_text())


def requestheaders(flow: http.HTTPFlow):
    request = flow.request
    authority = request.host_header or ""
    destination = routes.get(authority.lower())
    if destination is None:
        flow.response = http.Response.make(421, b"Unregistered request authority\n")
        return
    # These belong to the request, not the shared downstream H2 connection.
    request.scheme, request.host, request.port = destination
    request.host_header = authority

def server_connect(data):
    # The Origin negotiates independently of Envoy's H2-only proxy connection.
    data.server.alpn_offers = (b"h2", b"http/1.1")
