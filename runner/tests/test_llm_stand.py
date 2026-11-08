"""stand раздела «LLM»: известные сбои замера — сообщением, без трассировки."""
import os
import sys

import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "50-llm", "harness", "_lib"))

import llama  # noqa: E402
import llmload  # noqa: E402
import stand  # noqa: E402


@pytest.mark.parametrize("exc,hint", [
    (llmload.LoadGeneratorLagging("отстал на 80 мс"), "отстал на 80 мс"),
    (TimeoutError(), "не дождались"),
    (llama.LlamaStartError("llama-server завершился с кодом 1"), "завершился с кодом 1"),
])
def test_known_failures_become_messages(tmp_path, capsys, exc, hint):
    with pytest.raises(SystemExit) as stop:
        with stand.exclusive(path=str(tmp_path / "lock")):
            raise exc
    assert stop.value.code == 1
    err = capsys.readouterr().err
    assert hint in err and "Traceback" not in err
