# HTTP 프록시 실험실

클라이언트가 Envoy를 거쳐 내장 MITM 또는 외부 프록시로 보내는 HTTP 요청을 실험합니다. **클라이언트 → Envoy는 평문 HTTP/1.1 GET으로 고정됩니다.** Envoy가 실제 클라이언트 IP를 X-Forwarded-For(XFF)에 추가합니다. 요청 구성의 HTTP 버전과 TLS는 Envoy의 업스트림 연결에 적용됩니다.

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

1. **대상 서버**에서 실험용 Origin 또는 직접 입력한 URL을 선택합니다. Origin의 평문/TLS는 프록시 → Origin 구간의 설정입니다.
2. 기본값인 **내장 MITM · 리버스**, **Envoy 업스트림 HTTP/2**, **프록시 리스너 연결 TLS**를 유지합니다. 외부 프록시로 바꾸면 Envoy에서 접근 가능한 프록시 IP와 포트를 입력합니다.
3. 실험용 Origin을 여러 대 사용하면 **클라이언트별 대상 호스트**에서 각각 선택할 수 있습니다. 기본 선택은 클라이언트 번호 순으로 Origin을 분배하며, 상단에서 인스턴스를 지정하면 공통 기본 대상이 됩니다. 클라이언트 수와 클라이언트당 동시 요청 수를 정한 뒤 **캡처 및 전송**을 누릅니다. 실험용 Origin을 선택하면 결과 표에 클라이언트별 처리 서버와 Origin이 실제로 수신한 XFF가 표시됩니다.
4. Wireshark에서 `front.pcap`의 GET 소스 IP와 `middle-decrypted.pcapng`의 요청 HEADERS 안에 있는 `x-forwarded-for`를 비교합니다. `x-lab-client`와 `x-lab-request`로 같은 요청을 찾을 수 있습니다. 여러 요청의 TCP 스트림 번호가 같고 H2 스트림 ID가 다르면 해당 업스트림 연결을 공유한 것입니다.

리버스 모드에서는 Envoy가 프록시 리스너에 HTTP 요청을 직접 보냅니다. 포워드 모드는 Envoy의 업스트림 쪽에서 HTTP/1.1 CONNECT로 목적 서버 터널을 만들고 그 안에 선택한 HTTP 버전의 GET을 보냅니다. 포워드에서 리스너 TLS는 CONNECT 자체를 보호하며, 터널 내부 TLS는 목적 URL의 스킴을 따릅니다.

## 캡처 파일 사용하기

| 파일 | 관측 구간 또는 용도 |
|---|---|
| `front.pcap` | 클라이언트 → Envoy |
| `middle.pcap` | Envoy → 내장 MITM 또는 외부 프록시 |
| `back.pcap` | 내장 MITM → 대상 서버. 외부 프록시의 송신 구간은 해당 프록시에서 수집 |
| `*-plaintext.pcapng` | TLS를 제거한 평문 TCP 재구성. Follow TCP Stream, HTTP/1.1의 Follow HTTP Stream, HTTP/2의 Follow HTTP/2 Stream에 사용 |
| `*-decrypted.pcapng` | 내장 MITM 구간의 원본 프레임과 실행별 TLS 복호화 키를 함께 담은 Wireshark 파일 |
| `envoy.keys`, `proxy.keys` | 키 저장을 선택했을 때 생성되는 TLS 키 로그. Wireshark의 TLS 설정에서 같은 실행의 파일 지정 |

원본은 항상 `captures/<실행 ID>/`에 있습니다. UI에서 **파일명 다운로드**를 누르면 브라우저의 다운로드 설정에 따라 저장합니다. 위치와 이름을 직접 고르려면 지원 브라우저에서 **다른 이름으로 저장**을 누르세요. 저장 창이 차단된 환경에서도 다운로드 링크는 독립적으로 작동합니다. 서버에서 원본을 직접 열어도 됩니다.

이미지 검증, 원격 서버 접속, 배포 ZIP을 만드는 방법은 [폐쇄망 배포 안내](docs/OFFLINE.md)에 있습니다.

## Wireshark에서 스트림 추적하기

**요청과 응답을 따라가려면** `middle-plaintext.pcapng` 또는 `back-plaintext.pcapng`를 엽니다. HTTP/1.1 요청을 선택하고 **Follow → HTTP Stream**, HTTP/2 HEADERS나 DATA를 선택하고 **Follow → HTTP/2 Stream**을 누릅니다. **Follow → TCP Stream**은 연결의 평문 바이트 전체를 보여 줍니다. HTTP/2 헤더는 전송 형식인 HPACK과 바이너리 프레임이므로, 읽을 수 있는 헤더 이름·값은 HTTP/2 Follow에서 확인하세요.

평문 파일은 연결 양쪽의 IP와 복호화된 데이터 방향·시각을 이용해 TCP 헤더를 재구성합니다. 자동 HTTP 인식을 위해 서버 포트를 80으로 표시합니다. 패킷 경계·시퀀스·재전송 분석에는 원본 캡처를 사용하세요.

**원본 패킷을 분석하려면** 새 실행의 `middle-decrypted.pcapng` 또는 `back-decrypted.pcapng`를 엽니다. TLS 키가 파일에 들어 있어 별도 키 설정 없이 분석할 수 있습니다. 이 파일을 공유하면 수신자도 캡처 내용을 복호화할 수 있습니다.

- TCP 연결은 `tcp.stream == 0`처럼 필터링합니다. 원본 SYN, ACK, 시퀀스 번호와 캡처 시각이 보존됩니다. Follow TCP Stream에는 전송선에 실린 TLS 바이트가 표시됩니다.
- HTTP/2는 `http2.headers.method`로 요청을 찾고 해당 프레임에서 **Follow → HTTP/2 Stream**을 선택합니다. 같은 TCP 연결의 요청을 구분할 때는 `tcp.stream == 0 && http2.streamid == 1`처럼 두 번호를 함께 지정합니다. TLS 평문은 **Follow → TLS Stream**에서 볼 수 있습니다.
- 비표준 포트에서 TCP로만 보이면 **Analyze → Decode As**에서 해당 포트를 TLS로 지정합니다. 평문 CONNECT로 시작하는 포워드 리스너는 HTTP로 지정합니다. 프록시 접속과 터널이 모두 TLS인 경우 Origin 요청 분석에는 프록시 송신 측 `back-decrypted.pcapng`를 사용하세요.
- v1.1.0까지의 `*-decrypted.pcapng`는 애플리케이션 데이터만 담았습니다. 해당 실행의 원본 PCAP과 키 로그가 남아 있으면 Wireshark의 TLS 설정에서 키 로그를 지정해 열 수 있습니다.

## 소스 폴더

| 위치 | 내용 |
|---|---|
| `app/` | UI, 실험 제어, 클라이언트·Origin, 패킷 분석, 도구 이미지 |
| `proxy/` | Envoy 설정과 내장 MITM의 실행·요청별 라우팅 |
| `deploy/` | 배포 ZIP 생성, Windows·Linux 실행 스크립트 |
| `docs/` | 폐쇄망 배포 안내와 실험 구성 문서 |
| `captures/`, `dist/` | 로컬 실험 결과와 생성한 배포본 |

소스 체크아웃에서는 Windows의 `deploy/windows/start-lab.ps1` 또는 Linux의 `bash deploy/linux/start-lab.sh`로 시작합니다. 릴리즈 ZIP은 기존처럼 압축을 푼 폴더에서 바로 시작합니다.
