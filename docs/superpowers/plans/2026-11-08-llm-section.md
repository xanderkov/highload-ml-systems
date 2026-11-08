# Раздел «LLM» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** раздел `content/50-llm/`: своя крошечная GPT и свой continuous batching, затем llama.cpp (и необязательно vLLM) под той же нагрузкой, главы 0–6, два задания, вывод курса.

**Architecture:** всё меряется в runner: студенческий движок — отдельный процесс на 3 сервисных CPU, генератор нагрузки — CPU 0; `llama-server` копируется в образ runner из `ghcr.io/ggml-org/llama.cpp:server-b12199` и запускается харнессом как подпроцесс с нужными `-np`/`-c`. vLLM — сервис compose в профиле `vllm`, по умолчанию не запущен.

**Tech Stack:** torch CPU (runner), llama.cpp build 12199 (OpenAI-совместимый `/v1/completions`, SSE), vLLM v0.33.0 CPU (необязательно), существующие runner/web (FastAPI, pytest, Ace).

**Spec:** `docs/superpowers/specs/2026-11-08-llm-section-design.md`

## Global Constraints

- Только CPU; сервису (свой движок, llama-server, vLLM) — 3 CPU (`servicelib.service_cpus`, как в разделах 30/40; у vLLM `${TRITON_CPUS:-1-3}`), генератор — CPU 0.
- Все замеры раздела 50 держат ту же файловую блокировку, что раздел 40 (`/models/.lock`, `fcntl.flock`): CPU 1–3 общие с Triton.
- Модель llama.cpp: `Qwen/Qwen2.5-0.5B-Instruct-GGUF`, файл `qwen2.5-0.5b-instruct-q8_0.gguf`, в образе — `/opt/models/qwen05-q8.gguf`; бинарь — `/opt/llama/llama-server`, `LD_LIBRARY_PATH=/opt/llama`.
- Нагрузка по умолчанию: 80 % коротких ответов (16 токенов), 20 % длинных (128), `ignore_eos`, temperature 0.
- Генератор нагрузки — только stdlib (asyncio), без aiohttp/httpx.
- Тексты — по-русски, «в нашем замере», каждое число в тексте есть в калибровочной таблице спеки §7.x; в каждой главе: текст → замер → вывод.
- Порог задания: эталон ≥ 1,5× порога, стартовый код не проходит (правило разделов 30/40).
- Таймаут любого харнесса ≤ 240 с (`test_run_timeout_exceeds_every_harness_timeout`).
- Новые CSS-классы — только полными литералами Tailwind; UI проверяет автор в Firefox.
- Разделы 20–40 работают без изменений.

## Review Focus

- **Движок студента зависает** (не убирает закончившиеся строки, не принимает новые) — через `STALL_S` без токенов харнесс завершает процесс движка и пишет «за N с не пришло ни одного токена: …», а не ждёт таймаута runner (тест в задаче 3).
- **Движок студента бросает исключение в процессе-движке** — студент видит трассировку из дочернего процесса, а не «0 ответов» (тест в задаче 3).
- **`llama-server` не стартовал** (неверный аргумент, нехватка памяти под `-c`) — сообщение с хвостом его stderr, процесс не остаётся висеть (тест в задаче 4).
- **Задание 2: `SLOTS`/`CTX_TOTAL` не числа, ноль, отрицательные или `CTX_TOTAL > KV_BUDGET`** — понятное сообщение до старта сервера (тест в задаче 8).
- **Сервис vLLM не запущен или запущен, но ещё грузится** — блок отвечает «не запущен / ещё загружается, вот как запустить», а не трассировкой (тест в задаче 9).

---

### Task 1: llama-server в образе runner + закрытие открытых вопросов 1, 2, 4, 5

**Files:**
- Modify: `runner/Dockerfile` (multi-stage `COPY --from=ghcr.io/ggml-org/llama.cpp:server-b12199 /app /opt/llama`, загрузка GGUF, `ENV LD_LIBRARY_PATH=/opt/llama`)
- Modify: `runner/pytest.ini` (маркер `llm`; `addopts = -m "not triton and not llm"`)
- Modify: `Makefile` (цель `test-llm`: `docker compose run --rm --build runner python -m pytest -q -m llm`; `verify-content: test-triton test-llm`)
- Create: `runner/tests/test_llama_binary.py`
- Modify: спека §7 (ответы на вопросы 1, 2, 4, 5 с цифрами)

**Interfaces:**
- Produces: `/opt/llama/llama-server`, `/opt/models/qwen05-q8.gguf` в образе runner; маркер `llm`.

- [ ] **Step 1: Write the failing tests** (`@pytest.mark.llm`):
  - `test_llama_server_runs_in_runner_image`: `subprocess.run(["/opt/llama/llama-server", "--version"])` → returncode 0, в выводе `build 12199`.
  - `test_llama_server_serves_under_sandbox_limits`: запуск через `sandbox._limits(2048, MAX_FILE_MB)` как `preexec_fn`, `-m /opt/models/qwen05-q8.gguf -t 3 -np 16 -c 8192 --port <free>`; `/health` = 200 за ≤ 30 с; `/v1/completions` с `max_tokens=16, ignore_eos=true` → ровно 16 токенов (`usage.completion_tokens == 16`).
- [ ] **Step 2: Run** `make test-llm` — Expected: FAIL (нет бинаря).
- [ ] **Step 3: Implement Dockerfile changes.** Если бинарь не запускается в `python:3.12-slim` (glibc/libstdc++) — сначала попробовать скопировать недостающие `.so` из того же образа; если не выходит — запасной вариант спеки §7.1 (отдельный сервис), записать `Ruling:` и остановиться на согласование (меняется архитектура).
- [ ] **Step 4: Run** `make test-llm` — Expected: 2 passed. Записать рост образа runner (`docker image ls`).
- [ ] **Step 5: Ответить на вопросы спеки §7 в scratchpad-скрипте и записать в спеку:**
  - (2) запрос с `max_tokens` больше `ctx/np` минус промпт: что приходит (`finish_reason`, `completion_tokens`, HTTP-код, сдвиг контекста) — при `-np 4 -c 1024` и `max_tokens=512`;
  - (4) максимальный `-c`, при котором сервер стартует под RLIMIT_AS 2048 МБ при `-np 32`;
  - (5) какие флаги (`-b`, `-ub`, chunked prefill) влияют на паузу декода при длинном промпте — пауза у коротких при промпте ~1500 токенов с флагами по умолчанию и с `-ub 128`.
- [ ] **Step 6: Commit** `feat(runner): llama-server and GGUF model in runner image` (Dockerfile, pytest.ini, Makefile, тест, спека).

### Task 2: `tinygpt` и `KVBatch`

**Files:**
- Create: `content/50-llm/harness/_lib/tinygpt.py`
- Test: `runner/tests/test_tinygpt.py` (импорт через `sys.path` на `_lib`, как `test_tritonlib.py`)

**Interfaces:**
- Produces:
  - `Config(n_layer: int, d_model: int, n_head: int, vocab: int, max_len: int)`; `DEFAULT: Config`.
  - `make_model(cfg: Config = DEFAULT, seed: int = 0) -> TinyGPT` (`eval()`, `requires_grad_(False)`).
  - `TinyGPT.prefill(prompt: list[int]) -> tuple[int, KV]` — первый сгенерированный токен (argmax) и KV одного запроса.
  - `TinyGPT.decode_step(batch: KVBatch, last: torch.Tensor) -> torch.Tensor` — следующий токен (argmax) для каждой строки; дописывает K/V в `batch`.
  - `KVBatch()`; `add(kv: KV) -> int` (индекс новой строки); `keep(rows: list[int]) -> None` (оставить эти строки в этом порядке); `__len__`; `lengths: list[int]`; `nbytes() -> int`.
  - `generate_alone(model, prompt: list[int], n: int) -> list[int]` — эталон без батча.
  - `generate_nocache(model, prompt, n) -> list[int]` — пересчёт всего префикса на каждом шаге (глава 1).
  - `kv_bytes_per_token(cfg) -> int` = `2 * n_layer * d_model * 4`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cached_equals_nocache`: для 3 промптов разной длины `generate_alone(m, p, 32) == generate_nocache(m, p, 32)`.
  - `test_batch_equals_alone_with_joins_and_drops`: 6 запросов разной длины промпта и разного `n`; в цикле: добавлять по одному через `add` между шагами, после окончания строки `keep` без неё (порядок строк меняется); токены каждого запроса == `generate_alone`.
  - `test_deterministic_by_seed`: два `make_model(seed=0)` дают одинаковые токены; `seed=1` — другие.
  - `test_kv_bytes`: `batch.nbytes() == sum(lengths) * kv_bytes_per_token(cfg)` (без учёта паддинга — `nbytes` считает полезные байты).
- [ ] **Step 2: Run** `docker compose run --rm --build --no-deps runner python -m pytest -q tests/test_tinygpt.py` — Expected: FAIL (нет модуля).
- [ ] **Step 3: Implement.** Pre-LN декодер, learned positional embedding, causal attention через `torch.nn.functional.scaled_dot_product_attention` с маской паддинга; `KVBatch` хранит K/V `[layers, rows, heads, max_len_in_batch, head_dim]` с паддингом справа и `lengths`; `decode_step` строит маску из `lengths`. Детерминизм: веса из `torch.Generator(seed)`, init с масштабом, при котором argmax не залипает на одном токене (тест: в 32 токенах ≥ 4 разных).
- [ ] **Step 4: Калибровка `DEFAULT`** (scratchpad-скрипт, `torch.set_num_threads(3)`, `taskset 1-3`): цель — шаг декода при батче 1 и KV 64 — 2–8 мс, при батче 16 — ≤ 2,5× батча 1. Подобрать `n_layer`/`d_model`/`vocab` (стартовая точка 4 × 256, vocab 1024). Цифры — в спеку §7.x.
- [ ] **Step 5: Run tests** — Expected: PASS.
- [ ] **Step 6: Commit** `feat(content): tinygpt with KV cache and KVBatch`.

### Task 3: процесс-движок и генератор нагрузки `llmload`

**Files:**
- Create: `content/50-llm/harness/_lib/llmload.py`
- Create: `content/50-llm/harness/_lib/stand.py`
- Test: `runner/tests/test_llmload.py`

**Interfaces:**
- Consumes: `tinygpt.make_model`, `KVBatch`.
- Produces:
  - `Request(id: int, prompt: list[int], max_new: int)`; `Request.send(token: int) -> None` — студент отдаёт токен; после `max_new` токенов запрос считается законченным (`Request.done -> bool`).
  - `Inbox.poll(limit: int) -> list[Request]` — без ожидания, не больше `limit`; `Inbox.closed -> bool`; `Inbox.wait() -> None` — блокирует, пока не придёт запрос или inbox не закроется (для движка без работы).
  - `Mix(short: int = 16, long: int = 128, long_frac: float = 0.2, prompt_len: int = 16, seed: int = 1)`; `Mix.requests(n) -> list[Request]`.
  - `run_engine(engine_fn, *, model_seed: int, max_batch: int, rps: float, duration_s: float, mix: Mix, service_cpus: set[int], load_cpu: int) -> Result` — движок в `multiprocessing` (spawn) процессе на `service_cpus` с `torch.set_num_threads(len(service_cpus))`, генератор в родителе на `load_cpu`; токены приходят родителю через `multiprocessing.Queue` с отметкой времени родителя при получении.
  - `run_http(url: str, model: str, *, rps, duration_s, mix, load_cpu) -> Result` — тот же контракт для `/v1/completions` со `stream: true` (SSE), разбор как в спайковом `load.py`.
  - `Result`: `per_request: list[Rec]` (`cls: str` = `"short"|"long"`, `ttft_s`, `e2e_s`, `tokens: list[int] | None`, `n_tokens`, `itl_s: list[float]`, `error: str | None`); `ttft(cls, q)`, `e2e(cls, q)`, `tok_per_s()`, `goodput(ttft_slo_s)` (запросов в секунду без ошибки, с полным числом токенов и TTFT ≤ SLO), `truncated()`, `errors()`.
  - `LoadGeneratorLagging(Exception)`: генератор отстал от расписания больше чем на 50 мс; `run_engine`/`run_http` при этом один раз повторяют прогон (`gc.disable()` на время прогона, как `stand.load` раздела 40), при повторном отставании — исключение с понятным текстом.
  - `STALL_S = 10`; `EngineStalled(Exception)`, `EngineCrashed(Exception)` с текстом трассировки дочернего процесса.
  - `stand.py`: `fail(msg)`, `exclusive()` (flock `/models/.lock`, ожидание `LOCK_WAIT_S = 30`, сообщение «замер другого блока ещё идёт…»), `cpus() -> tuple[int, set[int]]` (CPU генератора и сервисные, через логику `servicelib.split_cpus`/`service_cpus` раздела 30 — скопировать нужные функции, не импортировать раздел 30).

- [ ] **Step 1: Write the failing tests:**
  - `test_engine_tokens_match_alone`: эталонный движок (пишется в тесте как фикстура `fixtures/engine_ref.py`, тот же код, что станет `snippets/engine_ref.py` в задаче 6) при 4 RPS × 2 с: у каждого запроса `tokens == generate_alone`, `errors() == 0`.
  - `test_stalled_engine_is_reported`: движок, который принимает запросы и никогда не шлёт токены → `EngineStalled` за ≤ `STALL_S + 5` с, процесс движка мёртв.
  - `test_crashing_engine_shows_traceback`: движок с `raise ValueError("boom")` → `EngineCrashed`, в тексте `ValueError: boom` и имя файла движка.
  - `test_sse_parsing`: локальный HTTP-сервер из stdlib отдаёт SSE с 3 чанками и `[DONE]` → `n_tokens == 3`, `ttft_s` задан; ответ 500 → `error` содержит код.
  - `test_goodput_counts_truncated_as_bad`: `Result` из синтетических `Rec`: обрезанный (n_tokens < max_new) не входит в goodput.
- [ ] **Step 2: Run** — Expected: FAIL (нет модуля).
- [ ] **Step 3: Implement.** Движок получает запросы через `Inbox`, сделанный поверх `multiprocessing.Queue` (родитель кладёт `(id, prompt, max_new)` в момент отправки по открытому расписанию); `Request.send` кладёт `(id, token)` в выходную очередь. Родитель считает зависание, если за `STALL_S` нет ни одного токена при незаконченных запросах.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(content): engine process and streaming load generator for LLM section`.

### Task 4: `llama.serve`

**Files:**
- Create: `content/50-llm/harness/_lib/llama.py`
- Test: `runner/tests/test_llama_serve.py` (`@pytest.mark.llm`)

**Interfaces:**
- Consumes: `stand.cpus`.
- Produces: `serve(*, slots: int, ctx_total: int, cpus: set[int], extra: list[str] = []) -> ContextManager[str]` (URL; `taskset` на `cpus`, `-t len(cpus)`, `--alias q`, порт свободный; ждёт `/health` ≤ 30 с; останавливает в `finally`); `LlamaStartError(Exception)` с хвостом stderr (≤ 40 строк); `MODEL = "q"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_serve_answers_completion`: `serve(slots=4, ctx_total=2048, cpus=...)` → `run_http` на 2 RPS × 2 с, `errors() == 0`.
  - `test_bad_args_raise_with_stderr`: `extra=["--no-such-flag"]` → `LlamaStartError`, в тексте `no-such-flag`; после выхода нет живого `llama-server` (`pgrep`).
- [ ] **Step 2: Run** `make test-llm` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(content): llama-server helper for harnesses`.

### Task 5: Скелет раздела, главы 0 и 1

**Files:**
- Create: `content/50-llm/section.md` (front matter `id: llm`, `title: "LLM: батч из шагов, а не из запросов"`, `order: 50`; главы 0–1)
- Create: `content/50-llm/harness/hook/{meta.yml,bench.py}`, `content/50-llm/harness/kv_cache/{meta.yml,bench.py}`
- Modify: `web/app/templates/index.html` (список «скоро» — пустой; убрать цикл, если пустой список оставляет пустую разметку), `web/tests/test_pages.py` (карточка раздела 50 — ссылка, «скоро» нет)
- Modify: `content/40-triton/section.md` («бонусной части» → ссылка `/section/llm`)

**Interfaces:**
- Consumes: `tinygpt`, `stand`.
- Produces: блоки `llm-hook` (`kind: series`: время шага, мс, от батча 1…32; линия «ток/с суммарно»), `llm-kv-cache` (`series`: мс/токен без кэша и с кэшем от длины ответа 16…512; память KV на запрос, КиБ).

- [ ] **Step 1: Write the failing test** в `web/tests/test_pages.py`: главная содержит ссылку `/section/llm` и не содержит «LLM-сервинг» в карточке «скоро»; страница `/section/llm` отдаёт 200 и содержит «0. Генерация — это цикл».
- [ ] **Step 2: Run** `make test-web` — Expected: FAIL.
- [ ] **Step 3: Implement** харнессы (замер шага — медиана 20 шагов после 5 прогревочных, KV одной длины 64) и тексты глав 0–1 по спеке §4; числа — из прогона харнессов, вносятся в спеку §7.x.
- [ ] **Step 4: Run** `make test` и `docker compose run --rm --build web python -m pytest -q -m content -k "50-llm"` — Expected: PASS (блоки отрабатывают).
- [ ] **Step 5: Commit** `feat(content): LLM section skeleton, chapters 0-1`.

### Task 6: Глава 2 и задание 1 (continuous batching)

**Files:**
- Create: `content/50-llm/snippets/engine_starter.py` (статический батч), `content/50-llm/snippets/engine_ref.py` (continuous batching; побайтно = `runner/tests/fixtures/engine_ref.py` из задачи 3)
- Create: `content/50-llm/harness/static/`, `content/50-llm/harness/engine_exercise/`, `content/50-llm/harness/engine_vs_static/` (`meta.yml`, `bench.py`)
- Modify: `content/50-llm/section.md` (главы 2–3)
- Modify: `web/tests/test_content_targets.py` (ошибочные решения), `web/tests/test_content.py` (копия `engine_ref` = фикстура)

**Interfaces:**
- Consumes: `llmload.run_engine`, `Mix`, `stand`, `tinygpt`.
- Produces: функция студента `engine(model, inbox, max_batch) -> None` (юнит b); блоки `llm-static` (`series`), `llm-engine` (`exercise`, `kind: ab`, `lang: python`), `llm-engine-vs-static` (`benchmark`, редактируемый, `source`/`starter` = `engine_starter.py`).

- [ ] **Step 1: Write the failing tests** в `web/tests/test_content_targets.py` (`@pytest.mark.content`):
  - `test_engine_mixed_rows_is_incorrect`: эталон с `keep` в обратном порядке строк → `check` b не 1.0, в логе «не совпали с генерацией в одиночку».
  - `test_engine_never_drops_is_reported`: эталон без `keep` → в логе «за 10 с не пришло ни одного токена» (или ошибка KV длины — тогда сообщение указывает на `keep`).
  - `test_engine_exception_is_shown`: `raise RuntimeError("oops")` в начале → в логе `RuntimeError: oops`.
  - Общие `test_reference_solution_reaches_target` / `test_starter_code_does_not_reach_target` подхватят блок автоматически.
- [ ] **Step 2: Run** `... -m content -k engine` — Expected: FAIL (нет блоков).
- [ ] **Step 3: Implement** харнессы. `engine_exercise`: проверка корректности (2 RPS × 3 с, все токены == `generate_alone`) затем `REPEATS` прогонов смеси при `RPS`; `samples` — p99 TTFT коротких, `check`, `metrics` — `goodput`, `goodput_ratio` (b к эталону a). Цель блока: `target: goodput_ratio >= 0.9`. `RPS`, `TTFT_SLO_S`, `max_batch` — калибровка: стартовый код ≤ 0,6 эталона, эталон ≥ 1,5× порога по goodput относительно стартового (если правило 1,5× в этой метрике не выполнимо — `Ruling:` с выбранной метрикой).
- [ ] **Step 4: Тексты глав 2–3**; числа — в спеку §7.x.
- [ ] **Step 5: Run** `make test` и `... -m content -k "50-llm"` — Expected: PASS.
- [ ] **Step 6: Commit** `feat(content): static batching chapter and continuous batching exercise`.

### Task 7: Глава 4 — llama.cpp

**Files:**
- Create: `content/50-llm/harness/llama_slots/`, `content/50-llm/harness/llama_vs_engine/`
- Modify: `content/50-llm/section.md` (глава 4)

**Interfaces:**
- Consumes: `llama.serve`, `llmload.run_http`, `run_engine`, `engine_ref`.
- Produces: блоки `llm-llama-slots` (`series`: TTFT p99 коротких и ток/с от RPS при `-np` 1/4/16, `-c` = `np * 256`), `llm-llama-vs-engine` (`series`: ток/с от RPS — llama.cpp `-np 16` против эталонного движка).

- [ ] **Step 1: Run харнессы вручную** через runner (`docker compose run --rm runner ...`), подобрать ступени RPS так, чтобы видно было насыщение каждого `-np`; таймаут ≤ 240 с.
- [ ] **Step 2: Текст главы 4** с оговоркой спеки (C++/q8 против torch/fp32 — сравниваем форму кривых); числа — в спеку §7.x.
- [ ] **Step 3: Run** `... -m content -k "llama"` — Expected: PASS.
- [ ] **Step 4: Commit** `feat(content): llama.cpp slots chapter`.

### Task 8: Задание 2 — бюджет KV

**Files:**
- Create: `content/50-llm/snippets/kv_starter.py` (`SLOTS = 32`, `CTX_TOTAL = 8192`), `content/50-llm/snippets/kv_ref.py`
- Create: `content/50-llm/harness/kv_budget_exercise/`
- Modify: `content/50-llm/section.md` (глава 5), `web/tests/test_content_targets.py`

**Interfaces:**
- Consumes: `llama.serve`, `run_http`, `Mix(long=512, prompt_len=…)`.
- Produces: блок `llm-kv-budget` (`exercise`, `kind: ab`, `lang: python`); `KV_BUDGET` (токенов) — константа харнесса, выбирается калибровкой задачи 1 (вопрос 4) и смесью.

- [ ] **Step 1: Write the failing tests:**
  - `test_kv_budget_rejects_bad_values`: `SLOTS = 0`, `SLOTS = "8"`, `CTX_TOTAL = KV_BUDGET + 1` → сообщение до старта сервера («SLOTS должен быть целым ≥ 1», «CTX_TOTAL больше бюджета …»), `check` b не 1.0.
  - `test_kv_budget_too_few_slots_fails_target`: `SLOTS = 1` с полным бюджетом → цель не достигнута, в логе TTFT.
  - `test_kv_budget_too_many_slots_truncates`: стартовые числа → в логе «N ответов обрезаны: в слот помещается … токенов» (формулировка — по поведению из задачи 1, вопрос 2).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** харнесс: a — эталонные числа, b — числа студента; проверка значений → `serve` → `REPEATS` прогонов → `samples` (p99 TTFT), `check` (1.0, если нет обрезанных), `metrics` (`goodput`, `goodput_ratio`). Цель блока — калибровка с правилом 1,5×.
- [ ] **Step 4: Текст главы 5** (формула: в слот помещается `CTX_TOTAL / SLOTS` токенов; связь с главой 1 — память KV); числа — в спеку §7.x.
- [ ] **Step 5: Run** `... -m content -k "kv"` — Expected: PASS.
- [ ] **Step 6: Commit** `feat(content): KV budget exercise`.

### Task 9: Глава 6 — длинный промпт, vLLM, вывод

**Files:**
- Create: `content/50-llm/harness/long_prompt/`, `content/50-llm/harness/vllm/`
- Modify: `docker-compose.yml` (сервис `vllm`, `profiles: [vllm]`, параметры спеки §5.2, том `hf_cache` под снапшот модели, сеть та же, что у runner; runner не зависит от `vllm`)
- Modify: `content/50-llm/section.md` (глава 6: длинный промпт, vLLM, SGLang с цифрами спайка §7.1, таблица вывода)
- Test: `runner/tests/test_vllm_probe.py`

**Interfaces:**
- Consumes: `llama.serve(extra=…)` (флаги из ответа на вопрос 5), `run_http`.
- Produces: `vllm` харнесс: `probe(url, timeout_s=2) -> "absent" | "loading" | "ready"`; блоки `llm-long-prompt` (`series`: межтокенное время коротких по времени, длинный промпт в момент t=2 с; с флагами по умолчанию и с chunked prefill), `llm-vllm` (`series` той же смеси, что в главе 4, или одна точка-сообщение).

- [ ] **Step 1: Write the failing test** `test_vllm_probe_states`: адрес без сервера → `"absent"`; локальный stdlib-сервер, отвечающий 503 на `/health` → `"loading"`; 200 на `/health` и `/v1/models` → `"ready"`. Харнесс в состоянии `absent`/`loading` печатает в stderr инструкцию (`docker compose --profile vllm up -d vllm`, AVX-512, остановить Triton) и выходит с понятной ошибкой.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement**; живой прогон vLLM-блока руками с `docker compose --profile vllm up -d vllm` (bf16 на машине разработки), числа — в спеку §7.x. Содержательная проверка vLLM-блока в `verify-content` — только ветка «не запущен» (спека §6).
- [ ] **Step 4: Тексты главы 6**; убедиться, что каждое число раздела есть в §7.x.
- [ ] **Step 5: Run** `make test` и `make verify-content` — Expected: всё зелёное.
- [ ] **Step 6: Commit** `feat(content): long prompt, vLLM and conclusion chapter`.

### Task 10: Документация

**Files:**
- Modify: `README.txt` (рост образа runner; профиль `vllm`: когда запускать — AVX-512 и ≥ 12 ГБ у Docker, остановить Triton)
- Modify: спека (§7.x калибровочная таблица полная; отклонения реализации)
- Create: `docs/superpowers/checklists/2026-11-08-llm-firefox-check.md` (навигация, карточка на главной, ссылка из раздела 40, каждый блок раздела 50 — что нажать и что увидеть)

- [ ] **Step 1:** Написать документы.
- [ ] **Step 2: Run** `make test` — Expected: PASS.
- [ ] **Step 3: Commit** `docs: LLM section calibration, README and Firefox checklist`.
