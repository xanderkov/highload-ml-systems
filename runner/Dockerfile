FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# RLIMIT_NPROC counts a UID's tasks across containers on the same kernel.
# Avoid the shared development UID 1000, which can already exceed our limit.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin bench \
 && chown -R bench:bench /app
USER bench
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
