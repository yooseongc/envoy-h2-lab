"""Each lab client sends only a plaintext HTTP/1.1 GET to Envoy."""
import http.client
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

client, url, start, count, front_port, mode, authority = sys.argv[1:]
target = urlsplit(url)
path = target.path or "/"
if target.query:
    path += "?" + target.query


def send(number):
    conn = http.client.HTTPConnection("envoy", int(front_port), timeout=25)
    time.sleep(max(0, float(start) - time.time()))
    began = time.monotonic()
    row = dict(client=client, request=number, authority=authority)
    try:
        conn.connect()
        row["client_ip"] = conn.sock.getsockname()[0]
        conn.request("GET", path, headers={"Host": authority, "X-Lab-Client": client,
                                          "X-Lab-Request": str(number)})
        with conn.getresponse() as response:
            row.update(status=response.status, response_protocol="HTTP/1.1")
            if mode == "origin" and response.status == 200:
                try:
                    observed = json.loads(response.read(8192))
                except (ValueError, UnicodeError):
                    observed = {}
                if isinstance(observed, dict):
                    for key in ("xff", "server", "server_ip", "origin_protocol"):
                        if key in observed:
                            row[key] = observed[key]
    except (OSError, http.client.HTTPException) as error:
        row["error"] = str(error)
    finally:
        conn.close()
    row["elapsed_ms"] = round((time.monotonic() - began) * 1000)
    return row


with ThreadPoolExecutor(max_workers=int(count)) as pool:
    print(json.dumps(list(pool.map(send, range(int(count))))))
