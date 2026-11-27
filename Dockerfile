# مونتير — دار الإبداع للحلول البرمجية
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg chromium nodejs npm fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine ./engine
RUN cd engine && npm install --omit=dev --silent
COPY server ./server
COPY web ./web
COPY seed ./seed
ENV CHROME_PATH=/usr/bin/chromium PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    MONTEER_DATA=/app/data MONTEER_LOWMEM=1 X264_PRESET=veryfast PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
WORKDIR /app/server
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
