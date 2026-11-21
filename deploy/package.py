"""Build a portable offline ZIP for the current Linux Docker engine architecture."""
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from lab import ROOT, digest, docker


def bundle():
    platform = docker("version", "--format", "{{.Server.Os}}/{{.Server.Arch}}", output=True)
    if not platform.startswith("linux/"):
        raise ValueError("Select a Linux container engine")
    docker("compose", "build", "ui")
    config = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    if config.count("  build: .\n") != 1:
        raise ValueError("Review Compose build entries before offline export")
    config = config.replace("  build: .\n", "")
    tags = set(docker("compose", "config", "--images", output=True).splitlines())
    images = {}
    for tag in sorted(tags):
        if subprocess.run(["docker", "image", "inspect", tag], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode:
            docker("pull", tag)
        details = json.loads(docker("image", "inspect", tag, output=True))[0]
        if platform != details["Os"] + "/" + details["Architecture"]:
            raise ValueError(f"{tag} platform does not match {platform}")
        images[tag] = details["Id"]
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dist) as temp:
        stage = Path(temp)
        # Stream binary bytes directly to gzip on both Windows and Linux.
        archive = stage / "images.tar.gz"
        with gzip.open(archive, "wb", compresslevel=1) as compressed:
            with subprocess.Popen(["docker", "save", *images], stdout=subprocess.PIPE) as proc:
                shutil.copyfileobj(proc.stdout, compressed, 1024 * 1024)
                if proc.wait():
                    raise RuntimeError("docker save failed")
        (stage / "images.json").write_text(json.dumps(dict(platform=platform, images=images,
            sha256=digest(archive)), indent=2))
        (stage / "compose.yaml").write_text(config, encoding="utf-8")
        output = dist / ("envoy-h2-lab-" + platform.replace("/", "-") + ".zip")
        pending = stage / "bundle.zip"
        with ZipFile(pending, "w", compression=ZIP_STORED) as z:
            for name in ("images.tar.gz", "images.json", "compose.yaml"):
                z.write(stage / name, name)
            files = ["envoy.yaml", "nginx.conf", "mitm_run.py", "deploy/lab.py",
                     "windows/save_capture.py", "OFFLINE.md"]
            files += [f"{action}-lab.{ext}" for action in ("install","start","stop") for ext in ("ps1","sh")]
            for name in files:
                info = ZipInfo.from_file(ROOT / name, name)
                info.create_system = 3
                info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
                z.writestr(info, (ROOT / name).read_bytes())
        pending.replace(output)
        print(output)


if __name__ == "__main__":
    bundle()
