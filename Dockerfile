FROM python:3.12-slim

ENV TZ=Africa/Kinshasa \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/Africa/Kinshasa /etc/localtime \
    && echo Africa/Kinshasa > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh \
    && mkdir -p /app/data/tiles

# Railway "Generate Service Domain" → type this port (or $PORT if Railway sets it).
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', os.environ.get('APP_PORT','8080')))"

CMD ["/app/start.sh"]
