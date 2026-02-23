FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY web/package*.json ./
RUN npm install --legacy-peer-deps
COPY web/ .
RUN npm run build

FROM python:3.9-slim
WORKDIR /app

COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

RUN mkdir -p /app/assets /app/fonts /app/web

COPY assets/next_airing_poster.jpg /app/assets/
COPY assets/gradient_top.png /app/assets/
COPY assets/gradient_bottom.png /app/assets/
COPY fonts/Juventus-Fans-Bold.ttf /app/fonts/

COPY *.py ./

COPY --from=frontend-builder /frontend/out /app/web/out

VOLUME /app/config
VOLUME /app/data

ENV RUNNING_IN_DOCKER=true

EXPOSE 8000

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--help"]
