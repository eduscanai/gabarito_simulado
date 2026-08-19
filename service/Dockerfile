# Build from the REPO ROOT (not from service/), because this service embeds
# the OMRChecker core (src/, main.py) via subprocess, the same way
# avaliacao_web/app.py already does locally:
#
#   docker build -f service/Dockerfile -t omr-service .
#   docker run --rm -p 8000:8000 -e OMR_SERVICE_TOKEN=changeme omr-service

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY main.py ./main.py
COPY src ./src
COPY service ./service

RUN pip install --no-cache-dir -r service/requirements.txt

WORKDIR /app/service

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
