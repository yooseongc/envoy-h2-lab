import pathlib
import signal
import subprocess
import sys
import time

run, leg, port, *options = sys.argv[1:]
direction = options[0] if options else "both"
filters = {
    "both": f"tcp port {int(port)}",
    "receive": f"tcp and ((inbound and dst port {int(port)}) or (outbound and src port {int(port)}))",
    "send": f"tcp and ((outbound and dst port {int(port)}) or (inbound and src port {int(port)}))",
}
folder = pathlib.Path("/captures") / run
log = folder / (leg + ".log")
with log.open("wb") as out:
    proc = subprocess.Popen(["tcpdump","-p","-Z","root","-i","any","-s","0","-U","-w",
                             str(folder / (leg + ".pcap")),filters[direction]], stderr=out)
    try:
        for _ in range(900):
            if proc.poll() is not None:
                raise RuntimeError(log.read_text())
            if (folder / "stop").exists():
                break
            time.sleep(0.1)
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
        (folder / (leg + ".done")).touch()
