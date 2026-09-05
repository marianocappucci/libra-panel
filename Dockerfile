# syntax=docker/dockerfile:1

# ── Frontend ────────────────────────────────────────────────────────────────
#
# Stage aparte: node no hace falta en la imagen final, sólo el resultado del
# build. Mismo patrón que los seis productos y el backoffice.
#
# `frontend/package.json` referencia `libra-ui` por `git+https`, que es lo que
# hace que el dev local en WSL funcione sin identidad SSH propia. Este stage
# reescribe esa URL a SSH con su propia deploy key de solo lectura. Un solo
# mount y un solo `SSH_AUTH_SOCK` alcanzan porque acá hay una sola dependencia
# privada — en el stage de Python, con dos, no alcanza (ver el comentario allá).
FROM node:22-slim AS frontend-build
WORKDIR /frontend
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*
RUN mkdir -p -m 0700 /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=ssh,id=libra-ui,target=/tmp/ssh-libra-ui.sock \
    SSH_AUTH_SOCK=/tmp/ssh-libra-ui.sock \
    sh -c 'git config --global url."ssh://git@github.com/marianocappucci/libra-ui.git".insteadOf "https://github.com/marianocappucci/libra-ui.git" && \
           npm ci'
COPY frontend/ .
RUN npm run build

# ── Backend ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# F1 (2026-09-05): las dependencias de terceros salen de `uv.lock`, no de la
# resolucion de pip del dia del build. Dos builds del mismo commit dan la misma
# imagen. El binario viene de la imagen oficial, pineada por version; el venv
# vive FUERA de /app porque el compose de dev monta ./:/app encima y lo taparia.
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_CACHE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Huso horario de Argentina, UTC-3 fijo y sin horario de verano. Estándar de la
# familia desde el 2026-08-12: afecta logs, cron y cualquier `datetime.now()`
# que se escape del helper. El helper (`libra_panel/fechas.py`) no depende de
# esto — lleva el offset adentro — pero los logs sí.
ENV TZ=America/Argentina/Buenos_Aires

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client tzdata && rm -rf /var/lib/apt/lists/*

# 🔑 **Sin cliente de Docker**, a diferencia de la imagen de libra-backoffice.
# Aquél administra instancias y para eso ejecuta `docker compose` como
# subproceso. El panel es de SOLO LECTURA hacia las sucursales: les habla por
# HTTP y nada más. Montarle el socket del host sería darle al contenedor del
# cliente control sobre el Docker del servidor.

# `pip install .` tiene que resolver libracore Y libraauth en un solo comando,
# así que un `SSH_AUTH_SOCK` global no alcanza: esa variable apunta a un solo
# socket a la vez. Cada dependencia usa su propio alias de Host con
# `IdentityAgent` (de qué socket sale la identidad) e `IdentityFile` apuntando
# a la clave PÚBLICA — que no es secreta y se hornea en la imagen — sólo para
# que ssh sepa qué fingerprint pedirle a ese agente.
#
# `IdentitiesOnly yes` por sí solo NO alcanza: sin un `IdentityFile` explícito
# ssh ofrece los paths default (id_rsa/id_ecdsa/…), que no existen en la
# imagen, y nunca llega a preguntarle nada al agente.
#
# Las claves privadas viajan por `--mount=type=ssh` y se descartan con la capa:
# ninguna queda en la imagen.
RUN mkdir -p -m 0700 /root/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG7oB3H2Rd+xsO/qCUk5aCA14/5GaQFMSh1U0ErJjG55 vps-donweb-libracore-deploy-key\n' > /root/.ssh/id_libracore.pub \
    && printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID0FOGgyaywQLO6J583j9+MG71a13oNpXoxOAAcV9Cbp vps-donweb-libraauth-deploy-readonly\n' > /root/.ssh/id_libraauth.pub \
    && printf 'Host github-libracore\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityFile /root/.ssh/id_libracore.pub\n  IdentityAgent /tmp/ssh-libracore.sock\n  IdentitiesOnly yes\n\nHost github-libraauth\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityFile /root/.ssh/id_libraauth.pub\n  IdentityAgent /tmp/ssh-libraauth.sock\n  IdentitiesOnly yes\n' > /root/.ssh/config \
    && chmod 600 /root/.ssh/config /root/.ssh/id_libracore.pub /root/.ssh/id_libraauth.pub

COPY backend/ .

# Fuera de /app a propósito, igual que en los productos: si algún día el
# compose monta el checkout sobre /app para desarrollo, un dist copiado adentro
# quedaría tapado por el host. `FRONTEND_DIST` (ver `app.py`) apunta acá por
# defecto.
COPY --from=frontend-build /frontend/dist /opt/frontend-dist

RUN --mount=type=ssh,id=libracore,target=/tmp/ssh-libracore.sock \
    --mount=type=ssh,id=libraauth,target=/tmp/ssh-libraauth.sock \
    git config --global url."ssh://git@github-libracore/marianocappucci/libracore.git".insteadOf "https://github.com/marianocappucci/libracore.git" \
    && git config --global url."ssh://git@github-libraauth/marianocappucci/libraauth.git".insteadOf "https://github.com/marianocappucci/libraauth.git" \
    && uv sync --frozen --no-dev --no-editable \
    && git config --global --unset url."ssh://git@github-libracore/marianocappucci/libracore.git".insteadOf \
    && git config --global --unset url."ssh://git@github-libraauth/marianocappucci/libraauth.git".insteadOf

# Los inyecta el build (`--build-arg`). Es el dato que delata un contenedor que
# "responde 200" pero está corriendo la imagen anterior.
ARG APP_VERSION=desconocida
ARG APP_COMMIT=desconocido
ENV APP_VERSION=$APP_VERSION APP_COMMIT=$APP_COMMIT

EXPOSE 8000

CMD ["uvicorn", "libra_panel.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
