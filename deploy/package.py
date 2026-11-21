"""Build a portable offline ZIP for the current Linux Docker engine architecture."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, output=False):
    result = subprocess.run(["docker", *args], cwd=ROOT, check=True, text=True,
                            stdout=subprocess.PIPE if output else None)
    return result.stdout.strip() if output else None


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as data:
        for block in iter(lambda: data.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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
        manifest = [f"sha256 {digest(archive)}", f"platform {platform}", *[f"{tag} {image}" for tag, image in images.items()]]
        (stage / "images.manifest").write_bytes(("\n".join(manifest) + "\n").encode("ascii"))
        (stage / "compose.yaml").write_text(config, encoding="utf-8")
        output = dist / ("envoy-h2-lab-" + platform.replace("/", "-") + ".zip")
        pending = stage / "bundle.zip"
        with ZipFile(pending, "w", compression=ZIP_STORED) as z:
            for name in ("images.tar.gz", "images.manifest", "compose.yaml"):
                z.write(stage / name, name)
            files = ["envoy.yaml", "nginx.conf", "mitm_run.py", "deploy/common.ps1",
                     "deploy/common.sh", "OFFLINE.md", "README.md"]
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
