# ============================================================
# Stage 1 — build React app
# ============================================================
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --silent
COPY . .

# REACT_APP_API_URL is injected at build time so the SPA knows
# where to send API requests when running in OpenShift.
# Default falls back to same-origin (proxied via nginx).
ARG REACT_APP_API_URL=""
ENV REACT_APP_API_URL=${REACT_APP_API_URL}

RUN npm run build

# ============================================================
# Stage 2 — serve with nginx
# ============================================================
FROM nginx:1.25-alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/paygate.conf

# Copy built React app
COPY --from=builder /app/build /usr/share/nginx/html

# OpenShift runs containers as arbitrary UID in group 0.
# nginx must be able to write its tmp/cache dirs.
RUN chown -R 0:0 /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    chmod -R g+rwX /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    # nginx.pid location that a non-root user can write
    touch /var/run/nginx.pid && \
    chown 0:0 /var/run/nginx.pid && chmod g+rw /var/run/nginx.pid

# Switch to non-root (arbitrary uid, root group is fine for OpenShift)
USER 1001

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
