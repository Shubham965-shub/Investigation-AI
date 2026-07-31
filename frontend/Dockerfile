# ── Stage 1: Build ────────────────────────────────────────────
FROM node:24-alpine AS builder

WORKDIR /build

# Lockfile-only copy first so `npm ci` is cached independently of source changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite bakes VITE_* vars in at BUILD time, not runtime — override via
# `docker build --build-arg VITE_API_BASE_URL=https://api.example.com/api`
# for non-local deployments; defaults to the same value frontend/.env.example
# ships with.
ARG VITE_API_BASE_URL=http://localhost:8000/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build


# ── Stage 2: Serve ────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
