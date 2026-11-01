import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

from app.build import COMPILE_TIMEOUT_S, CompileError, CompileTimeout, MINIMAL_ENV, build_c
from app.measure import ab_result, verdict, median
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

SUPPORTED_LANGS = {"c", "python"}
SUPPORTED_KINDS = {"ab", "sweep"}


def load_meta(harness_dir: str) -> tuple[Path, dict]:
    path = Path(harness_dir)
    if not path.is_absolute() and not path.exists():
        path = CONTENT_ROOT / harness_dir
    meta = yaml.safe_load((path / "meta.yml").read_text(encoding="utf-8"))
    return path, meta


def _prepare_python(work: Path, harness: Path, units: dict[str, str], meta: dict) -> tuple[list[str], dict]:
    """Готовит запуск Python-харнесса: студенческий и baseline-модули + bench.py.

    Возвращает команду и окружение процесса. Окружение явное и минимальное
    (как MINIMAL_ENV для C) — ни в коем случае не наследует окружение
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
        "OMP_NUM_THREADS": "1",
    }
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
    timeout_s = float(job.get("timeout_s", meta.get("timeout_s", 30)))
    repeats = int(meta.get("repeats", 11))
    sizes = meta.get("sizes", [1024])
    defines = {
        "BENCH_WARMUP": meta.get("warmup", 3),
        "BENCH_REPEATS": repeats,
        "BENCH_SIZES": "{" + ",".join(str(s) for s in sizes) + "}",
        "BENCH_NSIZES": len(sizes),
    }

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK_ROOT) as tmp:
        work = Path(tmp)
        if lang == "python":
            # No compilation stage for Python: a syntax error in the
            # student's module surfaces at import time as a non-zero exit
            # from bench.py, handled below as runtime_error — with
            # SyntaxError's own message already naming the line.
            command, env = _prepare_python(work, harness, job["units"], meta)
            compile_command = None
        else:
            try:
                build = build_c(work, harness, job["units"], meta.get("cflags", ["-O3"]), defines, unit_cflags=meta.get("unit_cflags"))
            except CompileTimeout as exc:
                return {
                    "status": "compile_timeout",
                    "message": f"Компиляция не уложилась в {COMPILE_TIMEOUT_S:.0f} с",
                    "log": exc.log[-4000:],
                }
            except CompileError as exc:
                # A line number only means something to the student if the
                # failing unit was their own submission ("b" by job-format
                # convention) — a baseline or harness/link failure must not
                # leak a line into the student's editor (Task 10 highlights it).
                is_student_unit = exc.unit == job.get("edited_unit", "b")
                return {
                    "status": "compile_error",
                    "message": "Код не скомпилировался",
                    "log": exc.log[-4000:],
                    "line": exc.line if is_student_unit else None,
                }
            command, env = [str(build.binary)], MINIMAL_ENV
            compile_command = build.compile_command

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

        if kind == "sweep":
            payload, error = _parse_sweep_output(proc.stdout, len(sizes))
        else:
            payload, error = _parse_output(proc.stdout, repeats, tuple(job["units"]))
        if error is not None:
            return {
                "status": "output_error",
                "message": "Бенчмарк не вернул корректных результатов",
                "log": (error + "\n" + proc.stderr[-4000:]).strip(),
            }

    if kind == "sweep":
        # A sweep measures one implementation across sizes, it never compares
        # two — no baseline, no speedup, no verdict, no correctness check.
        # Emitting any A/B field here (even a meaningless one) risks being
        # read downstream as a real comparison result.
        return {
            "status": "ok",
            "compile_command": compile_command,
            "series": payload["series"],
        }

    stats = ab_result(payload["samples"], payload["check"], float(meta.get("tolerance", 1e-9)))
    if math.isinf(stats["speedup"]):
        stats["speedup"] = MAX_SPEEDUP
    result = {
        "status": "ok",
        "compile_command": compile_command,
        "stdout": "",
        "stderr": proc.stderr[-4000:],
        **stats,
    }
    result["variant_ms"] = [median([sample[key] for sample in payload["samples"]]) for key in job["units"]]
    for key in list(job["units"])[2:]:
        extra = ab_result(
            [{"a": sample["a"], "b": sample[key]} for sample in payload["samples"]],
            {"a": payload["check"]["a"], "b": payload["check"][key]},
            float(meta.get("tolerance", 1e-9)),
        )
        result["correct"] = result["correct"] and extra["correct"]
    if job["mode"] == "exercise":
        result["passed"] = verdict(stats["speedup"], stats["correct"], job["target"])
    return result


def _parse_output(stdout: str, expected_repeats: int, keys: tuple = ("a", "b")) -> tuple[dict | None, str | None]:
    """Разбирает последнюю строку вывода бинарника как JSON с samples/check.

    Возвращает (payload, None) при успехе или (None, сообщение) при пустом,
    отсутствующем или неполном выводе — вызывающий код обязан не звать
    measure.ab_result на пустых samples, иначе statistics.median([]) упадёт
    с StatisticsError. Также проверяет, что число замеров совпадает с
    meta["repeats"] и что в каждом замере есть пара a/b — это фиксирует
    инвариант протокола (warmup отброшен, A/B парные), который иначе никак
    не проверяется и легко сломать при копировании bench.c под новый харнесс.
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


def _parse_sweep_output(stdout: str, expected_points: int) -> tuple[dict | None, str | None]:
    """Разбирает последнюю строку вывода бинарника как JSON с series для sweep.

    Отдельная функция от _parse_output, а не общая с ослабленной проверкой:
    у sweep нет пары a/b и нет check (это не сравнение двух реализаций), но
    свой инвариант всё равно нужно закрепить тестом, а не только доверием к
    bench.c — иначе кривая задержки кэша молча потеряет точку или получит
    мусор вместо числа, а это главный график всего курса. Проверяется: непустой
    разбираемый JSON, наличие непустого series, ровно столько точек, сколько
    было запрошено sizes, и обязательные size/ms_per_element в каждой точке.
    """
    lines = stdout.strip().splitlines()
    if not lines:
        return None, "пустой вывод бенчмарка"
    try:
        payload = json.loads(lines[-1])
        series = payload["series"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, f"не удалось разобрать JSON бенчмарка: {exc}"
    if not series:
        return None, "бенчмарк не вернул ни одной точки series"
    if len(series) != expected_points:
        return None, f"бенчмарк вернул {len(series)} точек series вместо {expected_points}"
    for point in series:
        if not isinstance(point, dict) or "size" not in point or "ms_per_element" not in point:
            return None, "точка series не содержит size и ms_per_element"
    return payload, None
