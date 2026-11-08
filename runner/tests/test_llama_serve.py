"""llama.serve раздела «LLM» против настоящего llama-server (make test-llm)."""
import os
import sys

import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "50-llm", "harness", "_lib"))

import llama  # noqa: E402
import llmload  # noqa: E402
import stand  # noqa: E402

pytestmark = pytest.mark.llm


def no_llama_left() -> bool:
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                if b"llama-server" in handle.read():
                    return False
        except OSError:
            continue
    return True


def test_serve_answers_completion():
    load_cpu, service = stand.cpus()
    with llama.serve(slots=4, ctx_total=2048, cpus=service) as url:
        result = llmload.run_http(url, llama.MODEL, rps=2, duration_s=2, mix=llmload.Mix(),
                                  load_cpu=load_cpu)
    assert result.errors() == 0, result.first_error()
    assert result.truncated() == 0
    assert all(rec.n_tokens == rec.max_new for rec in result.per_request)
    assert no_llama_left()


def test_bad_args_raise_with_stderr():
    _, service = stand.cpus()
    with pytest.raises(llama.LlamaStartError) as err:
        with llama.serve(slots=4, ctx_total=2048, cpus=service, extra=["--no-such-flag"]):
            pass
    assert "no-such-flag" in str(err.value)
    assert no_llama_left()
