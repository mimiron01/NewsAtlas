FROM node:22-slim AS build
WORKDIR /app
# Relative by default so the built app calls the same origin it's served from (see
# Caddyfile, which reverse-proxies /api/* to the backend) — no separate domain/CORS
# needed in production. Override only if the frontend and API are deliberately split
# across different origins.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM node:22-slim
WORKDIR /app
# node:22-slim already ships a "node" user at UID 1000, so let useradd pick a free UID
# instead of hardcoding one (avoids "UID 1000 is not unique" build failures).
RUN npm install -g serve \
    && useradd --create-home --shell /usr/sbin/nologin appuser
COPY --from=build --chown=appuser:appuser /app/dist ./dist
USER appuser
EXPOSE 4173
CMD ["serve", "-s", "dist", "-l", "4173"]
