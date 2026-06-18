FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy site content
COPY index.html /usr/share/nginx/html/index.html

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

LABEL org.opencontainers.image.source="https://github.com/winslowb/chicago-neighborhood-events"
LABEL org.opencontainers.image.description="Chicago Neighborhood Events & Closures"
LABEL org.opencontainers.image.licenses="MIT"
