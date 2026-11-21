# 폐쇄망 배포

배포 ZIP 전체를 한 폴더에 풉니다. 이 폴더가 설치 위치이며 실행 결과는 하위 captures/에 쌓입니다. 이미지는 images.tar.gz에 묶여 있습니다.

| 준비 항목 | Windows | Linux |
|---|---|---|
| 컨테이너 | Docker Desktop, Linux 컨테이너 모드 | 로컬 Docker Engine, Compose v2, /var/run/docker.sock 접근 권한 |
| 실행 도구 | Python 3.8 이상 (python), PowerShell | Python 3.8 이상 (python3), POSIX 셸 |
| 저장 대화상자 | Python 설치 시 Tcl/Tk 포함 | 그래픽 세션 및 tkinter (예: python3-tk). 헤드리스에서는 captures/ 사용 |

폐쇄망에는 위 호스트 도구를 미리 준비하세요. 배포 파일명의 linux-amd64 또는 linux-arm64는 Docker 엔진의 CPU 아키텍처입니다. Windows와 Linux의 엔진 아키텍처가 같으면 같은 ZIP을 사용합니다.

| 작업 | Windows PowerShell | Linux 셸 |
|---|---|---|
| 최초 설치 또는 이미지 갱신 | ` .\install-lab.ps1 ` | `sh install-lab.sh` |
| 시작 | ` .\start-lab.ps1 ` | `sh start-lab.sh` |
| 종료 | ` .\stop-lab.ps1 ` | `sh stop-lab.sh` |

설치는 압축 이미지의 SHA-256 및 대상 플랫폼을 검사하고 Docker에 이미지를 로드한 뒤 태그별 이미지 ID를 확인합니다. 시작은 레지스트리 조회와 빌드 없이 서비스를 띄웁니다. UI는 http://127.0.0.1:8765, 로컬 저장 도우미는 127.0.0.1:8766입니다. 종료 전에 진행 중인 실험을 마치세요. 종료는 컨테이너를 정지하며 캡처 파일을 보존합니다. 다시 시작하면 종료 직전 실행 중이던 동적 인스턴스도 재시작합니다.

Linux 헤드리스 서버에서는 해당 서버의 captures/ 폴더에서 결과를 복사할 수 있습니다. 원격 브라우저로 UI를 사용할 때는 SSH 로컬 포워딩으로 8765를 연결하세요. 저장 대화상자는 도우미가 실행된 데스크톱에서 사용합니다.

## 배포본 다시 만들기

인터넷 연결이 가능한 소스 작업 폴더에서 Windows는 `python deploy/package.py`, Linux는 `python3 deploy/package.py`를 실행하세요. 로컬 도구 이미지를 빌드하고 나머지 Compose 이미지는 엔진 캐시를 사용하며 누락된 이미지를 내려받습니다. 결과는 dist/envoy-h2-lab-linux-ARCH.zip입니다. 다른 아키텍처용 파일은 해당 아키텍처의 Linux 컨테이너 엔진에서 생성하세요.
