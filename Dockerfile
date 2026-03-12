# ===== Build Stage =====
FROM node:22-alpine AS builder

RUN npm i -g pnpm@10

WORKDIR /app

# Install dependencies first (cache layer)
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY packages/core/package.json packages/core/
COPY packages/main/package.json packages/main/
COPY packages/agent-director/package.json packages/agent-director/
COPY packages/agent-backend/package.json packages/agent-backend/
COPY packages/agent-frontend/package.json packages/agent-frontend/
COPY packages/agent-docs/package.json packages/agent-docs/
COPY packages/agent-git/package.json packages/agent-git/
COPY packages/dashboard-server/package.json packages/dashboard-server/

RUN pnpm install --frozen-lockfile

# Copy source and build
COPY tsconfig.base.json ./
COPY packages/ packages/

RUN pnpm build

# ===== Runtime Stage =====
FROM node:22-alpine AS runtime

RUN npm i -g pnpm@10

WORKDIR /app

COPY --from=builder /app/pnpm-lock.yaml /app/pnpm-workspace.yaml /app/package.json ./
COPY --from=builder /app/packages/ packages/
COPY --from=builder /app/node_modules/ node_modules/

# Don't run as root
RUN addgroup -g 1001 agent && adduser -u 1001 -G agent -s /bin/sh -D agent
USER agent

ENV NODE_ENV=production

EXPOSE 3001

CMD ["node", "packages/main/dist/index.js"]
