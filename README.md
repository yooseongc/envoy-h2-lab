# HTTP 프록시 실험실

Windows Docker Desktop을 Linux 컨테이너 모드로 시작하고 이 디렉터리에서 실행합니다.

```powershell
.\start-lab.ps1
Start-Process http://127.0.0.1:8765
```

UI에서 대상 서버와 경유 프록시(내장 MITM 또는 외부 프록시)를 선택하고 요청 수를 지정한 뒤 **캡처 및 전송**을 누릅니다. 두 경로 모두 Envoy를 통과합니다.

## 기존 Nginx 비교 실험 (API)

기존 실험에서는 두 클라이언트를 running 상태로 두고 ‘Nginx 경유 · HTTP/2 유지’, 클라이언트당 동시 요청 4개, ‘캡처 및 전송’을 선택합니다. 각 요청은 독립 HTTP/1.1 연결에서 출발합니다. Envoy는 워커 1개에서 h2c prior knowledge로 Nginx에 연결합니다. Origin은 동시 요청이 겹치도록 응답을 600ms 지연합니다. 결과의 reverse_received 값은 Nginx가 실제 수신한 프로토콜입니다. xff는 Origin이 수신한 헤더입니다. 기본 경로는 Nginx와 Origin 모두 HTTP/2를 사용하는 모드입니다. HTTP/2 → HTTP/1.1은 다운그레이드 비교용입니다.

| 파일 | 캡처 위치 | 볼 내용 |
|---|---|---|
| front.pcap | Envoy 수신 측 10000/tcp | 각 클라이언트의 H1 요청 및 서로 다른 소스 IP |
| middle.pcap | Nginx 수신 측 8080/tcp | H2 스트림 ID, XFF, TCP 연결 수. H1 비교 모드는 같은 포트에서 H1 사용 |
| back.pcap | Origin 수신 측 8000/tcp | 선택한 모드에 따른 H2 또는 H1 요청, XFF 체인, X-Reverse-Protocol |

Wireshark에서 h2c 실험의 middle.pcap을 열고 필요하면 Analyze → Decode As에서 TCP 8080을 HTTP2로 지정합니다. 표시 필터 `http2.type == 1`로 HEADERS를 찾고 같은 `tcp.stream`에서 서로 다른 `http2.streamid`를 확인합니다. TCP 스트림 번호는 파일별로 부여됩니다. URI의 실행 ID/클라이언트명/요청 번호로 서로 다른 캡처를 대조하세요. tshark로도 볼 수 있습니다.

```powershell
tshark -r middle.pcap -d tcp.port==8080,http2 -Y 'http2.type == 1' -T fields -e tcp.stream -e http2.streamid -e http2.headers.path
```

HTTP/1.1 경유 모드로 다시 실행해 middle.pcap의 TCP 대화 수를 비교하세요. 서버 직결 경로는 Envoy → Origin이므로 middle.pcap에 해당 요청이 없습니다. UI에서 클라이언트를 중지하면 다음 실행부터 남은 클라이언트만 전송합니다. 모든 클라이언트가 중지되면 실행을 거부합니다.

서버가 여러 대면 back.pcap은 모든 서버 연결이 보이는 송신 측(Nginx, 직결 모드는 Envoy)에서 수집합니다. 실행 결과에는 세 구간 TCP 연결 수, H2 스트림 수, XFF 일치 수, 응답 서버별 요청 수가 표시됩니다. 실행 폴더의 manifest.json은 클라이언트·서버 IP, responses.json은 실제 응답, verification.json은 패킷별 검증 근거를 담습니다.

## 경로 선택과 DooD

경로는 요청마다 X-Lab-Route 헤더로 미리 정의한 Envoy route를 선택합니다. UI 컨테이너만 호스트 Docker 소켓을 마운트하고 Docker SDK로 현재 Compose 프로젝트의 클라이언트 시작·중지 및 고정된 요청/캡처 명령을 실행합니다. 각 tap은 해당 수신 컨테이너의 네트워크 네임스페이스를 공유합니다. 캡처는 실험 시작 시 준비하고 종료 직후 닫습니다. 파일은 captures/<실행 ID>/ 아래에 남습니다. UI는 127.0.0.1:8765로만 게시합니다. Docker 소켓은 호스트 엔진 관리 권한이므로 개인 로컬 실험 환경을 전제로 합니다. 클라이언트·서버 수를 1~4로 지정하면 UI가 실험용 이미지와 고정 명령으로 필요한 컨테이너를 생성합니다. ‘대수 적용’을 누르면 실험 전에도 실제 목록을 볼 수 있고 실험 후에도 구성이 유지됩니다. 대수를 줄이면 초과 인스턴스를 제거합니다. 개별 중지한 클라이언트는 요청을 보내지 않습니다. SVG의 점은 해당 PCAP의 캡처 위치입니다.

## 확인 및 종료

```powershell
docker compose ps -a
docker compose logs --tail 80 envoy reverse ui
docker compose run --rm --no-deps envoy --mode validate -c /etc/envoy/lab.yaml
docker compose down --remove-orphans
```

캡처 시작 실패 시 해당 실행 폴더의 front.log, middle.log, back.log에서 tcpdump 오류를 확인하세요. 첫 실행은 이미지 다운로드 및 빌드가 필요합니다. 프로젝트 폴더를 Docker Desktop이 읽고 쓸 수 있어야 합니다.

## 실제 검증 결과 (2026-11-20 23:02–23:04 KST)

`docker compose up -d --build`로 9개 서비스를 기동한 뒤 UI에서 두 클라이언트 running, 클라이언트당 동시 요청 4개로 각 모드를 실행했습니다. 두 실행 모두 8개 요청이 HTTP 200으로 완료됐고 세 구간의 PCAP과 종료 마커가 생성됐습니다. tcpdump 로그의 커널 드롭은 모두 0입니다. Envoy 자체 설정 검증도 통과했습니다.

| 모드 | 실행 ID (captures 하위 폴더) | front TCP 연결 | middle TCP 연결 | back TCP 연결 |
|---|---|---:|---:|---:|
| h2c | `20261120T140229Z-50d4b698` | 8 | 1 | 8 |
| HTTP/1.1 경유 | `20261120T140300Z-28f5eb52` | 8 | 8 | 8 |

h2c의 middle.pcap에서 다음 요청은 모두 `tcp.stream=0`을 공유했습니다. XFF는 각 H2 HEADERS 프레임에서 추출했으며 front.pcap의 같은 URI 요청 소스 IP와 8개 모두 일치했습니다.

| 클라이언트 | 요청 번호 → H2 스트림 ID | middle XFF = front 소스 IP |
|---|---|---|
| client-a | 0 → 11, 1 → 13, 2 → 15, 3 → 9 | `172.21.0.3` |
| client-b | 0 → 7, 1 → 3, 2 → 5, 3 → 1 | `172.21.0.2` |

middle의 8개 요청 HEADERS는 3.574ms 안에 도착했고 모두 첫 응답보다 앞섰습니다. 따라서 서로 다른 클라이언트의 요청이 같은 TCP 연결에서 동시에 진행 중인 서로 다른 H2 스트림을 사용했습니다. HTTP/1.1 경유 모드도 8개 요청이 첫 응답 전에 도착했으며 서로 다른 TCP 연결 8개를 사용했습니다. 연결 수는 각 파일 전체의 고유 `tcp.stream` 개수입니다.

back.pcap에서는 두 모드 모두 XFF가 `클라이언트 IP, 172.24.0.3`으로 확인됐습니다. 뒤의 IP는 middle에서 관측된 Envoy 소스 IP입니다. UI 응답의 `reverse_received`는 각각 `HTTP/2.0`, `HTTP/1.1`이고 `origin_protocol`은 모두 `HTTP/1.1`입니다. IP와 스트림 번호는 이번 실행에 해당하며 재생성 시 달라질 수 있습니다.

재검증하려면 Python과 tshark가 PATH에 있는 환경에서 실행합니다.

```powershell
python verify_captures.py captures/20261120T140229Z-50d4b698 captures/20261120T140300Z-28f5eb52
```

스크립트는 요청 경로·응답 200·동시 진행·구간별 연결 수·스트림별 XFF·back XFF 체인을 검사하고 각 실행 폴더에 `verification.json`을 저장합니다. 한 TCP 패킷에 여러 H2 프레임이 들어갈 수 있으므로 패킷 단위 필드 목록을 단순히 짝짓지 않고 PDML의 각 H2 프레임을 분석합니다. 이번 실험에서는 서비스 설정 수정 없이 두 모드 모두 통과했습니다.

Windows에서 PCAP 저장은 시작 스크립트가 띄우는 로컬 도우미(127.0.0.1:8766)를 사용합니다. 버튼을 누르면 Windows의 다른 이름으로 저장 창에서 위치와 .pcap 파일명을 선택합니다. 취소하면 파일을 만들지 않습니다. PC 재시작 후 프로젝트에서 `.\start-lab.ps1`을 실행하세요.

## HTTPS 분석과 MITM

클라이언트는 Envoy(10001)에 CONNECT 터널을 엽니다. 내장 MITM의 공개 CA는 해당 실행의 클라이언트에만 적용됩니다. 내장 MITM에서 HTTP/2는 TLS 협상이 필요하며 평문 HTTP 요청은 HTTP/1.1을 사용합니다.

| 파일 | 사용 방법 |
|---|---|
| front / middle / back.pcap | 구성도에 표시된 구간의 네트워크 캡처 |
| client.keys | HTTPS에서 키 저장을 선택한 경우 생성. 클라이언트와 TLS 상대 사이의 세션 복호화 |
| proxy.keys | 내장 MITM + HTTPS 키 저장 시 생성. 프록시 양쪽의 TLS 세션 복호화 |
| flows.mitm | 내장 MITM이 기록한 HTTP 흐름. mitmproxy 또는 mitmweb의 읽기 모드로 열기 |

Wireshark → Preferences → Protocols → TLS → (Pre)-Master-Secret log filename에서 같은 실행의 키 파일을 선택합니다. 비표준 포트에서 프로토콜을 인식하지 못하면 Decode As에서 TLS로 지정합니다. 내장 MITM의 middle 포트는 8082, back 포트는 대상 URL의 포트입니다. 여러 실험의 파일을 혼동하지 않도록 Windows 저장 대화상자의 기본 파일명에 실행 ID를 넣습니다.

외부 프록시는 Envoy에서 접근 가능한 IP와 포트를 입력합니다. 포워드는 Envoy 터널 안에서 외부 프록시에 대상 주소로 두 번째 CONNECT를 보냅니다. 리버스는 외부 프록시에 upstream을 미리 설정해야 하며, Envoy 터널 안에서 바로 TLS 또는 평문 HTTP를 보냅니다. Host 및 TLS SNI(도메인인 경우)는 대상 URL 기준입니다. 프록시가 TLS를 종료하면 클라이언트 키로 관측할 수 있는 범위는 프록시 수신 측까지입니다. 외부 프로그램의 송신 PCAP과 TLS 키는 해당 프로그램에서 수집해야 합니다. 실제 외부 제품 연결은 사용자 환경에서 검증할 예정입니다. [구현 및 검증 계획](PROXY-PLAN.md)

실험용 Origin은 평문 HTTP(8000)와 TLS(8443)로 HTTP/1.1 및 HTTP/2를 받습니다. TLS 선택 시 터널 경로를 사용하며, 실험 도구는 실행 중인 Origin의 공개 인증서를 신뢰합니다. 외부 리버스 프록시에서는 리스너의 TLS 여부를 Origin과 독립적으로 선택할 수 있습니다. 실제 업스트림 주소와 인증서 신뢰는 해당 외부 프록시에 설정하세요.
내장 MITM은 기본 리버스 모드 또는 포워드 모드로 실행합니다. 포워드에서는 Envoy 터널 안에서 대상에 대한 두 번째 CONNECT를 보냅니다.
내장 MITM 리스너는 평문 TCP 또는 TLS를 선택합니다. 기본값은 포워드에서 평문 CONNECT, 리버스에서 대상 URL과 동일한 방식입니다. Envoy는 TLS를 전달하며, 클라이언트의 MITM 인증서 검증과 MITM의 Origin 인증서 검증은 실행별로 독립 설정합니다.

Windows·Linux 폐쇄망 설치 및 배포본 생성 절차는 [폐쇄망 배포 안내](OFFLINE.md)에 있습니다.
