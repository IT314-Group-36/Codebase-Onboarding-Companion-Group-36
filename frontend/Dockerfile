# syntax=docker/dockerfile:1
# Stages: deps -> dev (hot reload, used by docker-compose.dev.yml) | build -> prod (nginx, default)

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- development: Vite dev server with hot reload ----
FROM deps AS dev
COPY . .
ENV VITE_PROXY_TARGET=http://api:8000
EXPOSE 80
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80"]

# ---- production build ----
FROM deps AS build
COPY . .
# The browser calls /api/..., nginx (below) forwards it to the api container.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ---- production runtime ----
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
