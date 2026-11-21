"""Run-scoped HTTP routing in the lab Envoy network namespace."""
import ipaddress
import json
from contextlib import contextmanager

PREFIX = "type.googleapis.com/envoy."
FRONT_PORT = 10002


def address(host, port):
    return {"socket_address": {"address": host, "port_value": port}}


def cluster(name, host, port, protocol):
    options = "extensions.upstreams.http.v3.HttpProtocolOptions"
    http_version = "http2_protocol_options" if protocol == "HTTP/2" else "http_protocol_options"
    return {
        "name": name, "type": "STRICT_DNS", "connect_timeout": "8s",
        "load_assignment": {"cluster_name": name, "endpoints": [{"lb_endpoints": [
            {"endpoint": {"address": address(host, port)}}]}]},
        "typed_extension_protocol_options": {"envoy." + options: {
            "@type": PREFIX + options, "explicit_http_config": {http_version: {}}}},
    }


def enable_tls(upstream, hostname, protocol, ca, skip, keylog):
    common = {"alpn_protocols": ["h2" if protocol == "HTTP/2" else "http/1.1"]}
    try:
        ipaddress.ip_address(hostname)
        san = "IP_ADDRESS"
    except ValueError:
        san = "DNS"
    tls = {"@type": PREFIX + "extensions.transport_sockets.tls.v3.UpstreamTlsContext",
           "common_tls_context": common, "sni": hostname}
    if not skip:
        common["validation_context"] = {
            "trusted_ca": {"inline_string": ca} if ca else {"filename": "/etc/ssl/certs/ca-certificates.crt"},
        }
        if san == "DNS":
            tls["auto_sni_san_validation"] = True
        else:
            common["validation_context"]["match_typed_subject_alt_names"] = [
                {"san_type": san, "matcher": {"exact": hostname}}]
    if keylog:
        common["key_log"] = {"path": str(keylog)}
    upstream["transport_socket"] = {"name": "envoy.transport_sockets.tls", "typed_config": tls}


def listener(name, host, port, kind, config):
    return {"name": name, "address": address(host, port), "per_connection_buffer_limit_bytes": 1048576,
            "filter_chains": [{"filters": [{"name": "envoy.filters.network." + kind,
                                            "typed_config": config}]}]}


@contextmanager
def upstream_router(engine, base, tap, project, front_ip, target, hop, port, protocol,
                    forward, listener_tls, ca, skip, keylog, ready):
    target_port = target.port or (443 if target.scheme == "https" else 80)
    http = {"@type": PREFIX + "extensions.filters.network.http_connection_manager.v3.HttpConnectionManager",
            "stat_prefix": "requests", "codec_type": "HTTP1", "use_remote_address": True,
            "route_config": {"name": "run", "virtual_hosts": [{"name": "origin", "domains": ["*"],
                "routes": [{"match": {"prefix": "/"}, "route": {"cluster": "requests", "timeout": "20s"}}]}]},
            "http_filters": [{"name": "envoy.filters.http.router", "typed_config": {
                "@type": PREFIX + "extensions.filters.http.router.v3.Router"}}]}
    listeners = [listener("client_http", front_ip, FRONT_PORT, "http_connection_manager", http)]
    requests = cluster("requests", "127.0.0.1" if forward else hop, 11003 if forward else port, protocol)
    clusters = [requests]
    if forward:
        # Only the upstream side opens CONNECT. The HCM has already added XFF.
        authority = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
        tcp = {"@type": PREFIX + "extensions.filters.network.tcp_proxy.v3.TcpProxy",
               "stat_prefix": "forward", "cluster": "forward_proxy",
               "tunneling_config": {"hostname": f"{authority}:{target_port}"}}
        listeners.append(listener("forward_tunnel", "127.0.0.1", 11003, "tcp_proxy", tcp))
        proxy = cluster("forward_proxy", hop, port, "HTTP/1.1")
        clusters.append(proxy)
        if listener_tls:
            enable_tls(proxy, "mitm" if ca else hop, "HTTP/1.1", ca, skip, keylog)
    if (target.scheme == "https" if forward else listener_tls):
        enable_tls(requests, target.hostname, protocol, ca, skip, keylog)
    config = {"static_resources": {"listeners": listeners, "clusters": clusters},
              "admin": {"address": address("127.0.0.1", 11004)}}
    for stale in engine.containers.list(all=True, filters={"label": "lab.http-router=" + project}):
        stale.remove(force=True)
    worker = engine.containers.create(base.image.id, ["envoy", "--disable-hot-restart", "--concurrency", "1",
        "--config-yaml", json.dumps(config)], entrypoint=["/usr/bin/env"], user="0",
        name=project + "-http-router", labels={"lab.http-router": project},
        network_mode="container:" + base.id, volumes_from=[tap.id])
    try:
        worker.start()
        def listening():
            worker.reload()
            if worker.status != "running":
                raise RuntimeError(worker.logs(tail=6).decode(errors="replace"))
            return tap.exec_run(["python", "-c", "import urllib.request; "
                "urllib.request.urlopen('http://127.0.0.1:11004/ready', timeout=1).read()"]).exit_code == 0
        ready(listening, 12, "Envoy HTTP listener startup timed out")
        yield
    finally:
        worker.stop(timeout=2)
        worker.remove()
