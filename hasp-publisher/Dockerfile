FROM python:3.12-slim

WORKDIR /app

# Ensure Python logs stream immediately to 'docker logs'
ENV PYTHONUNBUFFERED=1 \
    TZ=America/New_York

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cyd_5inch_publisher.py .

CMD ["python", "cyd_5inch_publisher.py"]