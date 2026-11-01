"""Проверка учебного материала: каждое задание и каждый бенчмарк реально гоняются.

Это performance-тесты: они медленные и шумные, поэтому помечены маркером
`content` и исключены из обычного прогона (см. web/pytest.ini). Запуск —
`make verify-content`, на целевой машине, вместе с поднятым runner'ом.
"""

import os
from pathlib import Path

import httpx
import pytest
import yaml

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


def harness_meta(section, block):
    path = section.dir / "harness" / block.params["harness"] / "meta.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@pytest.mark.content
@pytest.mark.parametrize("section,block", EXERCISES)
def test_reference_solution_reaches_target(section, block):
    """Ловит протухший харнесс и завышенный порог."""
    reference = (section.dir / block.params["reference"]).read_text(encoding="utf-8")

    result = execute(section, block, reference)

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

    assert result["status"] == "ok", result
    assert result["passed"] is False, (
        f"Стартовый код уже проходит порог «{block.params['target']}» "
        f"({result['speedup']:.2f}x, метрики {result.get('metrics')}) — задание ничему не учит"
    )


@pytest.mark.content
@pytest.mark.parametrize("section,block", BENCHMARKS)
def test_benchmark_block_runs(section, block):
    """Бенчмарки в тексте тоже исполняются, а не только задания.

    Без этого лестница кэша, кривая префетчера и бенчмарк оси не проверялись бы
    ничем: их код компилируется и запускается только по нажатию кнопки в
    браузере, и сломанный харнесс обнаружился бы студентом, а не тестом.
    """
    result = execute(section, block, "")

    assert result["status"] == "ok", result

    if "series" in result:
        sizes = harness_meta(section, block)["sizes"]
        assert [point["size"] for point in result["series"]] == list(sizes)
        assert all(point["ms_per_element"] > 0 for point in result["series"]), result
    elif "lines" in result:
        # series-харнесс: набор линий, у каждой непустой список числовых точек.
        assert result["lines"], result
        assert all(line["points"] for line in result["lines"]), result
    else:
        # A/B-бенчмарк сравнивает два варианта одного вычисления: если их
        # ответы разошлись, сравнивать время бессмысленно — это ошибка в
        # материалах, а не наблюдение про память.
        assert result["correct"] is True, result
        assert result["baseline_ms"] > 0 and result["student_ms"] > 0, result


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
