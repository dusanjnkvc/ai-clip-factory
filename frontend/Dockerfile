FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=$API_ORIGIN
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup -S factory && adduser -S factory -G factory
COPY --from=build --chown=factory:factory /app/.next/standalone ./
COPY --from=build --chown=factory:factory /app/.next/static ./.next/static
COPY --from=build --chown=factory:factory /app/public ./public
USER factory
EXPOSE 3000
CMD ["node", "server.js"]
