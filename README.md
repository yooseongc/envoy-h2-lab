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
4. **TLS 검증 및 캡처 옵션**에서 Wireshark 추적용 PCAPNG 저장을 선택하고 **캡처 및 전송**을 누릅니다. 응답 수와 오류 수를 확인하고 결과에서 원하는 파일을 저장합니다.

외부 프록시를 시험할 때는 Envoy에서 접근할 수 있는 IP와 포트를 입력합니다. 포워드 모드는 터널 안에서 두 번째 CONNECT로 목적지를 전달합니다. 리버스 모드는 외부 프록시에 업스트림을 미리 설정하고 해당 리스너의 평문 또는 TLS 설정을 UI와 맞춥니다. 직접 입력한 서버 URL도 같은 방법으로 실험할 수 있습니다.

## 캡처 파일 사용하기

| 파일 | 관측 구간 또는 용도 |
|---|---|
| `front.pcap` | 클라이언트 → Envoy |
| `middle.pcap` | Envoy → 내장 MITM 또는 외부 프록시 |
| `back.pcap` | 내장 MITM → 대상 서버. 외부 프록시의 송신 구간은 해당 프록시에서 수집 |
| `*-plaintext.pcapng` | TLS를 제거한 평문 TCP 재구성. Follow TCP Stream, HTTP/1.1의 Follow HTTP Stream, HTTP/2의 Follow HTTP/2 Stream에 사용 |
| `*-decrypted.pcapng` | 내장 MITM 구간의 원본 프레임과 실행별 TLS 복호화 키를 함께 담은 Wireshark 파일 |
| `client.keys`, `proxy.keys` | 키 저장을 선택했을 때 생성되는 TLS 키 로그. Wireshark의 TLS 설정에서 같은 실행의 파일 지정 |

원본은 항상 `captures/<실행 ID>/`에 있습니다. UI에서 **파일명 다운로드**를 누르면 브라우저의 다운로드 설정에 따라 저장합니다. 위치와 이름을 직접 고르려면 지원 브라우저에서 **다른 이름으로 저장**을 누르세요. 저장 창이 차단된 환경에서도 다운로드 링크는 독립적으로 작동합니다. 서버에서 원본을 직접 열어도 됩니다.

이미지 검증, 원격 서버 접속, 배포 ZIP을 만드는 방법은 [폐쇄망 배포 안내](OFFLINE.md)에 있습니다.

## Wireshark에서 스트림 추적하기

**요청과 응답을 따라가려면** `middle-plaintext.pcapng` 또는 `back-plaintext.pcapng`를 엽니다. HTTP/1.1 요청을 선택하고 **Follow → HTTP Stream**, HTTP/2 HEADERS나 DATA를 선택하고 **Follow → HTTP/2 Stream**을 누릅니다. **Follow → TCP Stream**은 연결의 평문 바이트 전체를 보여 줍니다. HTTP/2 헤더는 전송 형식인 HPACK과 바이너리 프레임이므로, 읽을 수 있는 헤더 이름·값은 HTTP/2 Follow에서 확인하세요.

평문 파일은 연결 양쪽의 IP와 복호화된 데이터 방향·시각을 이용해 TCP 헤더를 재구성합니다. 자동 HTTP 인식을 위해 서버 포트를 80으로 표시합니다. 패킷 경계·시퀀스·재전송 분석에는 원본 캡처를 사용하세요.

**원본 패킷을 분석하려면** 새 실행의 `middle-decrypted.pcapng` 또는 `back-decrypted.pcapng`를 엽니다. TLS 키가 파일에 들어 있어 별도 키 설정 없이 분석할 수 있습니다. 이 파일을 공유하면 수신자도 캡처 내용을 복호화할 수 있습니다.

- TCP 연결은 `tcp.stream == 0`처럼 필터링합니다. 원본 SYN, ACK, 시퀀스 번호와 캡처 시각이 보존됩니다. Follow TCP Stream에는 전송선에 실린 TLS 바이트가 표시됩니다.
- HTTP/2는 `http2.headers.method`로 요청을 찾고 해당 프레임에서 **Follow → HTTP/2 Stream**을 선택합니다. 같은 TCP 연결의 요청을 구분할 때는 `tcp.stream == 0 && http2.streamid == 1`처럼 두 번호를 함께 지정합니다. TLS 평문은 **Follow → TLS Stream**에서 볼 수 있습니다.
- 비표준 포트에서 TCP로만 보이면 **Analyze → Decode As**에서 해당 포트를 TLS로 지정합니다. 평문 CONNECT로 시작하는 포워드 리스너는 HTTP로 지정합니다. 프록시 접속과 터널이 모두 TLS인 경우 Origin 요청 분석에는 프록시 송신 측 `back-decrypted.pcapng`를 사용하세요.
- v1.1.0까지의 `*-decrypted.pcapng`는 애플리케이션 데이터만 담았습니다. 해당 실행의 원본 PCAP과 키 로그가 남아 있으면 Wireshark의 TLS 설정에서 키 로그를 지정해 열 수 있습니다.
