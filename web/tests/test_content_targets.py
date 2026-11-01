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
        f"получилось {result['speedup']:.2f}x при разбросе {result['spread_pct']:.1f} %"
    )


@pytest.mark.content
@pytest.mark.parametrize("section,block", EXERCISES)
def test_starter_code_does_not_reach_target(section, block):
    """Ловит задание, которое решается само собой и ничему не учит."""
    result = execute(section, block, block.params["starter_code"])

    assert result["status"] == "ok", result
    assert result["passed"] is False, (
        f"Стартовый код уже проходит порог «{block.params['target']}» "
        f"({result['speedup']:.2f}x) — задание ничему не учит"
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
    else:
        # A/B-бенчмарк сравнивает два варианта одного вычисления: если их
        # ответы разошлись, сравнивать время бессмысленно — это ошибка в
        # материалах, а не наблюдение про память.
        assert result["correct"] is True, result
        assert result["baseline_ms"] > 0 and result["student_ms"] > 0, result
