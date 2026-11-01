# Раздел «Python как рантайм сервиса»: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в курс коллеги раздел `content/20-python-runtime/` с тремя заданиями и доработать runner/web: torch, лимиты, произвольные метрики в целях, графики-линии.

**Architecture:** Код курса коллеги импортируется в этот репозиторий как есть, затем дорабатывается. Runner получает поля `meta.yml` (`memory_limit`, `threads`), обобщённый вердикт по метрикам и новый `kind: series`. Web принимает цели вида `<метрика> <op> <число>` и рисует линии. Раздел целиком на Python-harness'ах того же формата, что `content/01-cpu-cache/harness/*/bench.py`.

**Tech Stack:** Python 3.12, FastAPI, pytest, Docker Compose, torch (CPU), NumPy, uPlot, vanilla JS-модули.

**Spec:** `docs/superpowers/specs/2026-11-01-python-runtime-section-design.md`

## Global Constraints

- Контент на русском; код и идентификаторы на английском.
- Поведение раздела `01-cpu-cache` не меняется: его тесты (`make test`) зелёные после каждой задачи.
- Значения по умолчанию новых полей сохраняют старое поведение: `memory_limit: as`, `threads: 1`.
- Модели создаются в коде harness'а со случайными весами; runner без интернета; torchvision не добавляется.
- torch только CPU: x86 из `https://download.pytorch.org/whl/cpu`, arm64 из PyPI.
- Протокол замера прежний: прогрев отбрасывается, медиана, A/B чередуются, baseline — стартовый код.
- Пороги: задание 1 `pss_growth_ratio <= 0.3`, задание 2 `speedup >= 1.5`, задание 3 `speedup >= 5` (калибруются в задаче 11).
- Задание 2 требует ≥ 4 ядер; при меньшем числе понятное сообщение, а не проваленный вердикт.
- Все тесты запускаются в контейнерах: `make test-runner`, `make test-web`, `make verify-content`, `make smoke`.

## Review Focus

1. **Машина с < 4 ядрами, задание 2**: harness завершается с сообщением «на машине N ядер, задание требует ≥ 4», `verify-content` пропускает задание, а не падает. Тест в задаче 9.
2. **Код студента падает или зависает внутри fork-воркера (задание 1)**: harness не ждёт таймаута молча, а завершается с ненулевым кодом и текстом исключения воркера, и runner возвращает `runtime_error`. Тест в задаче 7.
3. **Цель ссылается на метрику, которую harness не вернул**: `output_error` с именем метрики, а не 500. Тест в задаче 3.
4. **Задание 3, решение возвращает тензор не того dtype/формы или read-only массив, который torch молча копирует**: `correct: false` для неверного dtype/формы. Тест в задаче 10.
5. **`import torch` под лимитами sandbox**: работает при выбранном в задаче 1 режиме, а не падает с `MemoryError`/`OSError` в первом же эксперименте. Тест в задаче 1.

---

### Task 0: Импорт курса коллеги

**Files:**
- Create: всё содержимое `~/Downloads/cpu-course/` в корне репозитория (кроме `.runtime/`, `__pycache__/`, `.pytest_cache/`)

- [ ] **Step 1: Скопировать без перезаписи `docs/superpowers/specs/2026-11-01-*`**

Run: `rsync -a --exclude .runtime --exclude __pycache__ --exclude .pytest_cache ~/Downloads/cpu-course/ ./`

- [ ] **Step 2: Добавить `.gitignore`** с `.runtime/`, `__pycache__/`, `.pytest_cache/`, `.env`.

- [ ] **Step 3: Проверить, что исходный курс зелёный**

Run: `make test`
Expected: все тесты PASS. Если нет, остановиться и сообщить: дальнейшие задачи опираются на зелёную базу.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: import cpu-course as-is"
```

### Task 1: Спайк torch + лимит памяти

**Files:**
- Modify: `runner/requirements.txt`, `runner/Dockerfile`
- Modify: `docker-compose.yml` (сервис `runner`: `mem_limit: 3g`)
- Create: `runner/tests/fixtures/harness/torch_import/{meta.yml,bench.py}`
- Test: `runner/tests/test_jobs_torch.py`

**Interfaces:**
- Produces: вывод спайка — одно из двух решений, записанное в `docs/superpowers/specs/...design.md` §7 п.1: (А) torch работает под `RLIMIT_AS` при `memory_mb: N` → поле `memory_limit` не вводится, задача 2 делает только `threads`; (Б) не работает → задача 2 вводит `memory_limit: as | none`.

- [ ] **Step 1: Установить torch в образ.** В `Dockerfile` отдельный `RUN` перед `requirements.txt`: на `x86_64` `pip install --index-url https://download.pytorch.org/whl/cpu torch`, иначе `pip install torch` (ветвление по `uname -m`). Версию закрепить `torch~=2.5` или актуальной на момент реализации.

- [ ] **Step 2: Спайк.** В контейнере runner: `python -c "import resource; resource.setrlimit(resource.RLIMIT_AS, (N, N)); import torch; torch.nn.Linear(512,512)(torch.randn(64,512)); print('ok')"` для N = 2, 4, 8, 16 ГиБ, с `OMP_NUM_THREADS` = 1 и без него. Записать в спеку минимальное рабочее N и вывод (А) или (Б).

- [ ] **Step 3: Тест-фикстура.** `torch_import/bench.py` импортирует torch, прогоняет `Linear(512,512)` и печатает валидный A/B JSON (`samples` из `repeats` пар, `check` = сумма выхода). Тест:

```python
def test_torch_imports_under_harness_limits():
    result = run_job(job_for("tests/fixtures/harness/torch_import"))
    assert result["status"] == "ok", result
```

`meta.yml` фикстуры использует решение спайка (`memory_mb: N` или `memory_limit: none`); при (Б) тест помечается `xfail(strict=True)` до задачи 2.

- [ ] **Step 4: Run** `make test-runner` → PASS (или ожидаемый xfail при (Б)).

- [ ] **Step 5: Commit** `feat(runner): add CPU torch; spike RLIMIT_AS`

### Task 2: Поля `meta.yml`: `threads` и (при варианте Б) `memory_limit`

**Files:**
- Modify: `runner/app/sandbox.py` (`_limits`, `run`), `runner/app/jobs.py` (`_prepare_python`, вызов `run`)
- Test: `runner/tests/test_sandbox.py`, `runner/tests/test_jobs_python.py`

**Interfaces:**
- Produces: `sandbox.run(cmd, cwd, timeout_s, memory_mb, env=None, limit_address_space: bool = True)`; `jobs._prepare_python(work, harness, units, meta)` учитывает `meta.get("threads", 1)` и копирует `harness.parent / "_lib" / "*.py"` в `work`, если папка существует.

- [ ] **Step 1: Тесты**

```python
def test_threads_auto_leaves_omp_unset(tmp_path):
    _, env = _prepare_python(tmp_path, HARNESS_PATH, {"a": "", "b": ""}, {"threads": "auto"})
    assert "OMP_NUM_THREADS" not in env

def test_threads_default_is_one(tmp_path):
    _, env = _prepare_python(tmp_path, HARNESS_PATH, {"a": "", "b": ""}, {})
    assert env["OMP_NUM_THREADS"] == "1"

def test_shared_lib_is_copied(tmp_path):  # фикстура tests/fixtures/harness/_lib/helper.py
    _prepare_python(tmp_path, HARNESS_PATH, {"a": "", "b": ""}, {})
    assert (tmp_path / "helper.py").exists()

# только при варианте Б:
def test_memory_limit_none_skips_rlimit_as():
    proc = run([sys.executable, "-c", "import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0])"],
               cwd=Path("."), timeout_s=10, memory_mb=256, limit_address_space=False)
    assert proc.stdout.strip() == str(resource.RLIM_INFINITY)
```

- [ ] **Step 2: Run** `make test-runner` → новые тесты FAIL.
- [ ] **Step 3: Реализация.** `threads`: допустимы `1` и `"auto"`, иное → ответ `status: "harness_error"` с текстом. `memory_limit`: `"as"` (по умолчанию) или `"none"`, иное → `harness_error`. При варианте Б снять `xfail` из задачи 1 и перевести фикстуру на `memory_limit: none`.
- [ ] **Step 4: Run** `make test-runner` → PASS, включая `test_torch_imports_under_harness_limits`.
- [ ] **Step 5: Commit** `feat(runner): threads and memory_limit harness options`

### Task 3: Цели по произвольной метрике

**Files:**
- Modify: `runner/app/measure.py` (`verdict`), `runner/app/jobs.py` (`_parse_output`, сборка результата), `web/app/jobs.py` (`TARGET_METRICS`, `TARGET_OPS`, `parse_target`), `web/static/blocks/exercise.js` (`render`, `passBand`, `verdict`, `thresholdOf`)
- Test: `runner/tests/test_measure.py`, `runner/tests/test_jobs_python.py`, `web/tests/test_content.py` (или где сейчас тесты `parse_target`)

**Interfaces:**
- Produces:
  - `measure.verdict(values: dict[str, float], correct: bool, target: dict) -> bool`; `values` содержит `speedup` и метрики студента; ops `>=`, `>`, `<=`, `<`; отсутствующая метрика → `KeyError`, который `run_job` превращает в `{"status": "output_error", "message": "Харнесс не вернул метрику '<имя>' из цели задания"}`.
  - Формат harness'а: необязательное `"metrics": {"a": {<имя>: float}, "b": {<имя>: float}}` в последней строке JSON.
  - Ответ runner'а: `metrics` (метрики `b`) и `baseline_metrics` (метрики `a`), оба только если harness их вернул.
  - `web.jobs.parse_target`: метрика — любой идентификатор `\w+`, ops `>=`, `>`, `<=`, `<`.

- [ ] **Step 1: Тесты runner**

```python
def test_verdict_lower_is_better():
    assert verdict({"speedup": 1.0, "pss_growth_ratio": 0.2}, True, {"metric": "pss_growth_ratio", "op": "<=", "value": 0.3})
    assert not verdict({"speedup": 1.0, "pss_growth_ratio": 0.5}, True, {"metric": "pss_growth_ratio", "op": "<=", "value": 0.3})

def test_verdict_speedup_unchanged():
    assert verdict({"speedup": 3.2}, True, {"metric": "speedup", "op": ">=", "value": 3})

def test_missing_metric_is_output_error():  # фикстура pytest_sum + target pss_growth_ratio
    result = run_job(job({...}, target={"metric": "pss_growth_ratio", "op": "<=", "value": 0.3}))
    assert result["status"] == "output_error"
    assert "pss_growth_ratio" in result["message"]

def test_metrics_are_returned():  # новая фикстура harness/metrics_echo печатает metrics
    result = run_job(job_for("tests/fixtures/harness/metrics_echo", target={"metric": "m", "op": "<=", "value": 1}))
    assert result["metrics"] == {"m": 0.5} and result["passed"] is True
```

- [ ] **Step 2: Тесты web**

```python
def test_parse_target_metric_le():
    assert parse_target("pss_growth_ratio <= 0.3") == {"metric": "pss_growth_ratio", "op": "<=", "value": 0.3}

def test_parse_target_rejects_unknown_op():
    with pytest.raises(ContentError): parse_target("speedup => 3")
```

Существующий тест, проверяющий отказ на неизвестной метрике, удаляется: метрики больше не перечисляются в web, их наличие проверяет runner.

- [ ] **Step 3: Run** `make test` → новые тесты FAIL.
- [ ] **Step 4: Реализация runner и web.** Обновить комментарий над `TARGET_METRICS` в `web/app/jobs.py`: причина ограничения (ValueError → 500) теперь закрыта на стороне runner'а.
- [ ] **Step 5: UI.** В `exercise.js`: если метрика цели не `speedup`, плашка зачёта показывает `<метрика> = <значение>` и `порог <op> <число>`; таблица — строки `стартовый код` / `ваш код` со значениями `baseline_metrics` / `metrics`, затем время и разброс как сейчас. Для `speedup` вид не меняется. Метрику и операцию разбирать из `params.target` той же регуляркой, что в web (`/^\s*(\w+)\s*([<>]=?)\s*([\d.]+)\s*$/`).
- [ ] **Step 6: Run** `make test` → PASS; `make smoke` → PASS (раздел 01 рендерится, задания работают).
- [ ] **Step 7: Commit** `feat: exercise targets on arbitrary metrics`

### Task 4: `kind: series` — графики из нескольких линий

**Files:**
- Modify: `runner/app/jobs.py` (`SUPPORTED_KINDS`, ветка вывода, `_parse_lines_output`), `web/static/blocks/benchmark.js` (`drawLines`)
- Create: `runner/tests/fixtures/harness/linestest/{meta.yml,bench.py}`
- Test: `runner/tests/test_jobs_series.py`

**Interfaces:**
- Produces:
  - harness `kind: series` печатает `{"lines": [{"name": str, "points": [{"x": float, "y": float}, ...]}, ...]}`;
  - `_parse_lines_output(stdout: str) -> tuple[dict | None, str | None]`: непустой `lines`, у каждой линии строка `name` и непустой `points`, у каждой точки числовые `x` и `y`;
  - ответ runner'а: `{"status": "ok", "compile_command": None, "lines": [...]}`, без A/B-полей;
  - web: блок `benchmark` с `source:` (как sweep); `benchmark.js` при `data.lines` рисует `drawLines(container, lines, params)` — по линии на элемент, оси `params.x_label` / `params.y_label`, легенда включена, линейные шкалы (лог-шкала через `params.log_y: true`).

- [ ] **Step 1: Тесты**

```python
def test_series_returns_lines():
    result = run_job({"mode": "benchmark", "lang": "python", "harness_dir": "tests/fixtures/harness/linestest", "units": {"a": "N = 3\n"}, "target": None})
    assert result["status"] == "ok"
    assert [line["name"] for line in result["lines"]] == ["first", "second"]
    assert "speedup" not in result

@pytest.mark.parametrize("stdout", ['{"lines": []}', '{"lines": [{"name": "a", "points": []}]}',
                                    '{"lines": [{"name": "a", "points": [{"x": 1}]}]}', 'not json'])
def test_series_rejects_bad_output(stdout):
    payload, error = _parse_lines_output(stdout)
    assert payload is None and error
```

- [ ] **Step 2: Run** `make test-runner` → FAIL.
- [ ] **Step 3: Реализация** (sweep-ветку не трогать).
- [ ] **Step 4: Run** `make test-runner` → PASS.
- [ ] **Step 5: Commit** `feat: series harness kind with multi-line charts`

### Task 5: Каркас раздела и вспомогательная библиотека

**Files:**
- Create: `content/20-python-runtime/section.md` (фронтматтер `id: python-runtime`, `title: Python как рантайм сервиса`, `order: 20`; заголовки подглав 0–6 из спеки §4 с одной строкой-заглушкой под каждым)
- Create: `content/20-python-runtime/harness/_lib/memlib.py`
- Create: `content/20-python-runtime/harness/_lib/tinymodel.py`
- Test: `runner/tests/test_memlib.py` (импортирует из `/content/20-python-runtime/harness/_lib` через `sys.path`)

**Interfaces:**
- Produces:
  - `memlib.pss_mib(pid: int | None = None) -> float` — `Pss:` из `/proc/<pid|self>/smaps_rollup` в МиБ;
  - `memlib.rss_mib(pid: int | None = None) -> float` — `VmRSS` из `/proc/<pid|self>/status`;
  - `tinymodel.make_model(seed: int = 0) -> torch.nn.Module` — небольшой CNN на вход `(N, 3, 64, 64)`, ~1–5 мс на элемент на одном ядре, `eval()`, случайные веса с фиксированным seed;
  - `tinymodel.make_input(batch: int, seed: int = 0) -> torch.Tensor`.

- [ ] **Step 1: Тесты**

```python
def test_pss_grows_after_allocation():
    before = memlib.pss_mib(); data = bytearray(64 * 1024 * 1024); data[::4096] = b"x" * len(data[::4096])
    assert memlib.pss_mib() - before > 50

def test_tinymodel_is_deterministic():
    x = tinymodel.make_input(2)
    assert torch.equal(tinymodel.make_model()(x), tinymodel.make_model()(x))
```

- [ ] **Step 2: Run** `make test-runner` → FAIL. **Step 3:** реализация. **Step 4:** PASS. Раздел виден в оглавлении (`make smoke`).
- [ ] **Step 5: Commit** `feat(content): python-runtime section skeleton and helpers`

### Task 6: Подглава 0 — крючок «мы же ничего не писали»

**Files:**
- Create: `content/20-python-runtime/harness/fork_pss/{meta.yml,bench.py}`, `content/20-python-runtime/snippets/fork_pss.py`
- Modify: `content/20-python-runtime/section.md` (подглава 0)

**Interfaces:**
- Consumes: `memlib.pss_mib`, `kind: series` (задача 4), `threads`/`memory_limit` (задача 2).
- Produces: snippet определяет `build_data() -> dict[str, int]` (~1M ключей `f"tok{i}"`) и `worker(data, rounds: int) -> int` (чтение всех значений по ключам, сгенерированным внутри воркера, возврат суммы).

- [ ] **Step 1: Harness.** `kind: series`. Родитель: `data = unit_a.build_data()`, fork 4 воркеров через `os.fork()`; каждый каждые 0.2 с пишет свой PSS в pipe, пока выполняет `worker(data, rounds)`; родитель собирает `lines` = 4 линии `worker i` (x = секунды с fork, y = МиБ) + линия `parent`. Исключение в воркере → `os._exit(1)` с трассировкой в stderr; родитель при ненулевом коде ребёнка `sys.exit(1)`.
- [ ] **Step 2: Блок в `section.md`:** `benchmark id=fork-pss lang=python`, `harness: fork_pss`, `source: snippets/fork_pss.py`, `x_label: время, с`, `y_label: PSS, МиБ`; текст крючка из спеки §4.0.
- [ ] **Step 3: Проверить вручную** через UI (`make up`): суммарный PSS воркеров в конце > 2× размера данных родителя. Иначе увеличить `rounds`/размер данных.
- [ ] **Step 4: Commit** `feat(content): fork PSS hook`

### Task 7: Подглава 1 — CoW, viz и задание 1

**Files:**
- Create: `web/static/viz/cow-pages.js`
- Create: `content/20-python-runtime/harness/cow_exercise/{meta.yml,bench.py}`
- Create: `content/20-python-runtime/snippets/cow_starter.py`, `cow_ref.py`, `cow_freeze.py`
- Create: `content/20-python-runtime/harness/tensor_share/{meta.yml,bench.py}` (эксперимент «веса тензора остаются общими»)
- Modify: `content/20-python-runtime/section.md` (подглава 1)
- Test: `web/tests/test_content_targets.py` (новые тесты с маркером `content`)

**Interfaces:**
- Consumes: `memlib.pss_mib`, метрики задачи 3, `kind: series`.
- Produces:
  - контракт юнита задания: `build_data() -> object`, `prepare(data) -> None` (вызывается в родителе перед fork), `lookup(data, key: str) -> int`;
  - harness `kind: ab`, `repeats: 3`, `warmup: 0`: для каждого юнита (a, затем b, чередуя по повторам) родитель строит данные, вызывает `prepare`, fork 4 воркера; воркер мерит PSS сразу после fork и после прохода `lookup` по всем ключам (ключи генерирует сам), возвращает контрольную сумму; `samples` — время прохода, `check` — контрольная сумма, `metrics[u]["pss_growth_ratio"]` = (Σ PSS после − Σ PSS до) / (RSS родителя после `build_data` − RSS до), медиана по повторам;
  - `viz cow-pages`: `mount(element, params)`; сетка страниц родителя и ребёнка, клик/такт «читает» объект, его страница копируется и подсвечивается; `params.objects_per_page` (по умолчанию 4).

- [ ] **Step 1: Тесты content**

```python
@pytest.mark.content
def test_cow_reference_passes(): ...  # покрывается общим test_reference_solution_reaches_target

@pytest.mark.content
def test_cow_gc_freeze_alone_does_not_pass():
    result = execute_exercise("python-runtime", "cow-exercise", read_snippet("cow_freeze.py"))
    assert result["status"] == "ok" and result["passed"] is False

@pytest.mark.content
def test_cow_worker_exception_is_reported():
    code = read_snippet("cow_starter.py").replace("return data[key]", "raise RuntimeError('boom')")
    result = execute_exercise("python-runtime", "cow-exercise", code)
    assert result["status"] == "runtime_error" and "boom" in result["log"]
```

`execute_exercise(section_id, block_id, code)` — вспомогательная функция в `test_content_targets.py` поверх существующей `execute`.

- [ ] **Step 2: Run** `make verify-content` → новые тесты FAIL.
- [ ] **Step 3: Реализация** harness'а, сниппетов (`cow_starter.py`: dict, пустой `prepare`; `cow_ref.py`: отсортированные хэши ключей + значения в numpy, `np.searchsorted`; `cow_freeze.py`: стартовый код + `gc.freeze()` в `prepare`), viz и `tensor_share` (`kind: series`: PSS воркеров для `dict` и для тензора того же объёма, две группы линий).
- [ ] **Step 4: Текст подглавы 1** по спеке §4.1, блоки: `viz id=cow-pages`, `benchmark id=tensor-share`, `exercise id=cow-exercise` (`target: pss_growth_ratio <= 0.3`, `starter: snippets/cow_starter.py`, `reference: snippets/cow_ref.py`, `harness: cow_exercise`), выноска «Боль сервиса №1».
- [ ] **Step 5: Run** `make verify-content` → PASS; `make test-web` → PASS (парсер блоков, наличие viz-модуля).
- [ ] **Step 6: Commit** `feat(content): copy-on-write chapter and exercise 1`

### Task 8: Подглава 2 — арены pymalloc

**Files:**
- Create: `web/static/viz/pymalloc-arenas.js`
- Create: `content/20-python-runtime/harness/arenas/{meta.yml,bench.py}`, `snippets/arenas.py`
- Modify: `content/20-python-runtime/section.md` (подглава 2)

**Interfaces:**
- Consumes: `memlib.rss_mib`, `kind: series`.
- Produces: snippet задаёт `N_OBJECTS = 1_000_000` и `KEEP_EVERY = 10`; harness `kind: series` с двумя линиями `tracemalloc` и `RSS`, x = стадии `0` (старт), `1` (создано), `2` (удалено 90% вразброс), `3` (удалено всё), y = МиБ. Подписи стадий — в тексте под графиком.
- `viz pymalloc-arenas`: арены → пулы → блоки; кнопки «создать», «удалить через один», «удалить все»; арена светлеет (возвращается ОС) только когда пуста.

- [ ] **Step 1:** Проверить в контейнере размеры арены и пула на Python runner'а (`sys._debugmallocstats()`), подставить их в текст и viz.
- [ ] **Step 2:** Реализация harness'а, сниппета, viz, текста подглавы по спеке §4.2.
- [ ] **Step 3: Run** `make verify-content` (общий тест бенчмарков покрывает новый блок) → PASS; вручную: на стадии 2 RSS ≥ 80% от стадии 1, tracemalloc ≤ 20%.
- [ ] **Step 4: Commit** `feat(content): pymalloc arenas chapter`

### Task 9: Подглава 3 — GIL и задание 2

**Files:**
- Create: `content/20-python-runtime/harness/gil_threads/{meta.yml,bench.py}`, `snippets/gil_threads.py`
- Create: `content/20-python-runtime/harness/threads_exercise/{meta.yml,bench.py}`, `snippets/threads_starter.py`, `snippets/threads_ref.py`
- Modify: `content/20-python-runtime/section.md` (подглава 3)
- Modify: `web/tests/test_content_targets.py` (пропуск при нехватке ядер)

**Interfaces:**
- Consumes: `tinymodel`, `threads: auto` (задача 2), `kind: series`.
- Produces:
  - `gil_threads`: `kind: series`, `threads: auto`; линии `чистый Python`, `numpy.matmul`, `torch` (с `torch.set_num_threads(1)` в каждом потоке), x = число потоков 1, 2, 4, y = ускорение относительно 1 потока;
  - контракт юнита задания 2: `config(cores: int) -> tuple[int, int]` — (число процессов, `torch.set_num_threads` в каждом); стартовый код `return 4, cores`;
  - harness `threads_exercise`: `kind: ab`, `threads: auto`, `repeats: 5`; `cores = len(os.sched_getaffinity(0))`; если `cores < 4` — печать в stderr `на машине {cores} ядер, задание требует ≥ 4` и `sys.exit(3)`; процессы через `multiprocessing.get_context("spawn")`, импорт torch и прогрев до барьера, замер — время обработки K = 512 входов (батчи по 1) поделённых между процессами; `check` = число обработанных входов.

- [ ] **Step 1: Тест пропуска**

```python
def skip_if_not_enough_cores(result):
    if result.get("status") == "runtime_error" and "задание требует ≥ 4" in result.get("log", ""):
        pytest.skip(result["log"].strip())
```

Вызывать в `test_reference_solution_reaches_target` и тесте стартового кода сразу после `execute`.

- [ ] **Step 2:** Реализация harness'ов и сниппетов (`threads_ref.py`: `return 4, max(1, cores // 4)`).
- [ ] **Step 3:** Текст подглавы по спеке §4.3, блоки `benchmark id=gil-threads`, `exercise id=threads-exercise` (`target: speedup >= 1.5`), выноска «Боль сервиса №2».
  Эксперимент с oversubscription из спеки отдельным блоком не делается: его показывает первый замер стартового кода задания (`4 × cores` потоков), текст подводит к этому до задания.
- [ ] **Step 4: Run** `make verify-content` → PASS (или SKIP с сообщением на машине < 4 ядер).
- [ ] **Step 5: Commit** `feat(content): GIL chapter and exercise 2`

### Task 10: Подглавы 4–5 — event loop, сериализация и задание 3

**Files:**
- Create: `content/20-python-runtime/harness/loop_lag/{meta.yml,bench.py}`, `snippets/loop_lag.py`
- Create: `content/20-python-runtime/harness/decode_exercise/{meta.yml,bench.py}`, `snippets/decode_starter.py`, `snippets/decode_ref.py`
- Modify: `content/20-python-runtime/section.md` (подглавы 4, 5)
- Test: `web/tests/test_content_targets.py`

**Interfaces:**
- Consumes: `tinymodel`, `kind: series`.
- Produces:
  - snippet `loop_lag.py`: `async def handle(model, x)` — синхронный вызов модели; студент может заменить на `await asyncio.to_thread(model, x)`;
  - `loop_lag`: `kind: series`, `threads: auto`; задача-пульс спит 10 мс и пишет фактическую задержку; 20 «запросов» вызывают `handle`; линии `blocking` (стартовая версия из harness'а) и `ваш handle` (код блока), x = мс от старта, y = лаг цикла, мс;
  - контракт задания 3: `encode(img: np.ndarray) -> bytes` (клиент) и `decode(body: bytes) -> torch.Tensor` (сервер); `img` — `uint8` формы `(224, 224, 3)`; ожидаемый результат `decode` — `float32` тензор формы `(3, 224, 224)` со значениями `img / 255`, допуск `1e-6`;
  - harness `decode_exercise`: `kind: ab`, `repeats: 11`; замер — `decode(encode(img))` для 32 изображений; `check` — сумма тензоров; `correct` зависит и от формы/dtype: при несовпадении harness кладёт в `check` для юнита `NaN`.

- [ ] **Step 1: Тест неверного dtype**

```python
@pytest.mark.content
def test_decode_wrong_dtype_is_incorrect():
    code = read_snippet("decode_ref.py").replace("torch.float32", "torch.float64")
    result = execute_exercise("python-runtime", "decode-exercise", code)
    assert result["status"] == "ok" and result["correct"] is False
```

- [ ] **Step 2: Run** `make verify-content` → FAIL.
- [ ] **Step 3:** Реализация. `decode_starter.py`: `json.dumps(img.tolist()).encode()` / `torch.tensor(json.loads(body), dtype=torch.float32).permute(2, 0, 1) / 255`. `decode_ref.py`: `img.tobytes()` / `np.frombuffer(body, np.uint8).reshape(224, 224, 3)` → `torch.from_numpy(...)` → `permute` → `float().div_(255)`. Проверить, что `NaN` в `check` действительно даёт `correct: False` в `measure._close` (сравнение с NaN ложно); если нет — отдельный флаг формы в выводе, без изменения runner.
- [ ] **Step 4:** Текст подглав 4 и 5 по спеке §4.4–4.5, блоки `benchmark id=loop-lag`, `exercise id=decode-exercise` (`target: speedup >= 5`), выноски «Боль сервиса №3» и «№4».
- [ ] **Step 5: Run** `make verify-content` → PASS.
- [ ] **Step 6: Commit** `feat(content): event loop and serialization chapters, exercise 3`

### Task 11: Вывод, калибровка, финальная проверка

**Files:**
- Modify: `content/20-python-runtime/section.md` (подглава 6, таблица четырёх болей)
- Modify: `README.txt` (torch в образе, рекомендация ≥ 4 CPU и ≥ 4 ГиБ для Docker)
- Modify: `docs/superpowers/specs/2026-11-01-python-runtime-section-design.md` §7 (итоги калибровки)

- [ ] **Step 1:** Текст подглавы 6 по спеке §4.6.
- [ ] **Step 2: Калибровка.** На целевой машине 3 раза `make verify-content`. Для каждого задания записать фактическую метрику эталона, стартового кода и `cow_freeze.py`. Порог должен оставлять эталону запас ≥ 1.5× (для `<=` — значение эталона ≤ порог / 1.5), а стартовый код не должен проходить ни в одном прогоне. Если нет — поправить порог в `section.md` и записать в спеку.
- [ ] **Step 3: Полная проверка**

Run: `make test && make verify-content && make smoke`
Expected: всё PASS (задание 2 может быть SKIP на машине < 4 ядер — указать это в отчёте).

- [ ] **Step 4: Commit** `docs: calibrate thresholds; section conclusion`
