FROM python:3.12-slim
WORKDIR /app
# CPU-only torch: the default PyPI x86_64 wheel drags in ~GBs of CUDA libs.
RUN if [ "$(uname -m)" = "x86_64" ]; then \
      pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch~=2.15"; \
    else \
      pip install --no-cache-dir "torch~=2.15"; \
    fi
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# RLIMIT_NPROC counts a UID's tasks across containers on the same kernel.
# Avoid the shared development UID 1000, which can already exceed our limit.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin bench \
 && chown -R bench:bench /app
USER bench
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
