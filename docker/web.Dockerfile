# =============================================================================
# Stage 1: Build the React + TypeScript 7 + Vite 8 SPA (Debian glibc for native binaries)
# =============================================================================
FROM node:22.14.0-bookworm-slim AS builder

WORKDIR /app

COPY kivy/web/package.json kivy/web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY kivy/web/ ./

ARG VITE_BG_API_BASE=""
ENV VITE_BG_API_BASE=${VITE_BG_API_BASE}

RUN npm run build

# =============================================================================
# Stage 2: Lightweight non-root static runtime using Caddy Alpine
# =============================================================================
FROM caddy:2.9.1-alpine AS runtime

RUN addgroup -g 10001 -S appgroup \
    && adduser -u 10001 -S appuser -G appgroup \
    && mkdir -p /srv /config/caddy /data/caddy \
    && chown -R appuser:appgroup /srv /config /data

COPY --chown=appuser:appgroup --from=builder /app/dist /srv

RUN cp /usr/bin/caddy /usr/bin/caddy.unpriv \
    && mv /usr/bin/caddy.unpriv /usr/bin/caddy \
    && printf ':8080 {\n\
    root * /srv\n\
    encode zstd gzip\n\
    handle /healthz {\n\
        respond "OK" 200\n\
    }\n\
    handle /api/* {\n\
        reverse_proxy sketch-bg-api:7000\n\
    }\n\
    @immutable path /assets/* /hands/*\n\
    header @immutable Cache-Control "public, max-age=31536000, immutable"\n\
    handle {\n\
        try_files {path} /index.html\n\
        file_server\n\
    }\n\
}\n' > /etc/caddy/Caddyfile

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
