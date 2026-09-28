FROM node:22-alpine AS build
WORKDIR /app
COPY package.json .
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache gettext
COPY --from=build /app/dist /usr/share/nginx/html
COPY public-config.js.template /usr/share/nginx/html/config.js.template
RUN printf '#!/bin/sh\nset -e\nenvsubst '\''${COMPARIFY_API_URL}'\'' < /usr/share/nginx/html/config.js.template > /usr/share/nginx/html/config.js\nexec nginx -g "daemon off;"\n' > /docker-entrypoint-custom.sh && chmod +x /docker-entrypoint-custom.sh
ENV COMPARIFY_API_URL=http://localhost:8000
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint-custom.sh"]
