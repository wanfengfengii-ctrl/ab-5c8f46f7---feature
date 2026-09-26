FROM nginx:1.27-alpine

# Site assets and reverse-proxy configuration.
COPY html /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=5 \
    CMD wget -q --spider http://127.0.0.1/index.html || exit 1
