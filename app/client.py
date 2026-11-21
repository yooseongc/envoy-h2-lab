import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

route, client, run, start, count = sys.argv[1:]
def send(i):
    time.sleep(max(0, float(start) - time.time()))
    request = urllib.request.Request(f"http://envoy:10000/{run}/{client}/{i}",
                                     headers={"X-Lab-Route":route,"X-Lab-Client":client})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

with ThreadPoolExecutor(max_workers=int(count)) as pool:
    print(json.dumps(list(pool.map(send, range(int(count))))))
