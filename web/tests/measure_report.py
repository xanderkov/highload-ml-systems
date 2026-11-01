"""Служебный прогон: печатает измеренные числа по каждому блоку курса.

Не тест. Запуск: docker compose run --rm web python -m tests.measure_report
"""

import sys

from tests.test_content_targets import BENCHMARKS, EXERCISES, execute


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    for param in EXERCISES:
        section, block = param.values
        if only and only not in block.id:
            continue
        reference = (section.dir / block.params["reference"]).read_text(encoding="utf-8")
        ref = execute(section, block, reference)
        starter = execute(section, block, block.params["starter_code"])
        print(
            f"exercise {block.id}: target={block.params['target']!r} "
            f"reference={ref.get('speedup', float('nan')):.2f}x "
            f"correct={ref.get('correct')} passed={ref.get('passed')} "
            f"baseline={ref.get('baseline_ms', 0):.1f}ms student={ref.get('student_ms', 0):.1f}ms "
            f"spread={ref.get('spread_pct', 0):.1f}% | "
            f"starter={starter.get('speedup', float('nan')):.2f}x passed={starter.get('passed')}",
            flush=True,
        )
        if ref.get("status") != "ok":
            print(f"  !! {ref}", flush=True)

    for param in BENCHMARKS:
        section, block = param.values
        if only and only not in block.id:
            continue
        result = execute(section, block, "")
        if result.get("status") != "ok":
            print(f"benchmark {block.id}: !! {result}", flush=True)
        elif "series" in result:
            points = " ".join(
                f"{p['size']}:{p['ms_per_element'] * 1e6:.2f}ns" for p in result["series"]
            )
            print(f"benchmark {block.id} (sweep): {points}", flush=True)
        else:
            print(
                f"benchmark {block.id}: a={result['baseline_ms']:.1f}ms "
                f"b={result['student_ms']:.1f}ms ratio={result['speedup']:.2f}x "
                f"correct={result['correct']} spread={result['spread_pct']:.1f}%",
                flush=True,
            )


if __name__ == "__main__":
    main()
