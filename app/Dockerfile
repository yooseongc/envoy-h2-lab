FROM python:3.13-alpine
RUN apk add --no-cache openssl tcpdump tshark && pip install --no-cache-dir docker==7.1.0 hypercorn==0.17.3 PyYAML==6.0.3
WORKDIR /lab
COPY *.py *.html ./
