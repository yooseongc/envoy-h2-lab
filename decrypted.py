"""Export decrypted application PDUs; retain wire packets separately."""
import subprocess


def export_http_pdus(folder, leg, port):
    dest = folder / f"{leg}-decrypted.pcapng"
    temp = dest.with_suffix(".tmp")
    try:
        subprocess.run(["tshark","-n","-r",str(folder/f"{leg}.pcap"),
                        "-d",f"tcp.port=={port},tls","-o",f"tls.keylog_file:{folder/'proxy.keys'}",
                        "-Y","http or http2","-U","OSI layer 7","-w",str(temp)],
                       check=True, capture_output=True, timeout=30)
        decoded = subprocess.check_output(["tshark","-n","-r",str(temp),"-o","tls.keylog_file:",
                                           "-Y","http or http2","-T","fields","-e","frame.number"],
                                          timeout=30)
        if decoded.strip():
            temp.replace(dest)
            return dest.name
        return None
    finally:
        temp.unlink(missing_ok=True)
