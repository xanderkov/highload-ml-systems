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
# Раздел «LLM»: llama-server (с CPU-бэкендами от sse42 до avx512 — выбирает
# сам по процессору) и модель GGUF; харнессы запускают сервер подпроцессом.
COPY --from=ghcr.io/ggml-org/llama.cpp:server-b12199 /app /opt/llama
ENV LD_LIBRARY_PATH=/opt/llama
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/models && python -c "import urllib.request as u; u.urlretrieve('https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q8_0.gguf', '/opt/models/qwen05-q8.gguf')"
COPY . .
# RLIMIT_NPROC counts a UID's tasks across containers on the same kernel.
# Avoid the shared development UID 1000, which can already exceed our limit.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin bench \
 && chown -R bench:bench /app \
 && mkdir /models && chown bench:bench /models
# /models — точка монтирования тома model_repo (репозиторий моделей Triton):
# новый именованный том наследует владельца каталога образа.
USER bench
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
