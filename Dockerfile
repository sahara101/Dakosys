FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/assets /app/fonts

COPY assets/next_airing_poster.jpg /app/assets/
COPY assets/gradient_top.png /app/assets/
COPY assets/gradient_bottom.png /app/assets/
COPY fonts/Juventus-Fans-Bold.ttf /app/fonts/

COPY *.py ./

VOLUME /app/config
VOLUME /app/data

ENV RUNNING_IN_DOCKER=true

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["--help"]
