FROM python:3.12-alpine
ARG UPSTREAM_PROXY
EXPOSE 8888
RUN apk add --no-cache openssl
RUN mkdir -p /etc/pproxy \
    && openssl genrsa -out /etc/pproxy/server.key 2048 \
    && openssl req -new -key /etc/pproxy/server.key -out /etc/pproxy/server.csr \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" \
    && openssl x509 -req -days 365 -in /etc/pproxy/server.csr -signkey /etc/pproxy/server.key -out /etc/pproxy/server.crt
RUN pip install --no-cache-dir pproxy[accelerated]==2.7.9
RUN echo "#!/bin/sh" > /usr/local/bin/start-proxy.sh \
    && echo "pproxy -r http://${UPSTREAM_PROXY} -l http+socks4+socks5://:8888 -v --ssl /etc/pproxy/server.crt,/etc/pproxy/server.key" >> /usr/local/bin/start-proxy.sh \
    && chmod 755 /usr/local/bin/start-proxy.sh
ENTRYPOINT [ "/usr/local/bin/start-proxy.sh" ]
