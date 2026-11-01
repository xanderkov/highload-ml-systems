# Раздел «Наивный сервис и свой батчер»: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить раздел `content/30-naive-service/`: HTTP-сервис студента под открытой нагрузкой, все боли раздела 20 в цифрах сервиса, пятая боль (батч из одного) и задание «собрать батч».

**Architecture:** Вся новая логика — в `content/30-naive-service/harness/_lib/servicelib.py` (запуск uvicorn с кодом студента, генератор нагрузки с открытым циклом, метрики). Эксперименты — `kind: series`, задание — `kind: ab` с метрикой `goodput_ratio`. Runner и web не меняются, кроме случаев, которые выявит спайк.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx/asyncio, torch CPU, pytest, Docker Compose, vanilla JS (viz).

**Spec:** `docs/superpowers/specs/2026-11-01-naive-service-section-design.md`

## Global Constraints

- Контент на русском; код и идентификаторы на английском.
- Разделы `01-cpu-cache` и `20-python-runtime` не меняются (кроме случаев, явно названных в задаче).
- Новых зависимостей в образах нет (если спайк докажет обратное — решение фиксируется в спеке §7).
- Генератор нагрузки — открытый цикл, latency от запланированного момента отправки.
- Генератор прибит к 1 логическому CPU, сервис — к остальным; при < 4 логических CPU: stderr содержит «задание требует ≥ 4 логических CPU», exit 3.
- Один запуск любого блока ≤ ~30 с на машине разработки (16 CPU).
- Задание: `kind: ab`, метрика `goodput_ratio` в `metrics["b"]` (и `["a"]`), цель `goodput_ratio >= X`, X из калибровки (ориентир 2).
- Числа в тексте — с оговоркой «в нашем замере»; ответ задания не выдаётся в тексте буквально; технические утверждения точные; про Triton — только то, что будем проверять.
- Выноска «Боль сервиса №5: модель обрабатывает запросы по одному.» — в подглаве 2.
- Тесты: `make test`, `make verify-content`; фокусно `docker compose run --rm --build web python -m pytest -q -m content -k <expr>`. Браузера нет: JS проверяется в Node с заглушками DOM.
- Сообщения коммитов заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Сервис студента не стартует** (синтаксическая ошибка, исключение при импорте): `start_service` бросает исключение с stderr uvicorn, harness завершается с ненулевым кодом, студент видит трассировку, а не таймаут. Тест в задаче 1.
2. **После любого исхода не остаётся процессов uvicorn** (успех, исключение в нагрузке, таймаут runner'а): контекст гасит сервис, sandbox добивает группу. Тест в задаче 1.
3. **Решение задания перепутало ответы между запросами** (результат батча раздан не тем futures): `correct: false` с понятной диагностикой. Тест в задаче 5.
4. **Батч не отправляется, пока не наполнится**: при редкой нагрузке сервис зависает — harness ловит отдельным коротким прогоном и сообщает текстом, а не таймаутом runner'а. Тест в задаче 5.
5. **Генератор не успевает держать заданный RPS** (отстаёт от расписания): harness замечает отставание и сообщает, а не выдаёт заниженный latency. Тест в задаче 1.

---

### Task 0: Спайк генератора нагрузки

**Files:**
- Create (throwaway, не коммитится): скрипты в scratchpad
- Modify: `docs/superpowers/specs/2026-11-01-naive-service-section-design.md` §7 п.1 и п.3

**Interfaces:**
- Produces: решение, записанное в спеку: какой клиент использует `run_load` (httpx.AsyncClient с keep-alive или сырой asyncio HTTP/1.1), максимальный устойчивый RPS генератора на 1 CPU, сколько воркеров uvicorn с torch помещается в `mem_limit 3g`.

- [ ] **Step 1:** В контейнере runner (через `docker compose run --rm runner python ...`, под тем же пользователем) поднять минимальный FastAPI-сервис (`/health`, `/predict` с `tinymodel` батч 1) на `127.0.0.1`, привязанный к CPU 1..N-1, и генератор с открытым циклом на CPU 0. Замерить, при каком RPS генератор отстаёт от расписания > 1 мс на p99 отправок — для httpx и для сырого asyncio.
- [ ] **Step 2:** Замерить пиковую память (сумма PSS) для 1, 2, 4, 8 воркеров uvicorn с `tinymodel`.
- [ ] **Step 3:** Записать вывод в спеку §7, закоммитить `docs: naive-service spike results`.

### Task 1: `servicelib`, каркас раздела

**Files:**
- Create: `content/30-naive-service/section.md` (фронтматтер `id: naive-service`, `title: Наивный сервис и свой батчер`, `order: 30`; заголовки подглав 0–6 из спеки §4 с однострочными заглушками; короткое введение-мостик из раздела 20 без чисел)
- Create: `content/30-naive-service/harness/_lib/servicelib.py`
- Create: `content/30-naive-service/harness/_lib/tinymodel.py` (копия из раздела 20 с комментарием об источнике)
- Create: `content/30-naive-service/harness/_lib/forklib.py` и `memlib.py` — только если понадобятся (копии с комментарием)
- Test: `runner/tests/test_servicelib.py` (импорт из `CONTENT_ROOT`/`/content`/`30-naive-service/harness/_lib`, как `test_memlib.py`)

**Interfaces:**
- Produces (`servicelib`):
  - `split_cpus() -> tuple[set[int], set[int]]` — (генератор, сервис); при < 4 CPU печатает в stderr `на машине {n} логических CPU, задание требует ≥ 4 логических CPU` и `sys.exit(3)`;
  - `start_service(app_path: str, *, workers: int = 1, torch_threads: int | None = None, cpus: set[int], env: dict | None = None)` — контекст-менеджер, отдаёт базовый URL `http://127.0.0.1:<port>`; uvicorn в своей группе процессов; ждёт `GET /health` до 30 с; при неудаче — `ServiceStartError` с хвостом stderr сервиса; при выходе — SIGTERM группе, через 3 с SIGKILL, `wait`;
  - `run_load(url: str, *, path: str = "/predict", rps: float, duration_s: float, make_body: Callable[[int], bytes], content_type: str, cpus: set[int], timeout_s: float = 10) -> LoadResult` — открытый цикл по решению спайка; запрос *i* запланирован на `t0 + i / rps`; latency = момент полного ответа − запланированный момент;
  - `LoadResult`: поля `latencies_ms: list[float]`, `errors: int`, `duration_s: float`, `lag_ms_p99: float` (отставание фактической отправки от плана), `responses: list[bytes]` (по индексу запроса, `None` при ошибке); методы `p50()`, `p99()`, `throughput()`, `goodput(slo_ms: float)`;
  - `LoadGeneratorLagging(Exception)` — бросается, если `lag_ms_p99 > 5`.
  - `cpu_seconds(pids: list[int]) -> float` — сумма utime+stime по `/proc/<pid>/stat` (для линии загрузки CPU).

- [ ] **Step 1: Тесты**

```python
def test_open_loop_counts_latency_from_schedule(slow_app):  # сервис: каждый ответ 200 мс, 1 воркер, без конкурентности
    with start_service(slow_app, cpus=SERVICE) as url:
        result = run_load(url, rps=20, duration_s=1, make_body=lambda i: b"x", content_type="application/octet-stream", cpus=LOAD)
    assert result.p99() > 2000  # очередь растёт: закрытый цикл показал бы ~200 мс

def test_goodput_and_percentiles():
    r = LoadResult(latencies_ms=[10, 20, 30, 1000], errors=1, lag_ms_p99=0, responses=[b""] * 4 + [None], duration_s=1)
    assert r.goodput(slo_ms=100) == 3 and r.p50() == 25

def test_broken_app_raises_with_stderr(broken_app):  # SyntaxError в файле приложения
    with pytest.raises(ServiceStartError, match="SyntaxError"):
        with start_service(broken_app, cpus=SERVICE):
            pass

def test_no_service_processes_left(fast_app):
    with start_service(fast_app, cpus=SERVICE) as url:
        pids = service_pids(url)
    time.sleep(0.5)
    assert all(not pid_alive(p) for p in pids)

def test_lagging_generator_is_reported(fast_app):
    with start_service(fast_app, cpus=SERVICE) as url, pytest.raises(LoadGeneratorLagging):
        run_load(url, rps=RPS_BEYOND_GENERATOR, duration_s=1, make_body=lambda i: b"x", content_type="application/octet-stream", cpus=LOAD)
```

Фикстуры — маленькие файлы приложений в `runner/tests/fixtures/apps/`; `RPS_BEYOND_GENERATOR` — из спайка ×3. `service_pids`/`pid_alive` — хелперы теста (поиск по `/proc/*/cmdline`).

- [ ] **Step 2:** Run `make test-runner` → FAIL. **Step 3:** реализация. **Step 4:** PASS; раздел виден в навигации (TestClient: `/` содержит `/section/naive-service`).
- [ ] **Step 5: Commit** `feat(content): naive-service section skeleton and servicelib`

### Task 2: Подглава 0 — крючок

**Files:**
- Create: `content/30-naive-service/snippets/naive_service.py` — FastAPI: `/health`; `async def predict(request)`: JSON-тело (список чисел изображения 3×64×64) → `torch.tensor` → `model(x)` прямо в обработчике → JSON-ответ
- Create: `content/30-naive-service/harness/hook/{meta.yml,bench.py}`
- Modify: `content/30-naive-service/section.md` (подглава 0)

**Interfaces:**
- Consumes: `servicelib` (задача 1), `tinymodel`.
- Produces: `kind: series`, `threads: auto`; линии `p50`, `p99` (мс) и `CPU сервиса, %` (доля занятых CPU сервиса за ступень, от `cpu_seconds`) при x = ступени RPS (из калибровки, ≥ 5 ступеней, до перегрузки); блок `benchmark id=hook` с `source: snippets/naive_service.py`, `x_label: запросов в секунду`, `y_label` с единицами (если линии в разных единицах — две линии в мс и третья в % с явным указанием в названии линии).

- [ ] **Step 1:** Реализовать, подобрать ступени: на последних ступенях p99 ≥ 10× p50 первой ступени, а `CPU сервиса` < 50 %. Записать числа в отчёт.
- [ ] **Step 2:** Текст подглавы 0 (спека §4.0), вопрос «Сервис стоит в очереди, а процессор отдыхает. Где время?».
- [ ] **Step 3: Run** `make verify-content` (общий тест бенчмарков) → PASS, время блока ≤ 30 с.
- [ ] **Step 4: Commit** `feat(content): naive service hook`

### Task 3: Подглава 1 — все четыре боли в одном сервисе

**Files:**
- Create: `content/30-naive-service/snippets/service_def.py` (как наивный, но `def` вместо `async def`), `service_binary.py` (+ бинарное тело `application/octet-stream`, `np.frombuffer` → тензор), `service_workers.py` (+ параметры воркеров и потоков в константах наверху файла)
- Create: `content/30-naive-service/harness/four_pains/{meta.yml,bench.py}`
- Modify: `section.md` (подглава 1)

**Interfaces:**
- Consumes: `servicelib`, снипеты задачи 2.
- Produces: `kind: series`; по линии p99 на каждый вариант (`наивный`, `def`, `+ бинарный протокол`, `+ воркеры × потоки`), x = RPS (общие ступени); вариант с воркерами читает `WORKERS`/`TORCH_THREADS` из своего файла (блок редактируемый: `source` и `starter` — этот файл), остальные варианты берутся харнессом из `snippets/` как есть. Таблица в тексте: «боль → чем чинили → во сколько изменился p99/максимальный RPS в нашем замере», со ссылками на подглавы раздела 20.

- [ ] **Step 1:** Реализация; проверить, что каждый шаг ощутимо улучшает либо p99, либо пропускную способность; если какой-то шаг не виден на CPU-модели — честно сказать в тексте и отчёте.
- [ ] **Step 2:** Текст подглавы 1 по спеке §4.1.
- [ ] **Step 3: Run** `make verify-content` → PASS, блок ≤ 30 с.
- [ ] **Step 4: Commit** `feat(content): four pains in one service`

### Task 4: Подглавы 2–3 — батч из одного, идея батчинга, viz

**Files:**
- Create: `content/30-naive-service/harness/batch_curve/{meta.yml,bench.py}`, `snippets/batch_curve.py`
- Create: `web/static/viz/batch-queue.js`
- Modify: `section.md` (подглавы 2, 3)

**Interfaces:**
- Produces:
  - `batch_curve`: `kind: series`, линия «время на элемент, мс» при батче 1, 2, 4, 8, 16, 32, 64 (медиана, `torch.set_num_threads` — как у воркера в задаче 3);
  - `viz batch-queue`: `mount(element, params)`; временная шкала прихода запросов (детерминированный псевдослучайный поток), окна сбора и отправленные батчи для `max_queue_delay` из `params.delays` (по умолчанию `[0, 2, 10]` мс) и `max_batch_size` (по умолчанию 8); подписи на русском; правильные плюральные формы.
- Выноска «Боль сервиса №5: модель обрабатывает запросы по одному.» в конце подглавы 2.

- [ ] **Step 1:** Реализация; в отчёт — во сколько раз батч 32 дешевле батча 1 на элемент.
- [ ] **Step 2:** Тексты подглав 2 и 3 по спеке §4.2–4.3 (схема цикла сбора без готового кода решения).
- [ ] **Step 3:** viz проверить в Node с linkedom (scratchpad), `make test-web` (`test_every_viz_block_has_a_module`) → PASS.
- [ ] **Step 4: Commit** `feat(content): batch-of-one ceiling and batching idea`

### Task 5: Подглава 4 — задание «собрать батч»

**Files:**
- Create: `content/30-naive-service/harness/batcher_exercise/{meta.yml,bench.py,app.py}` — `app.py` — каркас сервиса: бинарный протокол, `asyncio.Queue`, фоновая задача «`collect_batch` → модель в потоке (`asyncio.to_thread`) → `future.set_result` по каждому элементу», импортирует `collect_batch` из модуля студента
- Create: `content/30-naive-service/snippets/batcher_starter.py` (`return [await queue.get()]`), `batcher_ref.py`
- Modify: `section.md` (подглава 4)
- Test: `web/tests/test_content_targets.py` (новые тесты с маркером `content`; `read_snippet(name, section_dir="30-naive-service")`)

**Interfaces:**
- Consumes: `servicelib`, `execute_exercise`, `read_snippet`, `skip_if_not_enough_cores` (адаптировать текст проверки к «≥ 4 логических CPU», не ломая раздел 20).
- Produces:
  - контракт: `async def collect_batch(queue: asyncio.Queue, max_batch_size: int, max_delay: float) -> list`; элементы очереди — непрозрачные объекты каркаса;
  - harness `kind: ab`, `threads: auto`, `repeats: 3`, `warmup: 0`; для каждого повтора A, затем B (чередуя порядок по повторам): поднять сервис с юнитом, прогреть, подать открытую нагрузку `RPS_EXERCISE` на `DURATION_S` (из калибровки), посчитать goodput при `SLO_MS`; `samples` — p99 мс; `check` — точное число запросов, чьи ответы совпали с эталонным выходом модели для своего входа (`torch.allclose(atol=1e-5)`), если все совпали, иначе `NaN`; `metrics[u]["goodput_ratio"]` = медиана goodput юнита / медиана goodput стартового кода (у `a` = 1.0);
  - проверка редкой нагрузки (до основного прогона, для каждого юнита): 5 запросов с интервалом 300 мс; если p99 > `max_delay` + 200 мс — stderr «батч не уходит, пока не наберётся max_batch_size: при редких запросах ответ ждёт …» и exit 1;
  - если CPU сервиса > 90 % при редкой нагрузке — stderr-предупреждение «похоже на busy-wait в collect_batch» (не провал).

- [ ] **Step 1: Тесты content**

```python
@pytest.mark.content
def test_batcher_mixed_up_responses_are_incorrect():
    code = read_snippet("batcher_ref.py", "30-naive-service") + MIXUP_PATCH  # переставляет элементы батча
    result = execute_exercise("naive-service", "batcher-exercise", code)
    skip_if_not_enough_cores(result)
    assert result["status"] == "ok" and result["correct"] is False

@pytest.mark.content
def test_batcher_waiting_for_full_batch_is_reported():
    code = WAIT_FOR_FULL_BATCH  # while len(batch) < max_batch_size: batch.append(await queue.get())
    result = execute_exercise("naive-service", "batcher-exercise", code)
    skip_if_not_enough_cores(result)
    assert result["status"] == "runtime_error" and "max_batch_size" in result["log"]
```

`MIXUP_PATCH` и `WAIT_FOR_FULL_BATCH` — строки в тестовом файле; патч не должен зависеть от деталей эталона больше, чем от контракта (например, обёртка над `collect_batch`, переставляющая список).

- [ ] **Step 2: Run** фокусно → FAIL. **Step 3:** реализация + калибровка `RPS_EXERCISE`, `SLO_MS`, `DURATION_S` так, чтобы клик ≤ 30 с, эталон давал `goodput_ratio` ≥ 1.5× порога, старт не проходил.
- [ ] **Step 4:** Текст подглавы 4: контракт, что делает каркас, что меряется, ловушки — без готового решения.
- [ ] **Step 5: Run** `make test`, фокусно, затем `make verify-content` → PASS.
- [ ] **Step 6: Commit** `feat(content): batcher exercise`

### Task 6: Подглавы 5–6, калибровка, финальная проверка

**Files:**
- Create: `content/30-naive-service/harness/delay_tradeoff/{meta.yml,bench.py}`
- Modify: `section.md` (подглавы 5, 6), `README.txt` (раздел 30: ≥ 4 логических CPU), спека §7 (результаты калибровки)

**Interfaces:**
- Consumes: каркас и эталон задачи 5.
- Produces: `delay_tradeoff`: `kind: series`, линии p50, p99, throughput при `max_queue_delay` из `[0, 1, 2, 5, 10, 20]` мс на эталонном батчере при фиксированной нагрузке; блок редактируемый (студент может вставить свой `collect_batch`).

- [ ] **Step 1:** Реализация и текст подглав 5–6 (спека §4.5–4.6): таблица «сделали руками / не сделали», мост к Triton только как то, что будем проверять.
- [ ] **Step 2: Калибровка.** 3 прогона `make verify-content`; таблица метрик эталона/старта задания в спеку §7; пороги правятся только при нарушении правила «эталон ≥ 1.5× порога, старт не проходит».
- [ ] **Step 3: Полная проверка** `make test && make verify-content` → PASS. `make smoke` не запускается (нет браузера) — указать в отчёте.
- [ ] **Step 4: Commit** `docs: naive-service conclusion and calibration`
