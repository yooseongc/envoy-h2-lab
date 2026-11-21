# HTTP 프록시 실험실

클라이언트가 Envoy를 거쳐 내장 MITM 또는 외부 프록시로 보내는 HTTP 요청을 실험합니다. 브라우저에서 목적지, TLS 사용 여부, HTTP 버전과 동시 요청 수를 선택하고 구간별 패킷을 Wireshark로 확인할 수 있습니다.

## 설치하고 열기

1. [최신 릴리즈](https://github.com/yooseongc/envoy-h2-lab/releases/latest)에서 이미지가 포함된 배포 ZIP을 받아 설치할 폴더에 풉니다. `linux-amd64`는 인텔·AMD x86-64 머신용입니다.
2. Docker를 시작합니다. Windows는 Docker Desktop의 Linux 컨테이너 모드와 PowerShell을, Linux는 Docker Engine, Compose v2, Bash, curl 및 sha256sum을 사용합니다. 실험 호스트에 Python을 설치할 필요가 없습니다.
3. 압축을 푼 폴더에서 아래 명령을 실행합니다. 설치 시 ZIP에 동봉된 이미지를 로드하므로 폐쇄망에서도 실행할 수 있습니다.

| 작업 | Windows PowerShell | Linux Bash |
|---|---|---|
| 최초 설치 | `.\install-lab.ps1` | `bash install-lab.sh` |
| 시작·재시작 | `.\start-lab.ps1` | `bash start-lab.sh` |
| 실험 종료 후 정지 | `.\stop-lab.ps1` | `bash stop-lab.sh` |

시작 후 [실험 UI](http://127.0.0.1:8765)를 엽니다. 정지해도 기존 캡처는 설치 폴더에 보관됩니다.

## 첫 HTTP/2 캡처

1. **대상 서버**에서 **실험용 Origin**과 **TLS (HTTPS) · 8443**을 고릅니다.
2. **경유 프록시**에서 **내장 MITM**, 방식은 **리버스**, 리스너는 **모드 기본값**으로 둡니다. 클라이언트 → Envoy → MITM → Origin 경로가 구성도에 표시됩니다.
3. **요청 구성**에서 HTTP/2, 클라이언트 2개, Origin 1개, 클라이언트당 동시 요청 4개를 선택합니다.
4. **TLS 검증 및 캡처 옵션**에서 복호화된 HTTP 패킷 저장을 선택하고 **캡처 및 전송**을 누릅니다. 응답 수와 오류 수를 확인하고 결과에서 원하는 파일을 저장합니다.

외부 프록시를 시험할 때는 Envoy에서 접근할 수 있는 IP와 포트를 입력합니다. 포워드 모드는 터널 안에서 두 번째 CONNECT로 목적지를 전달합니다. 리버스 모드는 외부 프록시에 업스트림을 미리 설정하고 해당 리스너의 평문 또는 TLS 설정을 UI와 맞춥니다. 직접 입력한 서버 URL도 같은 방법으로 실험할 수 있습니다.

## 캡처 파일 사용하기

| 파일 | 관측 구간 또는 용도 |
|---|---|
| `front.pcap` | 클라이언트 → Envoy |
| `middle.pcap` | Envoy → 내장 MITM 또는 외부 프록시 |
| `back.pcap` | 내장 MITM → 대상 서버. 외부 프록시의 송신 구간은 해당 프록시에서 수집 |
| `*-decrypted.pcapng` | 내장 MITM의 복호화 결과. Wireshark에서 HTTP 요청이나 H2 헤더 확인 |
| `client.keys`, `proxy.keys` | 키 저장을 선택했을 때 생성되는 TLS 키 로그. Wireshark의 TLS 설정에서 같은 실행의 파일 지정 |

원본은 항상 `captures/<실행 ID>/`에 있습니다. UI의 **저장**은 브라우저를 사용하는 컴퓨터로 파일을 복사할 때 씁니다. 지원 브라우저에서는 위치와 이름을 고를 수 있고, 그 외에는 브라우저의 다운로드 설정을 따릅니다. 서버에서 원본을 직접 열어도 됩니다.

이미지 검증, 원격 서버 접속, 배포 ZIP을 만드는 방법은 [폐쇄망 배포 안내](OFFLINE.md)에 있습니다.
