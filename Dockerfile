# tandem hub — stdlib-only Python, so the whole build is a COPY. No pip, no
# requirements.txt, no multi-stage: there is nothing to compile or install.
FROM python:3.13-alpine

# Explicit uid: the k8s manifest's fsGroup matches it so the PVC mounted at
# /data (STATE_DIRECTORY) is writable without running as root.
RUN addgroup -g 10001 -S tandem && adduser -u 10001 -S -G tandem tandem

WORKDIR /app
COPY hub/ hub/

USER tandem
ENV STATE_DIRECTORY=/data \
    TANDEM_PORT=8712
EXPOSE 8712

# server.py is env-driven (see its docstring): the same entrypoint the NixOS
# module execs, minus systemd. Gateway worker stays off unless
# TANDEM_GATEWAY_MEMBER is set — the containerized hub is ledger + HTTP API.
ENTRYPOINT ["python", "-m", "hub.server"]
