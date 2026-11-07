import re
from pathlib import Path

from app.content import Block, ContentError, Section

# Цель задания разбирается один раз здесь. Метрики не перечисляются: любая
# \w+ годится, а есть ли она у харнесса, проверяет runner (нет метрики —
# output_error с понятным сообщением, а не 500). Операция по-прежнему
# ограничена: опечатка вроде `=>` ловится здесь как ContentError, а не
# превращается в ValueError в runner'е.
TARGET_OPS = (">=", ">", "<=", "<")

TARGET = re.compile(r"^\s*(?P<metric>\w+)\s*(?P<op>[<>=!]+)\s*(?P<value>\d+(?:\.\d+)?)\s*$")


def parse_target(text: str) -> dict:
    """Разбирает `speedup >= 3` в {"metric": ..., "op": ..., "value": 3.0}."""
    match = TARGET.match(text)
    if not match:
        raise ContentError(
            f"Не разобралась цель задания: {text!r}. Ожидается вид 'speedup >= 3'"
        )
    metric, op = match.group("metric"), match.group("op")
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


def build_job(section: Section, block: Block, code: str) -> dict:
    """Собирает job для runner'а из блока раздела и кода студента.

    Ключи job'а — контракт с runner.jobs.run_job: `harness_dir` обязателен
    (его отсутствие там KeyError), `mode` читается всегда, `target` — только
    при mode == "exercise".
    """
    if block.kind not in ("exercise", "benchmark"):
        raise ContentError(f"Блок {block.kind} {block.id} не запускается")

    harness = block.params.get("harness")
    if not harness:
        raise ContentError(f"Блок {block.id} без харнесса — нечего запускать")

    job = {
        "mode": block.kind,
        "lang": block.lang,
        # Имя папки, а не section.id: папка несёт префикс порядка (20-python-runtime),
        # и именно от него runner резолвит путь внутри своего CONTENT_ROOT.
        # Путь относительный, потому что контент смонтирован в двух сервисах
        # по разным абсолютным путям (/app/content и /content).
        "harness_dir": f"{section.dir.name}/harness/{harness}",
    }

    if block.kind == "exercise":
        # baseline ("a") — стартовый код: ускорение считается относительно
        # того, с чего студент начал, а не относительно эталона (эталон в
        # браузер не попадает вовсе).
        job["units"] = {"a": block.params["starter_code"], "b": code}
        job["target"] = parse_target(str(block.params["target"]))
        return job

    # Замер — series-харнесс: исходник замера юнитом "a", правка студента
    # (если блок редактируемый) — юнитом "b".
    job["units"] = {"a": _read_unit(section, block.params["source"])}
    for path in block.params.get("extra", []):
        job["units"][Path(str(path)).stem] = _read_unit(section, str(path))
    if "starter_code" in block.params:
        job["units"]["b"] = code
    job["target"] = None
    return job
