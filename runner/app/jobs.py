import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

from app.measure import ab_result, verdict
from app.sandbox import run

CONTENT_ROOT = Path(os.environ.get("CONTENT_ROOT", "/content"))
WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/work"))
MEMORY_MB = int(os.environ.get("BENCH_MEMORY_MB", "2048"))

# JSON has no literal for infinity; measure.ab_result returns float("inf")
# when the student's median is 0.0 (timer granularity on a near-instant,
# usually-wrong answer). json.dumps would emit a bare `Infinity` token that
# browsers' JSON.parse rejects, breaking the response for exactly the
# "wrong but fast" case. Clamp instead of propagating it.
MAX_SPEEDUP = 1_000_000.0

SUPPORTED_LANGS = {"python"}
SUPPORTED_KINDS = {"ab", "series"}


def load_meta(harness_dir: str) -> tuple[Path, dict]:
    path = Path(harness_dir)
    if not path.is_absolute() and not path.exists():
        path = CONTENT_ROOT / harness_dir
    meta = yaml.safe_load((path / "meta.yml").read_text(encoding="utf-8"))
    return path, meta


def _prepare_python(work: Path, harness: Path, units: dict[str, str], meta: dict) -> tuple[list[str], dict]:
    """Готовит запуск Python-харнесса: студенческий и baseline-модули + bench.py.

    Возвращает команду и окружение процесса. Окружение явное и минимальное
    — ни в коем случае не наследует окружение
    сервиса runner. OMP_NUM_THREADS=1 обязателен: NumPy на OpenBLAS иначе
    незаметно уходит в многопоточность, и урок про память подменяется
    уроком про число потоков с нестабильными числами от прогона к прогону.
    """
    for name, source in units.items():
        (work / f"unit_{name}.py").write_text(source, encoding="utf-8")
    shutil.copy(harness / "bench.py", work / "bench.py")
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONPATH": str(work),
        "BENCH_WARMUP": str(meta.get("warmup", 3)),
        "BENCH_REPEATS": str(meta.get("repeats", 11)),
        "BENCH_SIZES": ",".join(str(s) for s in meta.get("sizes", [1024])),
    }
    # threads: 1 (по умолчанию) закрепляет OMP_NUM_THREADS; "auto" оставляет
    # переменную незаданной, и библиотека сама выбирает число потоков.
    if meta.get("threads", 1) != "auto":
        env["OMP_NUM_THREADS"] = "1"
    lib = harness.parent / "_lib"
    if lib.is_dir():
        for path in lib.glob("*.py"):
            shutil.copy(path, work / path.name)
    return [sys.executable, "bench.py"], env


def run_job(job: dict) -> dict:
    lang = job.get("lang")
    if lang not in SUPPORTED_LANGS:
        return {
            "status": "unsupported_lang",
            "message": f"Язык {lang!r} пока не поддерживается",
        }

    harness, meta = load_meta(job["harness_dir"])
    kind = str(meta.get("kind", "ab"))
    if kind not in SUPPORTED_KINDS:
        return {
            "status": "unsupported_kind",
            "message": f"Тип харнесса {kind!r} пока не поддерживается",
        }
    threads = meta.get("threads", 1)
    if threads not in (1, "auto") or isinstance(threads, bool):
        return {
            "status": "harness_error",
            "message": f"Некорректное значение threads в meta.yml харнесса: {threads!r} (допустимо 1 или \"auto\")",
        }
    timeout_s = float(job.get("timeout_s", meta.get("timeout_s", 30)))
    repeats = int(meta.get("repeats", 11))

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK_ROOT) as tmp:
        work = Path(tmp)
        # Синтаксическая ошибка в модуле студента всплывает при импорте как
        # ненулевой код выхода bench.py и обрабатывается ниже как
        # runtime_error — с сообщением SyntaxError, где уже есть номер строки.
        command, env = _prepare_python(work, harness, job["units"], meta)

        proc = run(command, work, timeout_s=timeout_s, memory_mb=min(MEMORY_MB, int(meta.get("memory_mb", MEMORY_MB))), env=env)
        if proc.timed_out:
            return {
                "status": "timeout",
                "message": f"Код не уложился в {timeout_s:.0f} с — похоже на бесконечный цикл",
            }
        if proc.returncode != 0:
            return {
                "status": "runtime_error",
                "message": f"Программа завершилась с кодом {proc.returncode}",
                "log": proc.stderr[-4000:],
            }

        if kind == "series":
            payload, error = _parse_lines_output(proc.stdout)
        else:
            payload, error = _parse_output(proc.stdout, repeats, tuple(job["units"]))
            if error is None:
                error = _check_metrics(payload.get("metrics"))
        if error is not None:
            return {
                "status": "output_error",
                "message": "Бенчмарк не вернул корректных результатов",
                "log": (error + "\n" + proc.stderr[-4000:]).strip(),
            }

    if kind == "series":
        # series не сравнивает две реализации: только линии.
        return {
            "status": "ok",
            "lines": payload["lines"],
        }

    stats = ab_result(payload["samples"], payload["check"], float(meta.get("tolerance", 1e-9)))
    if math.isinf(stats["speedup"]):
        stats["speedup"] = MAX_SPEEDUP
    result = {
        "status": "ok",
        "stdout": "",
        "stderr": proc.stderr[-4000:],
        **stats,
    }
    harness_metrics = payload.get("metrics")
    if harness_metrics is not None:
        result["baseline_metrics"] = harness_metrics.get("a", {})
        result["metrics"] = harness_metrics.get("b", {})
    if job["mode"] == "exercise":
        values = {"speedup": stats["speedup"], **result.get("metrics", {})}
        try:
            result["passed"] = verdict(values, stats["correct"], job["target"])
        except KeyError as exc:
            return {
                "status": "output_error",
                "message": f"Харнесс не вернул метрику {exc.args[0]!r} из цели задания",
            }
    return result


def _parse_output(stdout: str, expected_repeats: int, keys: tuple = ("a", "b")) -> tuple[dict | None, str | None]:
    """Разбирает последнюю строку вывода бинарника как JSON с samples/check.

    Возвращает (payload, None) при успехе или (None, сообщение) при пустом,
    отсутствующем или неполном выводе — вызывающий код обязан не звать
    measure.ab_result на пустых samples, иначе statistics.median([]) упадёт
    с StatisticsError. Также проверяет, что число замеров совпадает с
    meta["repeats"] и что в каждом замере есть пара a/b — это фиксирует
    инвариант протокола (warmup отброшен, A/B парные), который иначе никак
    не проверяется и легко сломать при копировании bench.py под новый харнесс.
    """
    lines = stdout.strip().splitlines()
    if not lines:
        return None, "пустой вывод бенчмарка"
    try:
        payload = json.loads(lines[-1])
        samples = payload["samples"]
        for key in keys:
            payload["check"][key]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, f"не удалось разобрать JSON бенчмарка: {exc}"
    if not samples:
        return None, "бенчмарк не сделал ни одного замера"
    if len(samples) != expected_repeats:
        return None, f"бенчмарк вернул {len(samples)} замеров вместо {expected_repeats}"
    for sample in samples:
        if not isinstance(sample, dict) or any(key not in sample for key in keys):
            return None, "замер бенчмарка не содержит пару a/b"
    return payload, None


def _check_metrics(metrics) -> str | None:
    """Необязательное поле metrics: {"a": {имя: число}, "b": {имя: число}}."""
    if metrics is None:
        return None
    if not isinstance(metrics, dict):
        return "metrics должен быть объектом {a: {...}, b: {...}}"
    for unit, named in metrics.items():
        if not isinstance(named, dict):
            return f"metrics[{unit!r}] должен быть объектом имя -> число"
        for name, value in named.items():
            if name == "speedup":
                # Имя занято измеренным ускорением: метрика харнесса с тем же
                # именем подменила бы его в вердикте.
                return f"metrics[{unit!r}]: имя 'speedup' зарезервировано за измеренным ускорением"
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return f"metrics[{unit!r}][{name!r}] должно быть конечным числом"
    return None


def _is_number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _parse_lines_output(stdout: str) -> tuple[dict | None, str | None]:
    """Разбирает последнюю строку вывода как JSON с lines для kind: series.

    Проверяется: непустой lines, у каждой линии строка name и непустой points,
    у каждой точки конечные числовые x и y (JSON-булевы значения не числа).
    """
    lines = stdout.strip().splitlines()
    if not lines:
        return None, "пустой вывод бенчмарка"
    try:
        payload = json.loads(lines[-1])
        chart_lines = payload["lines"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, f"не удалось разобрать JSON бенчмарка: {exc}"
    if not isinstance(chart_lines, list) or not chart_lines:
        return None, "бенчмарк не вернул ни одной линии lines"
    for line in chart_lines:
        if not isinstance(line, dict) or not isinstance(line.get("name"), str):
            return None, "линия lines не содержит строку name"
        points = line.get("points")
        if not isinstance(points, list) or not points:
            return None, f"линия {line['name']!r} не содержит точек"
        for point in points:
            if not isinstance(point, dict) or not _is_number(point.get("x")) or not _is_number(point.get("y")):
                return None, f"точка линии {line['name']!r} не содержит числовых x и y"
    return payload, None
