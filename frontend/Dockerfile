# Crossbid web app. Next.js standalone output; runs as a non-root user.
FROM node:22-alpine AS deps

WORKDIR /app

# Dependencies first, so a source-only change does not re-resolve the lock file.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci


FROM node:22-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Next.js inlines NEXT_PUBLIC_* into the client bundle at BUILD time, so these must be
# present here, not at run time. Passing them as `environment:` in Compose has no effect
# on the client bundle. Consequence: the image is environment-specific.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_AUTH_MODE=dev
ARG NEXT_PUBLIC_SUPABASE_URL=
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY=
# Dev-only tenant id sent as X-Dev-Company under NEXT_PUBLIC_AUTH_MODE=dev; see infra/.env.example.
ARG NEXT_PUBLIC_DEV_COMPANY_ID=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_DEV_COMPANY_ID=$NEXT_PUBLIC_DEV_COMPANY_ID

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build


FROM node:22-alpine AS runtime

# Non-root: the container never needs to write to its own filesystem.
RUN addgroup --system --gid 1001 crossbid \
 && adduser --system --uid 1001 --ingroup crossbid crossbid

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# `output: "standalone"` bundles the server and only the traced dependencies,
# so no node_modules install happens here.
COPY --from=builder --chown=crossbid:crossbid /app/public ./public
COPY --from=builder --chown=crossbid:crossbid /app/.next/standalone ./
COPY --from=builder --chown=crossbid:crossbid /app/.next/static ./.next/static

USER crossbid
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode<400?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
