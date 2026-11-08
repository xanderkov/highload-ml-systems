# Раздел «Triton» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** раздел `content/40-triton/`: та же `widemodel` в Triton под той же нагрузкой, замеры глав 0–5, два задания, вывод.

**Architecture:** общий сервис `triton` в compose (CPU, `--model-control-mode=explicit`, `cpuset` 3 CPU) и общий том `model_repo` с runner. Харнессы раздела под файловой блокировкой пишут репозиторий модели, грузят её через HTTP API Triton, гоняют генератор `servicelib` (CPU 0) и выгружают модель.

**Tech Stack:** Triton Inference Server (NGC-образ, python и pytorch_libtorch backend), torch CPU, KServe v2 HTTP + binary tensor extension, существующие runner/web (FastAPI, pytest, Ace).

**Spec:** `docs/superpowers/specs/2026-11-08-triton-section-design.md`

## Global Constraints

- Только CPU; серверу Triton — 3 CPU (`TRITON_CPUS`, по умолчанию `1-3`), генератор — CPU 0 (как `SERVICE_MAX_CPUS = 3` раздела 30).
- Студенческий код не исполняется внутри контейнера Triton: студент пишет только `config.pbtxt` (задание 1) и функцию экспорта (задание 2, исполняется в sandbox runner).
- Генератор — только `servicelib.run_load` / `probe_capacity` (HTTP), без gRPC-клиента.
- Тексты раздела — по-русски, «в нашем замере», никаких утверждений без цифр раздела; в каждой главе: текст → замер → вывод.
- Порт Triton наружу не публикуется; сеть `back` (internal).
- Разделы 20 и 30 работают без изменений; копии `servicelib.py`/`widemodel.py` побайтно равны оригиналам раздела 30.
- Новые CSS-классы — только полными литералами Tailwind (Tailwind ищет их в исходниках).
- Порог задания: эталон ≥ 1,5× порога, стартовый код не проходит (правило раздела 30).
- UI проверяет автор в Firefox; на машине разработки браузера нет.

## Review Focus

- **Triton не поднялся или ещё грузится**, когда студент жмёт «Запустить» — понятное сообщение «сервер Triton недоступен: …», а не трассировка `ConnectionRefused` (тест в задаче 5).
- **Упавший прошлый замер оставил модель загруженной** — следующий замер её выгружает и меряет честно (тест в задаче 5).
- **Битый `config.pbtxt` студента** (синтаксис, неизвестное поле, `max_batch_size: 0` при `dynamic_batching`) — текст ошибки Triton в выводе, а не «модель не готова» (тест в задаче 7).
- **Трассировка с зашитым батчем 1** в задании 2 — сообщение про форму батча, а не «ответы не совпали» (тест в задаче 9).
- **Два задания запущены одновременно** (две вкладки) — второй ждёт блокировку и пишет, что ждёт; ни один не меряет на занятом сервере (тест в задаче 4).

---

### Task 1: Спайк Triton на CPU (результат — запись в спеке, код выбрасывается)

**Files:**
- Modify: `docs/superpowers/specs/2026-11-08-triton-section-design.md` (§7.1 → «Решено» с цифрами)
- Scratch (не коммитится): каталог в scratchpad

- [ ] **Step 1:** Найти свежий тег `nvcr.io/nvidia/tritonserver:<YY.MM>-py3`, вышедший не позже чем ~2 месяца назад; `docker pull`; записать размер образа (`docker images`).
- [ ] **Step 2:** Собрать пробный образ `FROM` этого тега + `pip install --index-url https://download.pytorch.org/whl/cpu torch` (версия как в `runner/Dockerfile`, `~=2.15`, если совместима с Python образа). Записать размер.
- [ ] **Step 3:** Запустить `tritonserver --model-repository=/models --model-control-mode=explicit` с `--cpuset-cpus=1-3`, без GPU. Модель `widemodel` в python backend (`model.py` с `widemodel.make_model()`), `max_batch_size: 32`, `KIND_CPU`. Load через `POST /v2/repository/models/<n>/load`, один инференс через binary extension. Записать время старта сервера и загрузки модели.
- [ ] **Step 4:** То же для `platform: "pytorch_libtorch"` с `torch.jit.trace` от `widemodel` (вход `INPUT__0`, выход `OUTPUT__0`). Проверить совпадение выходов с eager (`allclose`, 1e-4).
- [ ] **Step 5:** 50 циклов load → 100 запросов → unload с разными конфигами (батчинг вкл/выкл, 1/3 экземпляра): RSS сервера (`docker stats`) не растёт неограниченно, ответы корректны, состояние прошлого конфига не видно (`/v2/models/<n>/config` отражает новый).
- [ ] **Step 6:** `curl :8002/metrics`: есть ли `nv_cpu_utilization` (или аналог) на CPU-only; какие счётчики по модели есть (`nv_inference_queue_duration_us`, `nv_inference_compute_infer_duration_us`, `nv_inference_exec_count`, `nv_inference_request_success`, `nv_inference_request_failure`).
- [ ] **Step 7:** Проверить, что python backend уважает переменные окружения/`parameters` для числа потоков torch на экземпляр (например, `torch.set_num_threads` в `initialize` по параметру `TORCH_THREADS` из `config.pbtxt`) — нужно главе 3.
- [ ] **Step 8:** Записать в спеку §7.1: тег, размеры, времена, CPU-метрика есть/нет, чистота load/unload (если не чисто — решение «вариант B» и правка §3, после чего остановиться и согласовать с автором), имя параметра потоков. Commit:

```bash
git add docs/superpowers/specs/2026-11-08-triton-section-design.md
git commit -m "docs: Triton CPU spike results"
```

### Task 2: Сервис `triton` в compose и общий том

**Files:**
- Create: `triton/Dockerfile`, `triton/.dockerignore`
- Modify: `docker-compose.yml`, `runner/Dockerfile`, `Makefile`, `runner/pytest.ini`
- Test: `runner/tests/test_triton_service.py`

**Interfaces:**
- Produces: хост `triton` (HTTP 8000, метрики 8002) в сети `back`; том `model_repo`, смонтированный в `triton:/models:ro` и `runner:/models` (rw, владелец UID 10001); маркер pytest `triton`; цель `make test-triton`.

- [ ] **Step 1: Тест** `test_triton_is_live` (маркер `triton`): `GET http://triton:8000/v2/health/live` → 200; `test_model_repo_writable`: файл в `/models` создаётся и удаляется под пользователем runner.
- [ ] **Step 2:** `make test-triton` падает (сервиса нет).
- [ ] **Step 3:** `triton/Dockerfile` — тег и установка torch из задачи 1; `CMD tritonserver --model-repository=/models --model-control-mode=explicit`. Compose: сервис `triton` (`build: ./triton`, `cpuset: "${TRITON_CPUS:-1-3}"`, `mem_limit: 4g`, `networks: [back]`, healthcheck `curl -sf localhost:8000/v2/health/live`, том `model_repo:/models:ro`), у `runner` — `model_repo:/models` и `depends_on: triton: {condition: service_healthy}`. В `runner/Dockerfile` до `USER bench`: `mkdir /models && chown bench:bench /models` (именованный том при первом монтировании наследует владельца). `runner/pytest.ini`: маркер `triton`, `addopts = -m "not triton"`. Makefile: `test-triton: docker compose run --rm --build runner python -m pytest -q -m triton`, добавить в `verify-content` зависимость.
- [ ] **Step 4:** `make test-triton` — PASS; `make test-runner` — по-прежнему зелёный (тесты `triton` исключены).
- [ ] **Step 5:** Commit `feat(infra): Triton service and shared model repository`.

### Task 3: Runner и web: язык `pbtxt` и лимит файла из meta

**Files:**
- Modify: `runner/app/jobs.py` (`SUPPORTED_LANGS`, `_prepare_python`, вызов `run`), `runner/app/sandbox.py` (параметр `max_file_mb`), `web/app/render.py` (`EXT`), `web/static/blocks/exercise.js` (режим Ace по `lang`), `web/Dockerfile` (`mode-protobuf.js`)
- Test: `runner/tests/test_jobs_python.py`, `runner/tests/test_sandbox.py`, `web/tests/test_render.py`

**Interfaces:**
- Produces: блок с `lang=pbtxt` — юниты пишутся как `unit_a.pbtxt`/`unit_b.pbtxt` рядом с `bench.py` (харнесс — Python, как обычно); `meta.yml: max_file_mb: <int>` (по умолчанию 64) задаёт `RLIMIT_FSIZE`; `run(..., max_file_mb: int = MAX_FILE_MB)`.

- [ ] **Step 1: Тесты:** `test_pbtxt_units_written_as_text_files` — job с `lang: "pbtxt"` и фикстурным харнессом, который печатает содержимое `unit_b.pbtxt`, возвращает его; `test_unknown_lang_still_rejected` (`lang: "c"` → `unsupported_lang`); `test_max_file_mb_from_meta` — харнесс пишет 100 МиБ при `max_file_mb: 128` успешно и падает при умолчании; `test_render_pbtxt_block` — `EXT["pbtxt"] == "pbtxt"`, блок рендерится с `data-lang="pbtxt"`.
- [ ] **Step 2:** Запуск — FAIL.
- [ ] **Step 3:** Реализация: расширение файла юнита по `lang` (`{"python": "py", "pbtxt": "pbtxt"}`), `max_file_mb` из meta в `run`; в `exercise.js` `mode: {python: "ace/mode/python", pbtxt: "ace/mode/protobuf"}[lang] || "ace/mode/text"`; `mode-protobuf.js` (и `mode-text` не нужен — встроен) в вендоринг.
- [ ] **Step 4:** `make test-runner && make test-web` — PASS.
- [ ] **Step 5:** Commit `feat(runner): pbtxt exercise units and per-harness file size limit`.

### Task 4: Копии библиотек раздела 30, заголовки в генераторе, чистые части `tritonlib`

**Files:**
- Create: `content/40-triton/harness/_lib/servicelib.py`, `content/40-triton/harness/_lib/widemodel.py` (копии), `content/40-triton/harness/_lib/tritonlib.py`
- Modify: `content/30-naive-service/harness/_lib/servicelib.py` (параметр `headers`)
- Test: `runner/tests/test_servicelib.py`, `runner/tests/test_tritonlib.py`, `web/tests/test_content.py` (копии)

**Interfaces:**
- Produces:
  - `servicelib.run_load(..., headers: dict[str, str] | None = None)` и `probe_capacity(..., headers=None)` — доп. заголовки в каждом запросе; без них байты запроса прежние.
  - `tritonlib.v2_body(array: np.ndarray, *, binary: bool = True, input_name: str = "INPUT__0", output_name: str = "OUTPUT__0") -> tuple[bytes, dict[str, str]]` — тело и заголовки (`Inference-Header-Content-Length` для binary; JSON — `{"inputs":[{"name","shape","datatype":"FP32","data"}]}`); `content_type` для `run_load` — `"application/octet-stream"` (binary) или `"application/json"`.
  - `tritonlib.parse_v2_response(raw: bytes, header_length: int | None) -> np.ndarray` — первый выход как float32 нужной формы; `header_length` из заголовка ответа `Inference-Header-Content-Length` (для этого `LoadResult.responses` в servicelib должны хранить его — добавить `response_headers: list[dict | None]` в `LoadResult`, по умолчанию пустой список).
  - `tritonlib.parse_metrics(text: str, model: str) -> dict[str, float]` — сумма по версиям для `queue_us`, `compute_us`, `exec_count`, `request_success`, `request_failure` (+ `cpu_util`, если задача 1 нашла метрику); `metrics_delta(before, after) -> dict` и `mean_batch(delta) -> float = request_success / exec_count`.
  - `tritonlib.server_lock(timeout_s: float = 120) -> ContextManager[None]` — `fcntl.flock` на `/models/.lock`; если не взят сразу — печатает в stderr «сервер Triton занят другим замером, ждём…»; по таймауту — `TritonBusy`.

- [ ] **Step 1: Тесты:** `test_v2_body_binary_roundtrip` — тело для `(2,3,64,64)` разбирается так же, как это сделал бы Triton (JSON-заголовок длины из заголовка + сырые байты = `array.tobytes()`); `test_parse_v2_response_binary_and_json`; `test_parse_metrics_sums_versions_and_ignores_other_models` (фикстура — текст Prometheus из задачи 1); `test_mean_batch`; `test_server_lock_second_holder_waits` (два процесса, второй ждёт, пишет в stderr, получает после освобождения; путь блокировки — параметр для теста); `test_run_load_sends_extra_headers` (фикстурный сервис эхом возвращает заголовок); `test_section40_lib_copies_match_section30` — `servicelib.py`, `widemodel.py` побайтно равны.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Реализация; правка `servicelib` вносится в раздел 30 и копируется в 40.
- [ ] **Step 4:** `make test-runner && make test-web` — PASS; `make verify-content` раздела 30 — без изменений результатов.
- [ ] **Step 5:** Commit `feat(content): tritonlib protocol, metrics and server lock`.

### Task 5: `deploy` и модель python backend

**Files:**
- Modify: `content/40-triton/harness/_lib/tritonlib.py`
- Create: `content/40-triton/harness/_lib/triton_model.py` (это `model.py` python backend; копируется в репозиторий как `<n>/1/model.py` вместе с `widemodel.py`)
- Test: `runner/tests/test_tritonlib_live.py` (маркер `triton`)

**Interfaces:**
- Consumes: `server_lock`, `v2_body`, `parse_v2_response` (задача 4).
- Produces:
  - `TRITON_URL = "http://triton:8000"`, `METRICS_URL = "http://triton:8002/metrics"`, `REPO = Path("/models")`.
  - `class TritonUnavailable(RuntimeError)`, `class TritonLoadError(RuntimeError)` (текст — сообщение Triton из ответа load).
  - `deploy(name: str, config: str, files: dict[str, bytes]) -> ContextManager[str]` — вызывать под `server_lock`; выгружает все загруженные модели (`POST /v2/repository/index`), пишет `REPO/name/config.pbtxt` и `files` (пути относительно `REPO/name`), load, ждёт `/v2/models/<name>/ready` (≤ 60 с), отдаёт URL сервера; в `finally` — unload и удаление каталога.
  - `python_model_files() -> dict[str, bytes]` — `{"1/model.py": ..., "1/widemodel.py": ...}`.
  - `unique_name(prefix: str) -> str` — `f"{prefix}-{os.getpid()}-{secrets.token_hex(3)}"`.
  - `triton_model.py`: вход `INPUT__0` FP32 `[3,64,64]`, выход `OUTPUT__0` FP32 `[10]`; `initialize` читает `parameters.TORCH_THREADS` (имя — из задачи 1) и `torch.set_num_threads`; вход, у которого первый элемент `== -1e9` (флаг «битый вход» главы 5), даёт ошибку только этому запросу (`pb_utils.InferenceResponse(error=...)`), остальные — ответ.

- [ ] **Step 1: Тесты (`triton`):** `test_deploy_loads_and_answers` (ответ совпадает с `widemodel` eager, 1e-4); `test_deploy_unloads_on_exit` (после выхода модели нет в index, каталога нет); `test_broken_config_raises_load_error_with_triton_text`; `test_stale_model_unloaded_before_deploy` (загрузить вручную «чужую» модель, `deploy` её выгружает); `test_unavailable_server_message` (URL на несуществующий хост → `TritonUnavailable` с «сервер Triton недоступен»); `test_bad_input_fails_only_its_request` (батч из 4 через dynamic batching, один с флагом).
- [ ] **Step 2:** `make test-triton` — FAIL.
- [ ] **Step 3:** Реализация (HTTP через `urllib.request`, без новых зависимостей).
- [ ] **Step 4:** `make test-triton` — PASS.
- [ ] **Step 5:** Commit `feat(content): deploy models to Triton from harnesses`.

### Task 6: Раздел, глава 0 (крючок) и глава 1 (протокол)

**Files:**
- Create: `content/40-triton/section.md` (фронтматтер `id: triton`, `title: Triton: проверяем обещания замером`, `order: 40`, summary; вступление; главы 0–1), `content/40-triton/snippets/config_minimal.pbtxt`, `content/40-triton/harness/hook/{bench.py,meta.yml}`, `content/40-triton/harness/protocol/{bench.py,meta.yml}`
- Test: `web/tests/test_content_targets.py` (бенчмарки гоняются автоматически параметризацией)

**Interfaces:**
- Consumes: `deploy`, `python_model_files`, `unique_name`, `server_lock`, `v2_body`, `servicelib.run_load/probe_capacity` (headers).
- Produces: `series`-харнессы; формат вывода — как у раздела 30 (`{"lines": [{"name", "points": [{"x","y"}]}]}`).

- [ ] **Step 1:** `hook`: минимальный конфиг (без `dynamic_batching`, 1 экземпляр, `TORCH_THREADS: 3`), ёмкость `probe_capacity`, ступени 0,25/0,5/0,75/0,9 C, C+30, C+60 по 3 с; линии p50, p99 (лог-шкала), средний батч из метрик; рядом — та же сетка на бинарном сервисе батча-из-одного раздела 30 (`service_binary.py` копией сниппета в `snippets/`), чтобы сравнение было на одном графике.
- [ ] **Step 2:** `protocol`: Triton + `dynamic_batching` выключен, одна ступень (0,5 C), три варианта тела: v2 JSON, v2 binary, бинарный сервис раздела 30; линии p50/p99 по вариантам (x — вариант по номеру, подписи в тексте).
- [ ] **Step 3:** Текст глав 0–1 по §4 спеки; числа в тексте — только из прогона харнессов на машине разработки (задача 11 перепроверит их калибровкой).
- [ ] **Step 4:** `make test-web` (раздел рендерится) и `docker compose run --rm --build web python -m pytest -q -m content -k "triton"` — бенчмарки отрабатывают без ошибок.
- [ ] **Step 5:** Commit `feat(content): Triton hook and protocol chapters`.

### Task 7: Глава 2 и задание 1 (`config.pbtxt`)

**Files:**
- Create: `content/40-triton/harness/batching/{bench.py,meta.yml}`, `content/40-triton/harness/config_exercise/{bench.py,meta.yml}`, `content/40-triton/snippets/config_starter.pbtxt`, `content/40-triton/snippets/config_ref.pbtxt`, `content/40-triton/snippets/batcher_ref.py` (копия эталона раздела 30 для сравнения)
- Modify: `content/40-triton/section.md` (глава 2), `web/tests/test_content_targets.py`

**Interfaces:**
- Consumes: всё из задач 4–5; `servicelib.start_service` для батчера раздела 30.
- Produces: блок `exercise id=config-exercise lang=pbtxt`, `target: goodput_ratio >= <порог из калибровки, стартовое значение 2>`, `harness: config_exercise`. Протокол `ab` — как у `batcher_exercise` раздела 30: samples p99, check (все ответы от своих входов), metrics `goodput`, `goodput_ratio`, `mean_batch`.

- [ ] **Step 1: Тесты (`content`):** эталон проходит; стартовый — нет; `test_config_exercise_broken_syntax_shows_triton_error` (ошибка в выводе содержит текст Triton); `test_config_exercise_zero_batch_size` (сообщение про `max_batch_size`); `test_config_exercise_huge_delay_fails_rare_load` (`max_queue_delay_microseconds: 2000000` — сообщение про редкие запросы, как в разделе 30); `test_config_exercise_wrong_io_names` (входы/выходы не `INPUT__0` FP32 [3,64,64] / `OUTPUT__0` FP32 [10] — сообщение с ожидаемыми именами и формами). Поле `name` харнесс всегда заменяет уникальным именем, студенту его менять не нужно.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `batching` (`series`): 700 RPS, SLO 50 мс — goodput, p99 и средний батч для: Triton без батчинга, Triton `dynamic_batching { }`, эталонный батчер раздела 30. `config_exercise`: юнит a/b — конфиги; редкие запросы → прогрев → `REPEATS` прогонов, как `batcher_exercise`. Текст главы 2 и блок задания с подсказками (какие поля, ссылка на документацию `dynamic_batching`).
- [ ] **Step 4:** `make verify-content -k triton` — PASS.
- [ ] **Step 5:** Commit `feat(content): Triton dynamic batching chapter and config exercise`.

### Task 8: Глава 3 — `instance_group` × `max_queue_delay`

**Files:**
- Create: `content/40-triton/harness/instances_delay/{bench.py,meta.yml}`
- Modify: `content/40-triton/section.md` (глава 3)

- [ ] **Step 1:** Харнесс `series`: экземпляров 1/2/3 при `TORCH_THREADS = 3 // экземпляров`, задержка 0/1/2/5/10 мс, нагрузка 100 и 700 RPS по 2 с; линии p99 «N экз., RPS» от задержки. Плюс одна линия «3 экз. × 3 потока» (переподписка CPU) при 700 RPS — показать замером, что произведение больше 3 CPU не бесплатно. Укладывается в `timeout_s` meta (поднять до 240, если нужно; иначе сократить сетку — решить по замеру).
- [ ] **Step 2:** Прогон на машине разработки 3 раза; вывод главы — по фактическому результату (включая «не окупается и здесь»).
- [ ] **Step 3:** Текст главы 3.
- [ ] **Step 4:** `make verify-content -k instances` — PASS.
- [ ] **Step 5:** Commit `feat(content): instances × queue delay chapter`.

### Task 9: Глава 4 и задание 2 (экспорт в libtorch)

**Files:**
- Create: `content/40-triton/harness/libtorch/{bench.py,meta.yml}`, `content/40-triton/harness/export_exercise/{bench.py,meta.yml}`, `content/40-triton/snippets/export_starter.py`, `content/40-triton/snippets/export_ref.py`
- Modify: `content/40-triton/section.md` (глава 4), `web/tests/test_content_targets.py`

**Interfaces:**
- Produces: модуль студента определяет `export(model: torch.nn.Module, path: str) -> None` (сохраняет TorchScript) и строку `CONFIG: str` (конфиг libtorch). Харнесс: вызывает `export(widemodel.make_model(), "/work/.../model.pt")`, проверяет размер ≤ 256 МиБ, кладёт как `1/model.pt`. meta: `kind: ab`, `max_file_mb: 256`, `memory_mb: 3072` (проверить по `mem_limit` runner 3g — если не помещается, поднять `mem_limit` runner до 4g в compose в этой задаче). Стартовый юнит — python backend (без экспорта, `export` в стартовом коде не вызывается: харнесс для юнита a деплоит `python_model_files()`). Метрики: `goodput_ratio` против python backend; check — совпадение ответов (1e-4) на батчах 1, 7 и 32.

- [ ] **Step 1: Тесты (`content`):** эталон проходит; стартовый — нет; `test_export_fixed_batch_trace_reported` (трассировка через `torch.jit.trace` с `strict` и зашитым `view(1, -1)` — сообщение «модель работает только с батчем 1»); `test_export_wrong_io_names` (сообщение про `INPUT__0`/`OUTPUT__0`). Забытый `eval()` не ловится: у `widemodel` нет dropout/batchnorm, ответы совпадают — поэтому он убран из типовых ошибок спеки §4.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `libtorch` (`series`): python vs libtorch при одном конфиге батчинга — p50/p99/goodput на 700 RPS и ёмкость. `export_exercise` по интерфейсу выше. Порог `goodput_ratio` — по калибровке; если libtorch не даёт заметного выигрыша (модель упирается в веса), задание проверяет корректность и «не хуже python backend» (`goodput_ratio >= 0.9`), а текст это объясняет — решение зафиксировать в спеке §7.
- [ ] **Step 4:** `make verify-content -k "libtorch or export"` — PASS.
- [ ] **Step 5:** Commit `feat(content): libtorch chapter and export exercise`.

### Task 10: Глава 5 — пять болей по списку

**Files:**
- Create: `content/40-triton/harness/backpressure/`, `content/40-triton/harness/bad_input/`, `content/40-triton/harness/cancel/`, `content/40-triton/harness/versions/`, `content/40-triton/harness/metrics/` (каждый `bench.py` + `meta.yml`, `kind: series`)
- Modify: `content/40-triton/section.md` (глава 5)

- [ ] **Step 1:** `backpressure`: нагрузка 1,5 C, конфиг без политики и с `default_queue_policy { max_queue_size: <калибровка> timeout_action: REJECT }`; линии: p99 принятых, доля отказов (`errors / sent`).
- [ ] **Step 2:** `bad_input`: 700 RPS, каждый 20-й вход с флагом `-1e9`; линии: доля ошибок среди нормальных и среди битых входов (ожидаем 0 и 1 — показываем то, что намерили).
- [ ] **Step 3:** `cancel`: клиенты, закрывающие соединение через 5 мс после отправки (доп. режим `run_load` не вводим — отдельная корутина в харнессе на asyncio, тело из `v2_body`); линии: `exec`-счётчик и `request_success` из метрик против числа реально дождавшихся ответов. Вывод — по цифрам.
- [ ] **Step 4:** `versions`: модель v1 под 300 RPS; в середине прогона — загрузка v2 (`version_policy: { all {} }`) рядом; линии: p99 по 200-мс окнам и ошибки, отметка момента загрузки.
- [ ] **Step 5:** `metrics`: один прогон 700 RPS; столбцы из `metrics_delta`: среднее время в очереди, вычисления, средний батч — сверка с latency, которую видит клиент.
- [ ] **Step 6:** Текст главы 5; `make verify-content -k "backpressure or bad_input or cancel or versions or metrics"` — PASS.
- [ ] **Step 7:** Commit `feat(content): five pains checked against Triton`.

### Task 11: Глава 6, калибровка, финальная проверка

**Files:**
- Modify: `content/40-triton/section.md` (глава 6, числа во всех главах), `docs/superpowers/specs/2026-11-08-triton-section-design.md` (§7.x — таблица калибровки, как в разделе 30), `content/30-naive-service/section.md` (последний абзац главы 6: ссылка на раздел 40 вместо «в следующем разделе», если формулировка устарела)

- [ ] **Step 1:** Все бенчмарки и задания раздела 40 — 3 прогона на машине разработки; таблица §7.x: блок, что меряли, результат; пороги заданий по правилу «эталон ≥ 1,5× порога».
- [ ] **Step 2:** Глава 6: таблица «боль → снята / частично / руками» строго по цифрам глав 0–5; мост к LLM.
- [ ] **Step 3:** `make test && make verify-content && make test-triton` — всё зелёное; `scripts/smoke.sh` — проходит.
- [ ] **Step 4:** Чек-лист для автора в `docs/superpowers/checklists/2026-11-08-triton-firefox-check.md` по образцу `2026-11-07-firefox-check.md` (раздел в навигации, редактор pbtxt с подсветкой, оба задания, графики глав).
- [ ] **Step 5:** Commit `docs: Triton section calibration and conclusion`.
