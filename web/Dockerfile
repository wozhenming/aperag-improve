# Multi-stage build: the frontend is compiled inside Docker, so deployments
# only need `docker compose up -d --build` — no manual copy of local build
# artifacts to the server.

# ---- Stage 1: build ----
FROM apecloud-registry.cn-zhangjiakou.cr.aliyuncs.com/apecloud/node:20.18.0-alpine AS builder

WORKDIR /app

# Build-time env (same values as web/deploy/env.local.template; next build
# inlines NEXT_PUBLIC_* into the bundle — must match the deployed config)
ARG NEXT_PUBLIC_BASE_PATH=""
ARG NEXT_PUBLIC_DEFAULT_THEME=light
ARG NEXT_PUBLIC_DEFAULT_LOCALE=en-US
ENV NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH
ENV NEXT_PUBLIC_DEFAULT_THEME=$NEXT_PUBLIC_DEFAULT_THEME
ENV NEXT_PUBLIC_DEFAULT_LOCALE=$NEXT_PUBLIC_DEFAULT_LOCALE

# Install dependencies first (cached unless package.json/yarn.lock change)
COPY package.json yarn.lock* ./
RUN yarn install --frozen-lockfile

# Copy the full source (local node_modules/.next/build are excluded via .dockerignore)
COPY . .

# Compile: next build + build.mjs assembles the standalone output into ./build
RUN npx next build && npx ts-node scripts/build.mjs

# ---- Stage 2: runtime ----
FROM apecloud-registry.cn-zhangjiakou.cr.aliyuncs.com/apecloud/node:20.18.0-alpine

WORKDIR /app

COPY --from=builder /app/build ./

RUN yarn global add pm2

ENV HOSTNAME="0.0.0.0"
ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000

# server.js is created by next build from the standalone output
# https://nextjs.org/docs/pages/api-reference/config/next-config-js/output
CMD ["pm2-runtime", "start", "server.js"]
