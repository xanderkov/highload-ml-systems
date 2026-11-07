# Своя айдентика курса: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать из курса всё наследие CPU-курса, переименовать курс в «Высоконагруженные ML/DL системы» и перевести веб на новый дизайн (Tailwind v4, светлая тема, три колонки).

**Architecture:** Сначала удаление (контент → web → runner) с зелёными тестами после каждого шага, затем ребрендинг текстов, затем сборка Tailwind в стадии `vendor` образа `web` с новыми шаблонами каркаса, и после этого — перевод JS-блоков на утилиты по одному блоку за задачу.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, markdown-it-py, vanilla JS (ES-модули), Tailwind CSS v4 + `@tailwindcss/typography`, fontsource (Inter, JetBrains Mono), uPlot, Ace, KaTeX, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-11-07-own-identity-design.md`

## Global Constraints

- Название курса: «Высоконагруженные ML/DL системы»; подзаголовок «Почему мы используем Triton». Тексты на русском, код и идентификаторы на английском.
- Удаляется только то, на что после grep по `content/20-*`, `content/30-*`, `web/`, `runner/`, `scripts/`, `Makefile`, `docker-compose.yml`, `README.txt` не ссылается ничего живое.
- Содержание разделов 20 и 30 не меняется, кроме введения раздела 20 (задача 3) и поля `summary` во фронтматтере.
- Каталоги разделов не переименовываются.
- Tailwind: `tailwindcss@4`, `@tailwindcss/cli@4`, `@tailwindcss/typography@0.5`, `@fontsource-variable/inter@5`, `@fontsource/jetbrains-mono@5` — в стадии `vendor`, как остальной вендор. Страница не грузит ничего из внешней сети.
- Имена утилит в JS, Python и шаблонах — только полными строковыми литералами; склейка вида `"bg-" + x` или `` `text-${x}` `` запрещена. Состояния — словари полных имён.
- Составные повторяющиеся элементы (карточка блока, кнопка, callout, бейдж статуса) — классы в `@layer components` в `web/static/src/app.css`; всё остальное — утилиты в разметке.
- Сохраняются все `data-*` атрибуты, на которые опираются JS и тесты: `data-kind`, `data-id`, `data-lang`, `data-params`, `data-part`, `data-exercises`, `data-section`.
- Токены цветов (светлая / тёмная):
  `page #ffffff / #0b1020`, `surface #f8fafc / #111827`, `line #e2e8f0 / #1f2937`, `ink #0f172a / #e5e7eb`, `muted #64748b / #94a3b8`, `accent #4f46e5 / #818cf8`, `good #16a34a / #4ade80`, `bad #dc2626 / #f87171`, `warn #d97706 / #fbbf24`;
  серии графиков `series-1..5`: светлая `#4f46e5 #0d9488 #ea580c #db2777 #64748b`, тёмная `#818cf8 #2dd4bf #fb923c #f472b6 #94a3b8`.
- Тёмная тема — только по `prefers-color-scheme: dark`; ручного переключателя нет.
- Брейкпоинты каркаса: правая колонка видна от 1200px, левая — от 860px; ниже 860px левая — выдвижная панель по кнопке «☰».
- Тесты: `make test`, `make verify-content`; фокусно `docker compose run --rm --build web python -m pytest -q -k <expr>` / `... runner ...`. Браузера нет: JS проверяется в Node с linkedom скриптами в scratchpad (не коммитятся); визуально — автор в Firefox.
- Сообщения коммитов заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Параллельно в той же ветке может идти раздел 30 (план `2026-11-01-naive-service-section.md`): перед каждой задачей `git pull`/rebase не нужен, но при конфликте в `section.md` раздела 30 его текст не трогать.

## Review Focus

1. **Утилита, собранная склейкой строк, не попала в CSS** — элемент без стиля, а тест страниц зелёный. Тест `test_no_dynamic_utility_fragments` в задаче 4.
2. **`localStorage` недоступен (приватное окно Firefox)** — навигация и главная должны отрисоваться без счётчиков, без исключений в консоли. Node-проверка с бросающим `localStorage` в задаче 5.
3. **Раздел без заданий** (раздел 30 сейчас) — в навигации и на карточке главной нет «0 из 0». Тест `test_nav_hides_progress_without_exercises` в задаче 5.
4. **Узкий экран 390px с длинной строкой кода или широкой таблицей** — нет горизонтальной прокрутки страницы, прокручивается только блок. Центральная колонка грида получает `min-w-0`; широкие `pre`/`table` — `overflow-x-auto`. Пункт чек-листа Firefox и тест `test_center_column_can_shrink` в задаче 4.
5. **Переход по якорю `#part-3` на мобильном** — заголовок не прячется под верхней полосой: у заголовков `scroll-mt-20`. Тест `test_headings_have_scroll_margin` в задаче 4.

---

### Task 1: Удалить раздел CPU-кэша, блок `experiment` и их фронтенд

**Files:**
- Delete: `content/01-cpu-cache/`, `TODO.md`, `docs/design/`, `docs/cache-info.md`
- Delete: все `web/static/viz/*.js`, кроме `cow-pages.js` и `pymalloc-arenas.js`
- Delete: `web/static/blocks/index-tutorial.js`, `web/static/blocks/experiment.js`, `web/app/experiments.py`
- Modify: `web/static/blocks/exercise.js` (убрать `mountIndexTutorial` и ветку, которая его вызывает), `web/app/render.py` (`BLOCK_KINDS` без `experiment`, ветка `kind == "experiment"`), `web/app/jobs.py` (ветка `experiment`, допустимые kind), `web/app/main.py` (`RunRequest.variant` и всё, что его использует)
- Modify: `scripts/smoke.sh` (URL по умолчанию `http://localhost:18080/section/python-runtime`)
- Test: `web/tests/test_content.py`, `test_render.py`, `test_api_run.py`, `test_pages.py`, `test_content_targets.py`

**Interfaces:**
- Produces: в вебе остаются типы блоков `viz`, `benchmark`, `exercise`; модули viz — `cow-pages`, `pymalloc-arenas` (плюс `batch-queue`, если раздел 30 его уже добавил).

- [ ] **Step 1:** grep каждого удаляемого имени модуля viz и `index-tutorial`/`experiment` по `content/20-*`, `content/30-*`, `web/` — убедиться, что ссылки только из удаляемого.
- [ ] **Step 2:** Тесты, использующие `cpu-cache`/C-фикстуры как пример общего механизма, перевести на вымышленный раздел с Python-харнессом (`lang: python`, `kind: ab` или `series`); тесты, проверяющие только удаляемое (`experiment`, `index-tutorial`), удалить. В `test_pages.py` список ассетов — без `style.css`-проверки пока не трогать, без `blocks/index-tutorial.js`.
- [ ] **Step 3:** Удалить файлы и ветки кода из списка.
- [ ] **Step 4:** Run `make test-web && make verify-content` → PASS; `grep -rn "cpu-cache\|index-tutorial\|experiments\b" web scripts` → пусто.
- [ ] **Step 5: Commit** `refactor: drop CPU cache section and experiment block`

### Task 2: Удалить C, `sweep` и `cache-info` из платформы

**Files:**
- Delete: `runner/app/build.py`, `runner/app/cache_info.py`, `runner/tests/test_build.py`, `test_cache_info.py`, `test_jobs_c.py`, `test_jobs_sweep.py`, `test_matrix_asm.py`, фикстуры `runner/tests/fixtures/harness/{sumtest,sweeptest,broken_bench}`, `scripts/cache-info.py`, `scripts/bench-asm.sh`
- Modify: `runner/app/jobs.py` (`SUPPORTED_LANGS = {"python"}`, `SUPPORTED_KINDS = {"ab", "series"}`, убрать `defines`, ветку `build_c`, `compile_command` из ответа), `runner/app/main.py` (эндпоинт `/cache-info`), `runner/Dockerfile` (`build-essential` — удалить, если `pip install` без него проходит)
- Modify: `web/app/main.py` (`/api/cache-info`), `web/app/render.py` (`EXT` только `python`; ветки `sweep`), `web/app/jobs.py` (ветка sweep), `web/static/blocks/benchmark.js` (ветка sweep и комментарий про лестницу кэша), `web/static/result.js` (статусы `compile_error`/`compile_timeout`, `renderCompileCommand`), `web/static/blocks/exercise.js` (подсветка строки `compile_error`, вызов `renderCompileCommand`), `web/Dockerfile` (`mode-c_cpp.js`)
- Modify: `docker-compose.yml` (том `./.runtime:/host-info`; у tmpfs `/work` убрать `exec` и комментарий про бинарники), `Makefile` (шаг `python3 scripts/cache-info.py` в `up`), `.gitignore` (`.runtime`, если есть)
- Create: `scripts/check-legacy.sh`

**Interfaces:**
- Produces: runner принимает только `lang: python`, харнессы `ab` и `series`; ответ runner'а не содержит `compile_command`. Цель `make test-repo` (входит в `make test`).

- [ ] **Step 1: Ограждение.** `scripts/check-legacy.sh`: `grep -rnE 'cpu-cache|cache-info|cache_info|bench\.c|\bsweep\b|build_c|compile_command'` по `web/app web/static runner/app runner/tests scripts Makefile docker-compose.yml README.txt`, с `--exclude-dir=vendor --exclude=check-legacy.sh`; найдено что-то — печатает строки и `exit 1`, иначе `exit 0`. Контейнеры не нужны: репозиторий целиком виден только с хоста. В `Makefile`: `test-repo: ; ./scripts/check-legacy.sh`, `test: test-repo test-web test-runner`.

- [ ] **Step 2:** Run `make test-repo` → FAIL (список попаданий).
- [ ] **Step 3:** Удалить и изменить файлы из списка. Из README здесь убрать только абзац про `.runtime`; остальное перепишет задача 3.
- [ ] **Step 4:** Run `make test-repo && make test && make verify-content` → PASS. Если `verify-content` падает из-за tmpfs без `exec` — вернуть `exec` с комментарием, что именно его требует.
- [ ] **Step 5: Commit** `refactor: drop C toolchain, sweep harness and cache-info`

### Task 3: Ребрендинг и введение курса

**Files:**
- Modify: `web/app/content.py` (`Section.summary: str | None`, из фронтматтера `summary`, необязательное), `web/app/main.py` (`FastAPI(title=...)`), `web/app/templates/base.html` (`<title>` по умолчанию, `.site-home`)
- Modify: `content/20-python-runtime/section.md` (фронтматтер `summary`, введение), `content/30-naive-service/section.md` (только фронтматтер `summary`)
- Rewrite: `README.txt`
- Test: `web/tests/test_content.py`, `web/tests/test_pages.py`

**Interfaces:**
- Produces: `Section.summary: str | None`; строка `COURSE_TITLE = "Высоконагруженные ML/DL системы"` и `COURSE_SUBTITLE = "Почему мы используем Triton"` в `web/app/main.py`, передаются во все шаблоны через context processor (рядом с `asset_prefix`).

- [ ] **Step 1: Тесты**

```python
def test_summary_is_optional(tmp_path):  # без summary → None, с summary → строка
def test_pages_use_course_title(client):
    html = client.get("/").text
    assert "Высоконагруженные ML/DL системы" in html and "Почему мы используем Triton" in html
    assert "Оптимизация" not in client.get("/section/python-runtime").text
```

- [ ] **Step 2:** Run фокусно → FAIL. **Step 3:** реализация.
- [ ] **Step 4:** Введение раздела 20 (текст до `## 0.`): 2–3 абзаца — курс о том, почему сервис с моделью на Python упирается в рантайм и как Triton снимает эти боли; путь курса: рантайм Python → наивный сервис и свой батчер → Triton → LLM-сервинг; принцип «сначала замеряем боль, потом чиним»; без ссылок на CPU-кэш и без чисел. `summary` раздела 20: «Почему воркеры копируют память, RSS не падает и потоки не помогают»; раздела 30: «Сервис под нагрузкой: где теряется время и зачем батчить».
- [ ] **Step 5:** README: название и подзаголовок, запуск (`docker compose up --build`, порт 18080, `COURSE_PORT`), требования (Docker, ≥ 4 ГиБ памяти, ≥ 4 CPU для заданий разделов 20 и 30, CPU-сборка PyTorch увеличивает первую сборку), остановка; без `cpu-course`, GCC, NumPy/Numba-фразы про установку, `.runtime`.
- [ ] **Step 6:** Run `make test-repo && make test && make verify-content` → PASS.
- [ ] **Step 7: Commit** `feat: course title, intro and README of its own`

### Task 4: Сборка Tailwind, токены, шрифты, каркас из трёх колонок

**Files:**
- Create: `web/static/src/app.css` (`@import "tailwindcss"`, `@plugin "@tailwindcss/typography"`, `@source` на `../../app/templates`, `../../app/render.py`, `../` (JS); `@theme` с токенами из Global Constraints и `--font-sans: "Inter Variable", system-ui, sans-serif`, `--font-mono: "JetBrains Mono", ui-monospace, monospace`; переопределение токенов в `@media (prefers-color-scheme: dark) { :root { ... } }`; `@layer components` — пока только `.btn`, `.btn-primary`, `.card`; переопределения Ace/uPlot/KaTeX — в задачах 6–8)
- Modify: `web/Dockerfile` (в стадии `vendor`: установка пакетов из Global Constraints; `COPY app /vendor/web/app` и `COPY static /vendor/web/static`; `npx @tailwindcss/cli -i web/static/src/app.css -o /out/app.css --minify`; шрифт Inter в `/out/fonts/inter`; в финальной стадии `COPY --from=vendor /out/app.css /app/static/app.css` **после** `COPY . .`)
- Modify: `.gitignore` (`web/static/app.css`), `web/app/main.py` (`asset_version` уже включает `.css` в корне static — проверить, что `src/` не ломает хеш)
- Rewrite: `web/app/templates/base.html`, `section.html`, `index.html` (каркас; главная получает финальный вид в задаче 5)
- Delete: `web/static/style.css`
- Test: `web/tests/test_pages.py`, `web/tests/test_tailwind.py`

**Interfaces:**
- Produces: каркас `base.html` с блоками Jinja `sidebar`, `content`, `aside`; корневой грид `<div class="xl:grid-cols-[260px_minmax(0,1fr)_220px] ...">` (на 860–1199px — `md2:grid-cols-[260px_minmax(0,1fr)]` через кастомный брейкпоинт `--breakpoint-md2: 860px`, `--breakpoint-xl: 1200px` в `@theme`); центральная колонка `min-w-0`; левая панель `<nav id="course-nav" data-drawer>`; кнопка `<button data-drawer-toggle aria-controls="course-nav" aria-expanded="false">☰</button>` в верхней полосе (видна < 860px); правая `<nav id="page-toc">`; заголовки статьи `scroll-mt-20` (в `render.py` при рендере `h2`/`h3`).
- Produces: `/static/app.css` (через `asset_prefix`) вместо `style.css`.

- [ ] **Step 1: Тесты**

```python
def test_app_css_contains_layout_utility(client):
    css = client.get(f"{ASSET_PREFIX}/app.css").text.replace("\\", "")
    assert "xl:grid-cols-[260px_minmax(0,1fr)_220px]" in css   # ловит сломанный @source

def test_no_dynamic_utility_fragments():
    pattern = re.compile(r"""["'`](?:bg|text|border|ring|grid-cols|w|h|p|m)-["'`]\s*\+|\b(?:bg|text|border|ring)-\$\{""")
    files = [*STATIC.rglob("*.js"), APP / "render.py"]
    assert [str(f) for f in files if "vendor" not in f.parts and pattern.search(f.read_text())] == []

def test_center_column_can_shrink(client):
    assert 'class="min-w-0' in client.get("/section/python-runtime").text

def test_headings_have_scroll_margin(client):
    html = client.get("/section/python-runtime").text
    assert re.search(r'<h2[^>]*id="part-1"[^>]*class="[^"]*scroll-mt-20', html) or re.search(r'<h2[^>]*class="[^"]*scroll-mt-20[^"]*"[^>]*id="part-1"', html)

def test_no_external_urls(client):  # страница не тянет ресурсы из сети
    assert not re.search(r'(src|href)="https?://', client.get("/section/python-runtime").text)
```

- [ ] **Step 2:** Run `docker compose run --rm --build web python -m pytest -q tests/test_tailwind.py tests/test_pages.py` → FAIL.
- [ ] **Step 3:** Реализация сборки и шаблонов. Левая и правая колонки пока статичны (список разделов и частей из шаблона), поведение — задача 5.
- [ ] **Step 4:** Run тот же набор → PASS; `make test-web` → PASS (старые тесты, опиравшиеся на классы `style.css`, обновить под новую разметку, сохранив их смысл).
- [ ] **Step 5:** Попросить автора открыть раздел 20 в Firefox на 1400/1000/390px, светлая и тёмная тема; блоки ещё в старом виде (без стилей) — это ожидаемо. Замечания по каркасу — исправить до коммита.
- [ ] **Step 6: Commit** `feat(web): Tailwind build, tokens and three-column layout`

### Task 5: Навигация: прогресс, «На этой странице», выдвижная панель, главная

**Files:**
- Modify: `web/static/progress.js`, `web/static/app.js` (или Create: `web/static/nav.js`, импортируется из `app.js`)
- Modify: `web/app/main.py` (контекст навигации для всех страниц), `web/app/render.py` (`section_outline` — подзаголовки `h3`)
- Modify: `web/app/templates/base.html`, `section.html`, `index.html`
- Test: `web/tests/test_pages.py`, `web/tests/test_render.py`

**Interfaces:**
- Consumes: каркас и `data-drawer*` из задачи 4; `Section.summary`, `COURSE_TITLE/SUBTITLE` из задачи 3.
- Produces:
  - `progress.js`: `doneCount(sectionId: string, blockIds: string[]) -> number` (через существующий `read()`, без исключений при недоступном `localStorage`);
  - `section_outline(section) -> list[dict]`: у каждой части добавляется `"subs": [{"id": str, "title": str}]` для `h3` (якоря — те же, что ставит `render_section`);
  - контекст шаблонов `course_nav: list[dict]` — `{"id", "title", "summary", "exercises": list[str], "parts": section_outline(...)}` для каждого не-черновика;
  - разметка: левая навигация — `<li data-section-nav="{id}" data-exercises="a,b">` со счётчиком `<span data-progress hidden>`; правая — ссылки `<a data-toc-link href="#part-N">`; карточка главной — `<a data-section-card="{id}" data-exercises="...">` со счётчиком `<span data-progress hidden>`.
  - Поведение JS: счётчик «N из M» показывается, только если `M > 0`; у пройденного раздела — галочка; текущая часть в правой колонке получает `aria-current="true"` (IntersectionObserver по `h2`/`h3`, `rootMargin: "-80px 0px -70% 0px"`); кнопка `☰` переключает `data-open` у панели и `aria-expanded`, `Esc` и клик по ссылке закрывают.
  - Главная: заголовок, подзаголовок, абзац о курсе (замер → боль → решение → Triton), карточки разделов (номер `01`, `02`… по позиции, название, `summary`, прогресс), затем две карточки «скоро» без ссылок: «Triton Inference Server», «LLM-сервинг».

- [ ] **Step 1: Тесты (pytest)**

```python
def test_outline_has_subheadings(): ...      # часть с «### Арены, пулы и блоки» → subs содержит этот заголовок и его якорь
def test_nav_lists_all_sections_with_exercises(client):  # data-section-nav="python-runtime" с непустым data-exercises
def test_nav_hides_progress_without_exercises(client):   # для раздела без заданий нет data-exercises и нет data-progress
def test_home_has_soon_cards(client):        # «Triton Inference Server» и «LLM-сервинг» присутствуют и не являются ссылками
```

- [ ] **Step 2:** Run фокусно → FAIL. **Step 3:** реализация.
- [ ] **Step 4:** Node-проверка (scratchpad, linkedom): отрендерить HTML главной и раздела из TestClient в файл, загрузить, подменить `localStorage` на (а) объект с прогрессом одного задания — счётчик «1 из 3», (б) геттер, бросающий `SecurityError` — счётчики скрыты, исключений нет; `☰` меняет `aria-expanded`.
- [ ] **Step 5:** Run `make test-web` → PASS.
- [ ] **Step 6: Commit** `feat(web): course navigation, page toc and home page`

### Task 6: Блок задания и результаты

**Files:**
- Modify: `web/static/blocks/exercise.js`, `web/static/result.js`, `web/static/src/app.css` (`@layer components`: `.block-card`, `.block-head`, `.status-badge`; переопределения Ace: фон `surface`, шрифт mono)
- Create: `web/static/theme.js`

**Interfaces:**
- Produces (`theme.js`): `aceTheme() -> "ace/theme/github" | "ace/theme/github_dark"` по `matchMedia("(prefers-color-scheme: dark)")`; `cssVar(name: string) -> string` (`getComputedStyle(document.documentElement)`); `chartColors() -> {series: string[5], grid: string, axis: string}` из `--color-series-1..5`, `--color-line`, `--color-muted`.
- Вид (спека §4.5): карточка с шапкой «Задание N» и бейджем статуса; кнопка «Запустить» `.btn-primary`, во время запуска — спиннер и «Выполняется…», кнопка `disabled`; зачтено — рамка `good`, метрика `text-4xl font-mono`, цель рядом; не зачтено — нейтральная рамка, метрика, цель, диагностика харнесса; ошибка — рамка `bad`, трассировка в `pre` с `overflow-x-auto max-h-96`. Классы состояний — словарь `{pass: "...", fail: "...", error: "..."}`.

- [ ] **Step 1:** Реализация; все существующие тексты и логика результата (`statusLabel`, плюралы) не меняются — только разметка и классы.
- [ ] **Step 2:** Node-проверка: смонтировать блок задания на заглушке DOM с фиктивным `run`, прогнать три ответа (зачтено / не зачтено / `runtime_error`) — нужные узлы и классы рамки на месте, `markDone` вызван только при зачёте.
- [ ] **Step 3:** Run `make test-web` → PASS (включая `test_no_dynamic_utility_fragments`).
- [ ] **Step 4: Commit** `feat(web): exercise block in the new design`

### Task 7: Замеры и графики

**Files:**
- Modify: `web/static/blocks/benchmark.js`, `web/static/blocks/comparison.js`, `web/static/src/app.css` (переопределения uPlot: шрифт подписей, легенда)

**Interfaces:**
- Consumes: `chartColors()`, `cssVar()` из задачи 6.
- Вид: карточка «Замер» как у задания; цвета серий, сетки и осей uPlot — из `chartColors()` при монтировании (первая серия — акцент); таблица сравнения — `font-mono tabular-nums`, обёртка `overflow-x-auto`.

- [ ] **Step 1:** Реализация.
- [ ] **Step 2:** Node-проверка: смонтировать `benchmark` для `series`-ответа с тремя линиями на заглушке `uPlot` — конструктор получил `stroke` из `chartColors().series` по порядку.
- [ ] **Step 3:** Run `make test-web && make verify-content` → PASS.
- [ ] **Step 4: Commit** `feat(web): benchmark and charts in the new design`

### Task 8: Проза, выноски, viz и финальная проверка

**Files:**
- Modify: `web/app/render.py` (статья в `prose prose-slate dark:prose-invert max-w-none`; `heading-link` видна при наведении на заголовок), `web/static/src/app.css` (`.callout` и `.callout-note/-tip/-important/-warning/-caution` — фон `surface`, полоса 3px слева: акцент / good / accent / warn / bad; KaTeX — цвет `ink`), `web/static/app.js` (кнопка «копировать» у `article pre` вне блоков)
- Modify: `web/static/viz/cow-pages.js`, `web/static/viz/pymalloc-arenas.js` (цвета только через `cssVar`/CSS-переменные; логика не меняется)
- Create: `docs/superpowers/checklists/2026-11-07-firefox-check.md`

**Interfaces:**
- Consumes: `cssVar()` из задачи 6.

- [ ] **Step 1:** Реализация. Классы callout формирует `render.py` как сейчас (`callout-{kind}`) — они определены в `@layer components`, поэтому сборке не нужно их находить; тест `test_no_dynamic_utility_fragments` их не ловит (это не утилиты) — проверить, что тест проходит.
- [ ] **Step 2:** Node-проверка viz: оба модуля монтируются без исключений, в SVG нет зашитых цветов `#rrggbb` (только `var(--color-…)`).
- [ ] **Step 3:** Чек-лист Firefox: главная; раздел 20 в светлой и тёмной теме; задание — зачтено / не зачтено / ошибка; замер с графиком; viz; ширины 1400 / 1000 / 390px (нет горизонтальной прокрутки, `☰` открывает и закрывает панель); переход по ссылке из правой колонки не прячет заголовок; приватное окно — страница работает без счётчиков.
- [ ] **Step 4:** Run `make test-repo && make test && make verify-content` → PASS. `make smoke` не запускается (нет браузера) — указать в отчёте.
- [ ] **Step 5: Commit** `feat(web): prose, callouts and viz in the new design`
- [ ] **Step 6:** Передать автору чек-лист; правки по результатам — отдельными коммитами `fix(web): ...`.
