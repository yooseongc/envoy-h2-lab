import json
import io
import tarfile
import ipaddress
from contextlib import contextmanager, nullcontext
import os
import shutil
import re
import threading
import time
import uuid
from urllib.parse import urlsplit
from verify_captures import verify
from decrypted import export_plaintext, export_trace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import docker

engine = docker.from_env(timeout=30)
project = engine.containers.get(os.environ["HOSTNAME"]).labels["com.docker.compose.project"]

legs = {"front": "10000", "middle": "8080", "back": "8000"}
routes = ("reverse-h2-keep", "reverse-h2", "reverse-h1", "origin-h1")
root = Path("/captures")
lock = threading.Lock()

def container(service):
    found = engine.containers.list(all=True, filters={"label": [
        "com.docker.compose.project=" + project, "com.docker.compose.service=" + service]})
    if len(found) != 1:
        raise RuntimeError(f"{service}: expected one container, found {len(found)}")
    return found[0]

def wait_until(check, seconds, message):
    deadline = time.monotonic() + seconds
    while not check():
        if time.monotonic() >= deadline:
            raise RuntimeError(message)
        time.sleep(0.1)

def workers(role):
    found = engine.containers.list(all=True, filters={"label": [
        "lab.project=" + project, "lab.role=" + role]})
    return {w.labels["lab.name"]: w for w in sorted(found, key=lambda c: c.name)}

def scale(role, count):
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("대수는 1~4입니다.")
    is_client = role == "client"
    first = 1 if is_client else 2  # Compose owns origin instance 1.
    desired = [f"{role}-{i}" for i in range(first, count + 1)]
    current = workers(role)
    net = f"{project}_" + ("front" if is_client else "back")
    image = container("ui").image.id
    command = ["python", "-c", "import signal; signal.pause()"] if is_client else ["python", "origin.py"]
    for name in desired:
        start_worker = True
        if name in current:
            previous = current[name]
            if (is_client and previous.labels.get("lab.client.version") == "2") or (not is_client and previous.labels.get("lab.origin.version") == "tls-1"):
                continue
            start_worker = previous.status == "running"
            previous.remove(force=True)
        worker = engine.containers.create(image, command, name=f"{project}-{name}", hostname=name,
            network=net, networking_config={net: engine.api.create_endpoint_config(
                aliases=[] if is_client else ["origin"])}, cap_drop=["ALL"],
            restart_policy={"Name": "unless-stopped"},
            labels={"lab.origin.version": "tls-1", "lab.client.version": "2", "lab.project": project, "lab.role": role, "lab.name": name,
                    "com.docker.compose.project": project, "com.docker.compose.service": "lab-worker"})
        try:
            if start_worker:
                worker.start()
        except Exception:
            worker.remove(force=True)
            raise
    for name, worker in current.items():
        if name not in desired:
            worker.remove(force=True)

def servers():
    return {"origin-1": container("origin"), **workers("origin")}

def topology():
    return {key: {name: worker.status for name, worker in group.items()}
            for key, group in (("clients", workers("client")), ("servers", servers()))}

@contextmanager
def nginx_url_hop(host, port):
    # A short-lived stream listener inside the lab Nginx forwards TLS bytes unchanged.
    try:
        ip = ipaddress.ip_address(host)
        upstream = f"[{ip}]" if ip.version == 6 else str(ip)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", host):
            raise ValueError("서버 호스트 이름을 확인하세요.")
        upstream = host
    if "%" in upstream:
        raise ValueError("IPv6 zone ID는 지원하지 않습니다.")
    reverse = container("reverse")
    prefix = "/tmp/url-" + uuid.uuid4().hex
    port_in = 8081
    config = (f"daemon on; worker_processes 1; pid {prefix}/nginx.pid; error_log stderr; "
              f"events {{}} stream {{ server {{ listen {port_in}; proxy_connect_timeout 5s; "
              f"proxy_timeout 20s; proxy_pass {upstream}:{port}; }} }}").encode()
    code, data = reverse.exec_run(["mkdir", prefix])
    if code:
        raise RuntimeError(data.decode())
    command = ["nginx", "-p", prefix + "/", "-c", "stream.conf"]
    started = False
    try:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            info = tarfile.TarInfo("stream.conf")
            info.size = len(config)
            tar.addfile(info, io.BytesIO(config))
        reverse.put_archive(prefix, archive.getvalue())
        # Redirect the daemon's descriptors so the Docker exec stream closes.
        code, data = reverse.exec_run(["sh","-c",'exec "$@" </dev/null >/dev/null 2>&1',
                                       "nginx-start", *command])
        if code:
            raise RuntimeError("Nginx URL 경로를 열 수 없습니다. 대상 이름과 포트를 확인하세요.")
        started = True
        address = reverse.attrs["NetworkSettings"]["Networks"][f"{project}_middle"]["IPAddress"]
        yield (address, port_in)
    finally:
        if started:
            reverse.exec_run(command + ["-s", "stop"])
            wait_until(lambda: reverse.exec_run(["test","!","-e",prefix+"/nginx.pid"]).exit_code == 0,
                       5, "Nginx URL 경로 종료 시간 초과")
        reverse.exec_run(["rm","-f",prefix+"/stream.conf"])
        reverse.exec_run(["rmdir",prefix])

@contextmanager
def packet_capture(folder, plan):
    launched = []
    try:
        for leg, (tap, port, direction) in plan.items():
            container("tap-" + tap).exec_run(
                ["python","tap.py",folder.name,leg,str(port),direction], detach=True)
            launched.append(leg)
        def ready():
            return all((folder / (leg+".log")).is_file() and
                       "listening on" in (folder / (leg+".log")).read_text() for leg in launched)
        wait_until(ready, 8, f"tcpdump 준비 실패: captures/{folder.name}")
        yield
        time.sleep(1.1)
    finally:
        (folder / "stop").touch()
        wait_until(lambda: all((folder / (leg+".done")).exists() for leg in launched),
                   8, f"캡처 종료 시간 초과: captures/{folder.name}")


@contextmanager
def mitm_url_hop(target, folder, skip, keys, mode):
    proxy = container("mitm")
    upstream = target.scheme + "://" + target.netloc
    proxy.exec_run(["python","/lab/mitm_run.py",str(folder),upstream,mode,
                    "yes" if skip else "no","yes" if keys else "no"],detach=True)
    try:
        def ready():
            if (folder/"mitm.done").exists():
                raise RuntimeError(f"MITM 기동 실패: {folder.name}/mitm.log")
            return (folder/"mitm.ready").exists()
        wait_until(ready, 18, "MITM 기동 시간 초과")
        yield proxy.attrs["NetworkSettings"]["Networks"][f"{project}_middle"]["IPAddress"], 8082
    finally:
        (folder/"mitm.stop").touch()
        wait_until(lambda:(folder/"mitm.done").exists(),10,"MITM 종료 시간 초과")


def save_client_keys(worker,path,folder,name):
    try:
        chunks, _ = worker.get_archive(path)
        with tarfile.open(fileobj=io.BytesIO(b"".join(chunks))) as archive:
            data = archive.extractfile(archive.getmembers()[0]).read()
        (folder / (name+".keys.tmp")).write_bytes(data)
    except docker.errors.NotFound:
        pass
    finally:
        worker.exec_run(["rm","-f",path])


def direct_request(body):
    mode = body.get("target_mode","url")
    if mode not in ("url","origin"):
        raise ValueError("잘못된 대상 유형입니다.")
    url = body.get("url")
    if mode == "origin":
        instance = body.get("origin","")
        size = body.get("servers", len(servers()))
        if type(size) is not int or not 1 <= size <= 4:
            raise ValueError("Origin 수는 1~4입니다.")
        if instance and instance not in [f"origin-{i}" for i in range(1,size+1)]:
            raise ValueError("선택한 Origin이 설정한 대수에 포함되지 않습니다.")
        scale("origin",size)
        pool = servers()
        # Named instances and external proxies must not depend on Docker DNS aliases.
        if instance or body.get("via") == "external":
            server = pool[instance or "origin-1"]
            host = server.attrs["NetworkSettings"]["Networks"][project+"_back"]["IPAddress"]
        else:
            host = "origin"
        scheme = body.get("origin_scheme", "http")
        if scheme not in ("http", "https"):
            raise ValueError("Origin 연결 방식은 http 또는 https여야 합니다.")
        url = f"{scheme}://{host}:{8443 if scheme == 'https' else 8000}/"

    if not isinstance(url, str) or len(url) > 2048 or not url.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError("공백 없이 URL을 입력하세요. 비ASCII 경로는 URL 인코딩이 필요합니다.")
    target = urlsplit(url)
    if (target.scheme not in ("https", "http") or not target.hostname or target.username is not None
            or target.fragment or target.port == 0 or chr(92) in url):
        raise ValueError("사용자 정보와 프래그먼트가 없는 HTTP 또는 HTTPS URL을 입력하세요.")
    skip = body.get("skip_verify", False)
    count = body.get("count")
    if type(skip) is not bool or type(count) is not int or count not in (1,4,8):
        raise ValueError("잘못된 요청 수 또는 TLS 옵션입니다.")
    protocol = body.get("protocol", "HTTP/1.1")
    if protocol not in ("HTTP/1.1","HTTP/2"):
        raise ValueError("지원하지 않는 HTTP 버전입니다.")
    if "clients" in body:
        scale("client", body["clients"])
    active = [(name, c) for name,c in workers("client").items() if c.status == "running"]
    if not active:
        raise ValueError("실행 중인 클라이언트가 없습니다.")
    via = body.get("via", "nginx")
    if via not in ("envoy","nginx","mitm","external"):
        raise ValueError("잘못된 URL 경로입니다.")
    keys = body.get("keylog", False)
    if type(keys) is not bool:
        raise ValueError("잘못된 키 로그 설정")
    mitm_mode = body.get("mitm_mode", "reverse") if via == "mitm" else None
    if via == "mitm" and mitm_mode not in ("forward", "reverse"):
        raise ValueError("내장 MITM 방식은 forward 또는 reverse여야 합니다.")
    external_mode = body.get("external_mode","forward") if via=="external" else None
    if via == "external":
        if external_mode not in ("forward","reverse"):
            raise ValueError("외부 프록시 방식은 forward 또는 reverse여야 합니다.")
        external_ip = str(ipaddress.ip_address(body.get("proxy_ip","")))
        external_port = body.get("proxy_port")
        if type(external_port) is not int or not 1 <= external_port <= 65535:
            raise ValueError("외부 프록시 포트는 1~65535입니다.")
    port = target.port or (443 if target.scheme == "https" else 80)
    program = Path("direct_client.py").read_text(encoding="utf-8-sig")
    wire_scheme = target.scheme
    if via == "external" and external_mode == "reverse":
        wire_scheme = body.get("listener_scheme") or target.scheme
        if wire_scheme not in ("http", "https"):
            raise ValueError("외부 리버스 리스너 방식은 http 또는 https여야 합니다.")
    proxy_tls = False
    if via == "mitm":
        listener = body.get("mitm_listener") or ("http" if mitm_mode == "forward" else target.scheme)
        if listener not in ("http", "https"):
            raise ValueError("내장 MITM 리스너 방식은 http 또는 https여야 합니다.")
        if mitm_mode == "reverse":
            wire_scheme = listener
        else:
            proxy_tls = listener == "https"
    skip_proxy = body.get("skip_proxy_verify", False)
    if type(skip_proxy) is not bool or (skip_proxy and (via != "mitm" or not (proxy_tls or wire_scheme == "https"))):
        raise ValueError("MITM 인증서 검증 옵션은 클라이언트의 MITM TLS 연결에서만 사용할 수 있습니다.")
    if via == "mitm" and protocol == "HTTP/2" and wire_scheme == "http":
        raise ValueError("내장 MITM의 HTTP/2 요청에는 TLS가 필요합니다.")
    verify_scheme = target.scheme if via == "mitm" else wire_scheme
    if skip and verify_scheme != "https":
        raise ValueError("인증서 검증 옵션은 TLS 연결에서만 사용할 수 있습니다.")
    has_tls = proxy_tls or wire_scheme == "https" or (via == "mitm" and target.scheme == "https")
    keys = keys and has_tls
    decrypt = via == "mitm" and has_tls and body.get("decrypt", True) is True
    origin_trust = ""
    if mode == "origin" and scheme == "https" and not skip:
        for replica in ([pool[instance or "origin-1"]] if instance or via == "external" else pool.values()):
            wait_until(lambda: replica.exec_run(["test","-s","/tmp/lab-origin.pem"]).exit_code == 0,
                       10, "Origin TLS 인증서 준비 시간 초과")
            code, cert = replica.exec_run(["cat","/tmp/lab-origin.pem"])
            if code:
                raise RuntimeError("Origin TLS 인증서를 읽을 수 없습니다.")
            origin_trust += cert.decode()
    def invoke(item):
        name, worker = item
        keypath = "/tmp/"+run+".keys" if keys else ""
        try:
            ca = (folder/"client-ca.pem").read_text() if via=="mitm" and has_tls else origin_trust
            code, output = worker.exec_run(["python","-c",program,name,url,
                "skip" if skip_proxy or (skip and via!="mitm") else "verify",start,str(count),hop,str(hop_port),
                protocol,("forward" if "forward" in (mitm_mode, external_mode) else "direct"),keypath,ca,wire_scheme,"tls" if proxy_tls else "plain"])
            if code:
                raise RuntimeError(f"{name}: URL 요청 프로그램 실행 실패")
            return json.loads(output)
        finally:
            if keys:
                save_client_keys(worker,keypath,folder,name)
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    folder = root / run
    folder.mkdir()
    plan = {"front":("front",10001,"receive")}
    if via=="mitm":
        plan.update(middle=("mitm",8082,"receive"), back=("mitm",port,"send"))
        route_context = mitm_url_hop(target,folder,skip,keys or decrypt,mitm_mode)
    elif via=="external":
        plan["middle"] = ("front",external_port,"send")
        route_context = nullcontext((external_ip,external_port))
    elif via=="nginx":
        plan.update(middle=("middle",8081,"receive"), back=("middle",port,"send"))
        route_context = nginx_url_hop(target.hostname,port)
    else:
        plan["back"] = ("front",port,"send")
        route_context = nullcontext((target.hostname,port))
    (folder / "manifest.json").write_text(json.dumps(dict(route="url",target_mode=mode,origin=body.get("origin") or None,via=via,external_mode=external_mode,mitm_mode=mitm_mode,host=target.hostname,
        skip_proxy_verify=skip_proxy, skip_verify=skip, protocol=protocol, target_url=url, listener_scheme=listener if via=='mitm' else wire_scheme, capture_plan=plan),indent=2))
    if origin_trust and via == "mitm":
        (folder/"origin-trust.pem").write_text(origin_trust)
    decrypted_files = []
    try:
        with packet_capture(folder, plan):
            with route_context as (hop, hop_port):
                start = str(time.time() + 0.8)
                with ThreadPoolExecutor(max_workers=len(active)) as pool:
                    rows = [row for batch in pool.map(invoke, active) for row in batch]
        if decrypt and (folder/"proxy.keys").is_file() and (folder/"proxy.keys").stat().st_size:
            for leg in ("middle","back"):
                decrypted_files.append(export_trace(folder, leg))
                forward = leg == "middle" and mitm_mode == "forward"
                tls = (listener if leg == "middle" else target.scheme) == "https"
                plain = export_plaintext(folder, leg, plan[leg][1], tls, forward,
                                         forward and target.scheme == "https")
                if plain:
                    decrypted_files.append(plain)
    finally:
        if decrypt and not keys:
            (folder/"proxy.keys").unlink(missing_ok=True)
    (folder / "responses.json").write_text(json.dumps(rows,indent=2))
    fragments = sorted(folder.glob("client-*.keys.tmp"))
    if fragments:
        (folder/"client.keys").write_bytes(b"\n".join(part.read_bytes() for part in fragments))
        for part in fragments:
            part.unlink()
    extras = decrypted_files + [file for file in ("client.keys","proxy.keys","flows.mitm")
              if (folder/file).is_file() and (folder/file).stat().st_size]
    marker = folder / "url-result.tmp"
    marker.write_text(json.dumps({"run":run,"legs":list(plan),"extras":extras}))
    marker.replace(folder / "url-result.json")
    return dict(run=run,legs=list(plan),extras=extras,url=url,external_mode=external_mode,mitm_mode=mitm_mode,protocol=protocol, via={"envoy":"Envoy","nginx":"Envoy → Nginx","mitm":"Envoy → 내장 "+("포워드" if mitm_mode=="forward" else "리버스"),"external":"Envoy → 외부 "+("리버스" if external_mode=="reverse" else "포워드")}[via], tls=("검증 생략" if skip else "검증 사용") if wire_scheme=="https" else "HTTP",
                responses=rows)

def experiment(route, count):
    active = {name: worker for name, worker in workers("client").items() if worker.status == "running"}
    def address(worker, net):
        return worker.attrs["NetworkSettings"]["Networks"][f"{project}_{net}"]["IPAddress"]
    origins = servers()
    manifest = dict(server_names={address(c, "back"): name for name,c in origins.items()},
                    clients={n: address(c, "front") for n,c in active.items()},
                    servers={address(c, "back"): c.attrs["Config"]["Hostname"] for c in origins.values()},
                    count=count, route=route)
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    return capture(run, route, count, active, manifest)

def capture(run, route, count, active, manifest):
    if not active:
        raise ValueError("실행 중인 클라이언트가 없습니다.")
    folder = root / run
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    plan = {leg:(leg,port,"both") for leg,port in legs.items()}
    if len(manifest["servers"]) > 1:
        plan["back"] = ("front" if route == "origin-h1" else "middle",8000,"both")
    with packet_capture(folder, plan):
        # Let idle upstream connections expire, so the H2 preface enters this PCAP.
        time.sleep(3)
        start = str(time.time()+0.8)
        def invoke(service):
            code, data = active[service].exec_run(["python","client.py",route,service,run,start,str(count)])
            if code:
                raise RuntimeError(data.decode(errors="replace")[-1500:])
            return json.loads(data)
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            responses = [row for batch in pool.map(invoke, active) for row in batch]
    (folder / "responses.json").write_text(json.dumps(responses, indent=2))
    mode = {"reverse-h2-keep":"h2-keep", "reverse-h2":"h2", "reverse-h1":"h1", "origin-h1":"direct"}[route]
    report = verify(folder, mode)
    return {"run":run,"responses":responses,"route":route,"summary":report["summary"],"server_names":manifest["server_names"]}

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, mime="application/json", filename=None):
        if mime == "application/json":
            body = json.dumps(body,ensure_ascii=False).encode()
        self.send_response(code)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host") in ("127.0.0.1:8765","localhost:8765")

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403,{"error":"host"})
        if self.path == "/":
            return self.reply(200,Path("index.html").read_bytes(),"text/html; charset=utf-8")
        if self.path in ("/status", "/topology"):
            try:
                state = topology()
                return self.reply(200,state if self.path == "/topology" else state["clients"])
            except Exception as e:
                return self.reply(503,{"error":str(e)})
        if self.path == "/captures/latest":
            for folder in sorted(root.iterdir(), reverse=True):
                if re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", folder.name) and (folder/"url-result.json").is_file():
                    return self.reply(200,json.loads((folder/"url-result.json").read_text()))
                if re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", folder.name) and all(
                    (folder / (leg + ".done")).is_file() and (folder / (leg + ".pcap")).is_file()
                    for leg in legs):
                    result = {"run":folder.name}
                    if (folder / "responses.json").is_file() and (folder / "manifest.json").is_file():
                        manifest = json.loads((folder / "manifest.json").read_text())
                        result.update(responses=json.loads((folder / "responses.json").read_text()),
                                      server_names=manifest.get("server_names", {}))
                    return self.reply(200, result)
            return self.reply(200, {"run":None})
        match = re.fullmatch(r"/pcap/(\d{8}T\d{6}Z-[0-9a-f]{8})/((?:front|middle|back)\.pcap|(?:middle|back)-(?:decrypted|plaintext)\.pcapng|(?:client|proxy)\.keys|flows\.mitm)", self.path)
        if match:
            run, name = match.groups()
            folder = root / run
            file = folder / name
            if name.endswith(".pcap"):
                ready = file.with_suffix(".done").is_file()
            else:
                result = folder / "url-result.json"
                ready = result.is_file() and name in json.loads(result.read_text()).get("extras", [])
            if ready and file.is_file() and self.headers.get("Sec-Fetch-Site") != "cross-site":
                with file.open("rb") as source:
                    self.send_response(200)
                    self.send_header("Content-Disposition", f'attachment; filename="{run}-{name}"')
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(os.fstat(source.fileno()).st_size))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    shutil.copyfileobj(source, self.wfile)
                return
        self.reply(404,{"error":"unknown path"})

    def do_POST(self):
        if (not self.valid_host() or self.headers.get("Origin") != "http://"+self.headers["Host"]
                or self.headers.get("Content-Type") != "application/json"):
            return self.reply(403,{"error":"local UI only"})
        if not lock.acquire(blocking=False):
            return self.reply(409,{"error":"다른 작업이 진행 중입니다."})
        try:
            size = int(self.headers.get("Content-Length","0"))
            if not 0 < size <= 8192:
                raise ValueError("invalid request length")
            body = json.loads(self.rfile.read(size))
            if self.path == "/direct":
                result = direct_request(body)
            elif self.path == "/scale" or (self.path == "/run" and body.get("route") in routes and body.get("count") in (1,4,8)):
                sizes = [(role,body[key]) for role,key in (("client","clients"),("origin","servers"))
                         if body.get(key) is not None]
                if any(type(size) is not int or not 1 <= size <= 4 for _, size in sizes):
                    raise ValueError("대수는 1~4입니다.")
                for role, size in sizes:
                    scale(role, size)
                result = topology() if self.path == "/scale" else experiment(body["route"],body["count"])
            elif self.path == "/client" and body.get("service") in workers("client") and body.get("action") in ("start","stop"):
                target = workers("client")[body["service"]]
                if body["action"] == "start":
                    target.start()
                else:
                    target.stop(timeout=2)
                result = {"ok":True}
            else:
                raise ValueError("unknown operation")
        except ValueError as e:
            return self.reply(400,{"error":str(e)})
        except Exception as e:
            return self.reply(500,{"error":str(e)})
        finally:
            lock.release()
        self.reply(200,result)

if not workers("client"):
    scale("client", 2)
ThreadingHTTPServer(("",8765),Handler).serve_forever()
