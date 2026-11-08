"""Проверка учебного материала: каждое задание и каждый бенчмарк реально гоняются.

Это performance-тесты: они медленные и шумные, поэтому помечены маркером
`content` и исключены из обычного прогона (см. web/pytest.ini). Запуск —
`make verify-content`, на целевой машине, вместе с поднятым runner'ом.
"""

import os
from pathlib import Path

import httpx
import pytest

from app.content import list_sections
from app.jobs import build_job
from app.render import render_section

RUNNER_URL = os.environ.get("RUNNER_URL", "http://runner:8000")
CONTENT_ROOT = Path(os.environ.get("CONTENT_ROOT", "/app/content"))

# Не меньше main.RUN_TIMEOUT_S: тест обязан дождаться того же, чего дождался бы
# браузер студента, иначе он падает раньше, чем runner вернёт свой вердикт.
REQUEST_TIMEOUT_S = 300


def blocks_of_kind(kind: str):
    for section in list_sections(CONTENT_ROOT):
        _, blocks = render_section(section)
        for block in blocks:
            if block.kind == kind:
                yield pytest.param(section, block, id=f"{section.id}/{block.id}")


EXERCISES = list(blocks_of_kind("exercise"))
BENCHMARKS = list(blocks_of_kind("benchmark"))


def execute(section, block, code):
    job = build_job(section, block, block.params.get("starter_code", code) if block.kind == "benchmark" else code)
    response = httpx.post(f"{RUNNER_URL}/run", json=job, timeout=REQUEST_TIMEOUT_S)
    assert response.status_code == 200, response.text
    return response.json()


def find_block(section_id, block_id):
    for section in list_sections(CONTENT_ROOT):
        if section.id != section_id:
            continue
        _, blocks = render_section(section)
        for block in blocks:
            if block.id == block_id:
                return section, block
    raise LookupError(f"нет блока {block_id!r} в разделе {section_id!r}")


def execute_exercise(section_id, block_id, code):
    """Запускает задание с произвольным кодом студента (юнит b)."""
    section, block = find_block(section_id, block_id)
    assert block.kind == "exercise", block.kind
    return execute(section, block, code)


def read_snippet(name, section_dir="20-python-runtime"):
    return (CONTENT_ROOT / section_dir / "snippets" / name).read_text(encoding="utf-8")


def skip_if_not_enough_cores(result):
    """Задание на параллелизм на машине с малым числом ядер не проверяется.

    Харнесс сам сообщает об этом (exit 3, «задание требует ≥ N»): это не
    поломка материала, а неподходящая машина.
    """
    if result.get("status") == "runtime_error" and "задание требует ≥ 4" in result.get("log", ""):
        pytest.skip(result["log"].strip())


@pytest.mark.content
@pytest.mark.parametrize("section,block", EXERCISES)
def test_reference_solution_reaches_target(section, block):
    """Ловит протухший харнесс и завышенный порог."""
    reference = (section.dir / block.params["reference"]).read_text(encoding="utf-8")

    result = execute(section, block, reference)
    skip_if_not_enough_cores(result)

    assert result["status"] == "ok", result
    assert result["correct"] is True, result
    assert result["passed"] is True, (
        f"Эталон не берёт порог «{block.params['target']}»: "
        f"получилось {result['speedup']:.2f}x при разбросе {result['spread_pct']:.1f} %, "
        f"метрики {result.get('metrics')}"
    )


@pytest.mark.content
@pytest.mark.parametrize("section,block", EXERCISES)
def test_starter_code_does_not_reach_target(section, block):
    """Ловит задание, которое решается само собой и ничему не учит."""
    result = execute(section, block, block.params["starter_code"])
    skip_if_not_enough_cores(result)

    assert result["status"] == "ok", result
    assert result["passed"] is False, (
        f"Стартовый код уже проходит порог «{block.params['target']}» "
        f"({result['speedup']:.2f}x, метрики {result.get('metrics')}) — задание ничему не учит"
    )


@pytest.mark.content
@pytest.mark.parametrize("section,block", BENCHMARKS)
def test_benchmark_block_runs(section, block):
    """Бенчмарки в тексте тоже исполняются, а не только задания.

    Без этого их код запускался бы только по нажатию кнопки в браузере, и
    сломанный харнесс обнаружился бы студентом, а не тестом. Замер —
    series-харнесс: набор линий, у каждой непустой список точек.
    """
    result = execute(section, block, "")

    assert result["status"] == "ok", result
    assert result["lines"], result
    assert all(line["points"] for line in result["lines"]), result


# ── Раздел «Python как рантайм сервиса», задание 1 (copy-on-write) ──────


@pytest.mark.content
def test_cow_gc_freeze_alone_does_not_pass():
    """gc.freeze не останавливает инкременты refcount — порог он не берёт."""
    result = execute_exercise("python-runtime", "cow-exercise", read_snippet("cow_freeze.py"))
    assert result["status"] == "ok", result
    assert result["correct"] is True, result
    assert result["passed"] is False, result


@pytest.mark.content
def test_cow_worker_exception_is_reported():
    code = read_snippet("cow_starter.py").replace("return data[key]", "raise RuntimeError('boom')")
    result = execute_exercise("python-runtime", "cow-exercise", code)
    assert result["status"] == "runtime_error" and "boom" in result["log"], result


@pytest.mark.content
def test_cow_misaligned_scores_are_incorrect():
    """Отсортировали хэши и id, а score забыли: контрольная сумма это ловит."""
    reference = read_snippet("cow_ref.py")
    code = reference.replace(
        "hashes, ids, scores = hashes[order], ids[order], scores[order]",
        "hashes, ids = hashes[order], ids[order]",
    )
    assert code != reference
    result = execute_exercise("python-runtime", "cow-exercise", code)
    assert result["status"] == "ok", result
    assert result["correct"] is False, result
    assert result["passed"] is False, result


@pytest.mark.content
def test_cow_lookup_from_key_formula_is_incorrect():
    """Записи — псевдослучайные: вычислить их из ключа, не храня данных, нельзя."""
    code = (
        "def build_data(records):\n"
        "    return bytearray(32 << 20)  # только чтобы RSS родителя вырос\n\n\n"
        "def prepare(data):\n"
        "    pass\n\n\n"
        "def lookup(data, key):\n"
        "    i = int(key[3:])\n"
        "    return i, -(i % 5000) / 100.0\n"
    )
    result = execute_exercise("python-runtime", "cow-exercise", code)
    assert result["status"] == "ok", result
    assert result["correct"] is False, result
    assert result["passed"] is False, result


# ── Раздел «Python как рантайм сервиса», подглава 4 (event loop) ─────────


@pytest.mark.content
def test_loop_lag_to_thread_unblocks_loop():
    """Синхронная модель останавливает цикл на весь инференс, to_thread — нет."""
    section, block = find_block("python-runtime", "loop-lag")
    code = read_snippet("loop_lag.py").replace("return model(x)", "return await asyncio.to_thread(model, x)")
    response = httpx.post(f"{RUNNER_URL}/run", json=build_job(section, block, code), timeout=REQUEST_TIMEOUT_S)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ok", result
    max_lag = {line["name"]: max(point["y"] for point in line["points"]) for line in result["lines"]}
    assert max_lag["blocking"] > 20, max_lag
    assert max_lag["ваш handle"] < 10, max_lag


# ── Раздел «Python как рантайм сервиса», задание 3 (сериализация) ───────


@pytest.mark.content
def test_decode_wrong_dtype_is_incorrect():
    code = read_snippet("decode_ref.py").replace("torch.float32", "torch.float64")
    result = execute_exercise("python-runtime", "decode-exercise", code)
    assert result["status"] == "ok" and result["correct"] is False


@pytest.mark.content
def test_decode_swapped_axes_are_incorrect():
    """Высота и ширина перепутаны: форма и сумма те же, позиции — нет."""
    reference = read_snippet("decode_ref.py")
    code = reference.replace("pixels.transpose(2, 0, 1)", "pixels.transpose(2, 1, 0)")
    assert code != reference
    result = execute_exercise("python-runtime", "decode-exercise", code)
    assert result["status"] == "ok", result
    assert result["correct"] is False, result
    assert result["passed"] is False, result


# ── Раздел «Наивный сервис и свой батчер», задание «собрать батч» ──────

# Обёртка над эталоном, которая переставляет элементы батча: модель получит
# входы в другом порядке, и ответы уйдут не тем запросам.
BATCHER_MIXUP = """

_collect = collect_batch


async def collect_batch(queue, max_batch_size, max_delay):
    batch = await _collect(queue, max_batch_size, max_delay)
    if len(batch) > 1:
        tensors = [item[0] for item in batch]
        batch = [(tensors[(k + 1) % len(batch)], item[1]) for k, item in enumerate(batch)]
    return batch
"""

BATCHER_WAIT_FOR_FULL = """
async def collect_batch(queue, max_batch_size, max_delay):
    batch = []
    while len(batch) < max_batch_size:
        batch.append(await queue.get())
    return batch
"""


@pytest.mark.content
def test_batcher_mixed_up_responses_are_incorrect():
    code = read_snippet("batcher_ref.py", "30-naive-service") + BATCHER_MIXUP
    result = execute_exercise("naive-service", "batcher-exercise", code)
    skip_if_not_enough_cores(result)
    assert result["status"] == "ok", result
    assert result["correct"] is False and result["passed"] is False, result
    assert "перепутаны" in result["stderr"], result


@pytest.mark.content
def test_batcher_waiting_for_full_batch_is_reported():
    result = execute_exercise("naive-service", "batcher-exercise", BATCHER_WAIT_FOR_FULL)
    skip_if_not_enough_cores(result)
    assert result["status"] == "runtime_error", result
    assert "max_batch_size" in result["log"], result

# Типичная ошибка: get_nowait без обработки QueueEmpty — collect_batch бросает.
BATCHER_RAISES = """
import asyncio


async def collect_batch(queue, max_batch_size, max_delay):
    batch = [await queue.get()]
    while len(batch) < max_batch_size:
        batch.append(queue.get_nowait())
    return batch
"""

# Обёртка над эталоном, которая из каждого батча длиннее одного выбрасывает
# последний запрос: забрала из очереди и не вернула.
BATCHER_DROPS = """

_collect = collect_batch


async def collect_batch(queue, max_batch_size, max_delay):
    batch = await _collect(queue, max_batch_size, max_delay)
    if len(batch) > 1:
        batch.pop()
    return batch
"""

# Busy-wait: крутится, пока очередь пуста, отдавая управление, но не засыпая.
BATCHER_BUSY_WAIT = """
import asyncio


async def collect_batch(queue, max_batch_size, max_delay):
    while queue.empty():
        await asyncio.sleep(0)
    batch = [queue.get_nowait()]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_delay
    while len(batch) < max_batch_size and loop.time() < deadline:
        if queue.empty():
            await asyncio.sleep(0)
        else:
            batch.append(queue.get_nowait())
    return batch
"""


@pytest.mark.content
def test_batcher_exception_is_shown_to_student():
    result = execute_exercise("naive-service", "batcher-exercise", BATCHER_RAISES)
    skip_if_not_enough_cores(result)
    assert result["status"] == "runtime_error", result
    assert "QueueEmpty" in result["log"] and "max_batch_size =" not in result["log"], result


@pytest.mark.content
def test_batcher_losing_requests_is_incorrect():
    code = read_snippet("batcher_ref.py", "30-naive-service") + BATCHER_DROPS
    result = execute_exercise("naive-service", "batcher-exercise", code)
    skip_if_not_enough_cores(result)
    assert result["status"] == "ok", result
    assert result["correct"] is False and result["passed"] is False, result
    assert "без ответа" in result["stderr"], result


@pytest.mark.content
def test_batcher_busy_wait_is_warned():
    result = execute_exercise("naive-service", "batcher-exercise", BATCHER_BUSY_WAIT)
    skip_if_not_enough_cores(result)
    assert result["status"] == "ok", result
    assert "busy-wait" in result["stderr"], result


# --- Раздел 40, задание «config.pbtxt»: типовые ошибки конфига -------------

def triton_config(**replace):
    """Эталонный конфиг задания с заменами строк: {старое: новое}."""
    text = read_snippet("config_ref.pbtxt", "40-triton")
    for old, new in replace.items():
        assert old in text, old
        text = text.replace(old, new)
    return text


@pytest.mark.content
def test_config_exercise_broken_syntax_shows_triton_error():
    code = triton_config(**{"max_batch_size: 32": "max_batch_sise: 32"})
    result = execute_exercise("triton", "config-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "max_batch_sise" in result["log"], result


@pytest.mark.content
def test_config_exercise_zero_batch_size_is_explained():
    code = triton_config(**{"max_batch_size: 32": "max_batch_size: 0"})
    result = execute_exercise("triton", "config-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "max_batch_size" in result["log"], result


@pytest.mark.content
def test_config_exercise_huge_delay_fails_rare_load():
    code = triton_config(**{"dynamic_batching {": "dynamic_batching {\n  max_queue_delay_microseconds: 2000000"})
    result = execute_exercise("triton", "config-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "редких" in result["log"], result


@pytest.mark.content
def test_config_exercise_wrong_io_names():
    code = triton_config(**{'name: "INPUT__0"': 'name: "input"'})
    result = execute_exercise("triton", "config-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "INPUT__0" in result["log"], result


# --- Раздел 40, задание «экспорт в libtorch» -------------------------------

def export_solution(**replace):
    text = read_snippet("export_ref.py", "40-triton")
    for old, new in replace.items():
        assert old in text, old
        text = text.replace(old, new)
    return text


# Типичная ошибка: модель «зашита» на батч 1 (reshape с константой при трассировке).
EXPORT_FIXED_BATCH = '''
import torch


class _FixedBatch(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x.reshape(1, 3, 64, 64))


def export(model, path):
    torch.jit.trace(_FixedBatch(model.eval()), torch.zeros(1, 3, 64, 64)).save(path)
'''


@pytest.mark.content
def test_export_fixed_batch_is_reported():
    ref = read_snippet("export_ref.py", "40-triton")
    code = ref[:ref.index("def export")] + EXPORT_FIXED_BATCH
    result = execute_exercise("triton", "export-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "батч" in result["log"] and "1" in result["log"], result


@pytest.mark.content
def test_export_wrong_io_names_are_reported():
    code = export_solution(**{'name: "INPUT__0"': 'name: "x"'})
    result = execute_exercise("triton", "export-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "INPUT__0" in result["log"], result


@pytest.mark.content
def test_export_exception_shows_traceback():
    signature = "def export(model: torch.nn.Module, path: str) -> None:\n"
    code = export_solution(**{signature: signature + "    raise ValueError('сломано')\n"})
    result = execute_exercise("triton", "export-exercise", code)
    assert result["status"] == "runtime_error", result
    assert "сломано" in result["log"], result
