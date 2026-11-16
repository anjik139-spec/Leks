FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        fonts-dejavu-core \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    "aiogram>=3.13" \
    "aiohttp>=3.10" \
    aiohttp-socks \
    redis \
    python-docx \
    reportlab \
    cairosvg \
    pillow \
    boto3 \
    edge-tts \
    pypdf \
    pymupdf \
    openpyxl \
    python-pptx \
    striprtf \
    pytesseract \
    python-dotenv \
    sentry-sdk

COPY . .

CMD ["python", "server.py"]
