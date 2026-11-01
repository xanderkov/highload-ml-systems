import re

from app.content import Block, ContentError, Section
from app.experiments import prepare_units

# Цель задания разбирается один раз здесь, а не в runner'е. Ограничения жёсткие
# по одной причине: measure.verdict в runner'е бросает ValueError на любой
# метрике кроме speedup и любой операции кроме >= и >, и этот ValueError уже
# никто не ловит — POST /run отвечает 500, а студент видит «сервис сломался»
# вместо честного сообщения об опечатке в материалах. Ловим опечатку здесь,
# на разборе контента, где из неё получается ContentError с текстом причины.
TARGET_METRICS = ("speedup",)
TARGET_OPS = (">=", ">")

TARGET = re.compile(r"^\s*(?P<metric>\w+)\s*(?P<op>[<>=!]+)\s*(?P<value>\d+(?:\.\d+)?)\s*$")


def parse_target(text: str) -> dict:
    """Разбирает `speedup >= 3` в {"metric": ..., "op": ..., "value": 3.0}."""
    match = TARGET.match(text)
    if not match:
        raise ContentError(
            f"Не разобралась цель задания: {text!r}. Ожидается вид 'speedup >= 3'"
        )
    metric, op = match.group("metric"), match.group("op")
    if metric not in TARGET_METRICS:
        raise ContentError(
            f"Неизвестная метрика цели {metric!r} в цели {text!r}. "
            f"Поддерживается только: {', '.join(TARGET_METRICS)}"
        )
    if op not in TARGET_OPS:
        raise ContentError(
            f"Неизвестная операция сравнения {op!r} в цели {text!r}. "
            f"Поддерживаются только: {', '.join(TARGET_OPS)}"
        )
    return {"metric": metric, "op": op, "value": float(match.group("value"))}


def _read_unit(section: Section, relative: str) -> str:
    path = section.dir / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContentError(f"{path}: не удалось прочитать код варианта: {exc}") from exc


def build_job(section: Section, block: Block, code: str, variant: int | None = None) -> dict:
    """Собирает job для runner'а из блока раздела и кода студента.

    Ключи job'а — контракт с runner.jobs.run_job: `harness_dir` обязателен
    (его отсутствие там KeyError), `mode` читается всегда, `target` — только
    при mode == "exercise".
    """
    if block.kind not in ("exercise", "benchmark", "experiment"):
        raise ContentError(f"Блок {block.kind} {block.id} не запускается")

    harness = block.params.get("harness")
    if not harness:
        raise ContentError(f"Блок {block.id} без харнесса — нечего запускать")

    job = {
        "mode": block.kind,
        "lang": block.lang,
        # Имя папки, а не section.id: папка несёт префикс порядка (01-cpu-cache),
        # и именно от него runner резолвит путь внутри своего CONTENT_ROOT.
        # Путь относительный, потому что контент смонтирован в двух сервисах
        # по разным абсолютным путям (/app/content и /content).
        "harness_dir": f"{section.dir.name}/harness/{harness}",
    }

    if block.kind == "experiment":
        job["mode"] = "benchmark"
        job["units"], job["gap_bytes"] = prepare_units(block.params["starter_code"], code)
        job["target"] = None
        return job

    if block.kind == "exercise":
        # baseline ("a") — стартовый код: ускорение считается относительно
        # того, с чего студент начал, а не относительно эталона (эталон в
        # браузер не попадает вовсе).
        job["units"] = {"a": block.params["starter_code"], "b": code}
        job["target"] = parse_target(str(block.params["target"]))
        return job

    if "source" in block.params:
        # sweep-харнесс: одна реализация на многих размерах, второго юнита нет
        job["units"] = {"a": _read_unit(section, block.params["source"])}
    else:
        names = block.params["variant_sources"]
        job["units"] = {
            key: _read_unit(section, f"snippets/{name}") for key, name in zip("abc", names)
        }
    if block.params.get("parallel_editors") and variant is not None:
        job["units"]["abc"[variant]] = code
        job["edited_unit"] = "abc"[variant]
    elif "starter_code" in block.params:
        job["units"]["b"] = code
    job["target"] = None
    return job
