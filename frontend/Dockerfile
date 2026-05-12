# stage 1: build
FROM node:22-slim AS builder

RUN corepack enable && corepack prepare pnpm@10 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# stage 2: serve with nginx
# pinned to the same minor used by the docker-compose nginx
# reverse-proxy service. `apk upgrade` picks up alpine OS-level
# patches that lag the base-image rebuild cadence (e.g. the
# nghttp2-libs fix for CVE-2026-27135 landed in 1.68.1-r0 but
# was not yet in the nginx:1.27-alpine layer at last pull).
FROM nginx:1.27-alpine

RUN apk upgrade --no-cache \
    && apk add --no-cache curl

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["curl", "-f", "http://localhost/"]
