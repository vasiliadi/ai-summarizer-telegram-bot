FROM alpine:latest
ARG UPSTREAM_PROXY
EXPOSE 8888
RUN apk add --no-cache tinyproxy
COPY /tinyproxy /etc/tinyproxy/
RUN echo "Upstream http ${UPSTREAM_PROXY}" >> /etc/tinyproxy/tinyproxy.conf
ENTRYPOINT ["tinyproxy", "-d"]
