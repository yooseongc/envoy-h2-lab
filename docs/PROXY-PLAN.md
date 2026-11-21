# URL 프록시 실험 구현 및 검증 계획

1. 클라이언트는 Envoy에 평문 HTTP/1.1 GET을 보낸다. Envoy가 실제 접속 IP로 XFF를 추가한다.
2. 기본 경로는 Envoy → 내장 리버스 MITM의 HTTP/2 over TLS다. 외부 IP·포트와 포워드 모드도 지원한다. CONNECT는 포워드 업스트림에만 사용한다. 내장 리버스는 실행 시 등록한 Host/:authority 표를 요청별로 조회하고, 등록되지 않은 대상에는 421을 반환한다.
3. front의 요청 소스 IP와 middle의 H2 HEADERS에 있는 XFF를 요청별로 비교한다. 같은 TCP 연결의 서로 다른 H2 스트림에 여러 클라이언트 요청이 실리는지 확인한다.
4. 내장 MITM은 middle·back의 원본과 Wireshark용 평문 TCP 파일을 제공한다. 외부 프록시는 Envoy 송신 측까지 캡처한다.
