FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
RUN addgroup -S archpilot && adduser -S archpilot -G archpilot
COPY --from=builder --chown=archpilot:archpilot /app/public ./public
COPY --from=builder --chown=archpilot:archpilot /app/.next/standalone ./
COPY --from=builder --chown=archpilot:archpilot /app/.next/static ./.next/static
USER archpilot
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=8s --start-period=20s --retries=4 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/api/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
CMD ["node", "server.js"]
