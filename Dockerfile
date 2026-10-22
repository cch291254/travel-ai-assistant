FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/models   
ENV HF_HUB_OFFLINE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt .

RUN python -m pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130
RUN python -m pip install --no-cache-dir -r requirements.docker.txt

COPY app ./app

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]