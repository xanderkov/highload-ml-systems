"""Есть ли сервис vllm (профиль compose `vllm`) и готов ли он."""
from __future__ import annotations

import urllib.error
import urllib.request

URL = "http://vllm:8000"
MODEL = "q"
HOW_TO = (
    "Сервис vllm по умолчанию не запущен: ему нужно ~6 ГБ памяти, а режим bf16 — процессор с AVX-512 "
    "(в fp32 он вдвое медленнее и требует ещё больше памяти). Если это про вашу машину, остановите Triton "
    "и запустите vLLM:\n"
    "    docker compose stop triton\n"
    "    docker compose --profile vllm up -d vllm\n"
    "Первый старт скачивает модель и занимает пару минут; потом запустите блок снова."
)


def probe(url: str = URL, timeout_s: float = 2) -> str:
    """"absent" — никто не отвечает; "loading" — отвечает, но /health не 200; "ready"."""
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout_s) as response:
            return "ready" if response.status == 200 else "loading"
    except urllib.error.HTTPError:
        return "loading"
    except (OSError, ValueError):
        return "absent"
