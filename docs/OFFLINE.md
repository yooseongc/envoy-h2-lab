# 폐쇄망 배포

릴리즈 ZIP을 대상 PC로 복사해 한 폴더에 풉니다. 릴리즈에 첨부된 SHA256SUMS.txt의 값과 ZIP의 SHA-256을 대조할 수 있습니다. Windows에서는 `Get-FileHash 파일명.zip`, Linux에서는 ZIP과 체크섬을 같은 폴더에 놓고 `sha256sum -c SHA256SUMS.txt`를 실행합니다.

| 작업 | Windows PowerShell | Linux Bash |
|---|---|---|
| 최초 설치 또는 이미지 갱신 | `.\install-lab.ps1` | `bash install-lab.sh` |
| 시작 | `.\start-lab.ps1` | `bash start-lab.sh` |
| 종료 | `.\stop-lab.ps1` | `bash stop-lab.sh` |

Windows는 Docker Desktop의 Linux 컨테이너 모드, Linux는 로컬 Docker Engine과 Compose v2, Bash, curl, sha256sum이 필요합니다. 현재 사용자는 Docker 엔진을 사용할 수 있어야 합니다. Docker 엔진의 아키텍처는 `docker version --format '{{.Server.Os}}/{{.Server.Arch}}'`로 확인하세요.

설치는 images.tar.gz의 SHA-256과 플랫폼을 확인하고 이미지를 로드한 뒤 태그별 이미지 ID를 검사합니다. 배포 ZIP에서 시작하면 빌드와 pull 없이 서비스를 기동합니다. UI는 http://127.0.0.1:8765 에서 열립니다. 종료 전에 진행 중인 실험을 마치세요. 다시 시작하면 종료 직전 실행 중이던 동적 인스턴스도 재시작합니다.

원격 Linux 서버에서 실행할 때는 브라우저가 있는 컴퓨터에서 `ssh -L 8765:127.0.0.1:8765 사용자@서버`를 실행한 뒤 로컬 브라우저에서 UI를 엽니다. 호스트에 Python이나 GUI를 설치할 필요가 없습니다. 결과는 서버의 captures/ 폴더에 보관되며 UI에서 브라우저로도 받을 수 있습니다.

## 새 배포 ZIP 만들기

패키지를 만드는 개발 PC에서만 Python 3을 사용합니다. 소스 폴더에서 Windows는 `python deploy/package.py`, Linux는 `python3 deploy/package.py`를 실행하세요. 인터넷에 연결된 Docker 엔진에서 도구 이미지를 빌드하고 필요한 Compose 이미지를 모아 dist/envoy-h2-lab-linux-ARCH.zip을 생성합니다. 다른 아키텍처용 파일은 그 아키텍처의 엔진에서 만드세요.
