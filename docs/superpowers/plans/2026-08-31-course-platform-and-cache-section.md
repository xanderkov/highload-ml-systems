# Платформа курса + раздел «Кэш процессора» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docker compose up` поднимает курс, в котором студент читает раздел про иерархию памяти, запускает бенчмарки на настоящем железе и решает три задания с автоматической проверкой ускорения.

**Architecture:** Два сервиса. `web` (FastAPI) читает Markdown из смонтированной папки `content/`, рендерит страницы и проксирует запуски кода. `runner` (FastAPI) компилирует C и исполняет Python в tmpfs под rlimit'ами и таймаутами, замеряет по A/B-протоколу и возвращает JSON. `runner` живёт во внутренней сети без выхода наружу; harness'ы заданий лежат вместе с контентом и монтируются в оба сервиса.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, markdown-it-py, Jinja2, PyYAML, NumPy, gcc; на фронте — ES-модули без сборщика, Ace (редактор), uPlot (графики), KaTeX (формулы), вендоринг через npm-стадию в Dockerfile.

**Spec:** `docs/superpowers/specs/2026-08-31-inference-course-design.md`

## Global Constraints

- Python 3.12, базовый образ `python:3.12-slim`.
- Тесты гоняются внутри контейнеров: `make test`. Хостовый Python не настраивается.
- Контент на русском; код, идентификаторы, имена файлов — на английском.
- Никаких абсолютных чисел конкретного железа в текстах: размеры кэшей и границы уровней студент получает замером.
- Сборка нативная под архитектуру хоста. Никакого `platform: linux/amd64` в compose — эмуляция QEMU уничтожает замеры.
- `runner` не имеет выхода в интернет (`internal: true`), портов наружу не публикует.
- `content/` монтируется read-only в оба сервиса; рендер Markdown происходит на запрос, пересборка образа для правки текста не требуется.
- Флаг нативной оптимизации определяется в рантайме (`-march=native` → `-mcpu=native` → без флага), не зашивается.
- Коммит после каждой задачи; сообщения на русском.

## Контракты между задачами

Единый справочник имён и типов. Задачи ссылаются на него, чтобы не разъехаться.

**`web/app/content.py`**

```python
class ContentError(Exception): ...

@dataclass(frozen=True)
class Block:
    kind: str            # "viz" | "benchmark" | "exercise" | "sandbox"
    id: str
    lang: str | None     # "c" | "python" | None (для viz)
    params: dict         # разобранный YAML из тела блока

@dataclass(frozen=True)
class Section:
    id: str
    title: str
    order: int
    draft: bool
    dir: Path
    body: str            # markdown без фронтматтера

def load_section(directory: Path) -> Section
def list_sections(root: Path) -> list[Section]   # отсортованы по order, draft исключены
```

**`web/app/render.py`**

```python
def render_section(section: Section) -> tuple[str, list[Block]]
```

**`web/app/jobs.py`**

```python
def build_job(section: Section, block: Block, code: str) -> dict
```

**`runner/app/sandbox.py`**

```python
@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool

def run(cmd: list[str], cwd: Path, timeout_s: float, memory_mb: int,
        env: dict[str, str] | None = None) -> ProcResult
```

**`runner/app/measure.py`**

```python
def median(xs: list[float]) -> float
def spread_pct(xs: list[float]) -> float
def ab_result(samples: list[dict], check: dict, tolerance: float) -> dict
    # -> {"baseline_ms", "student_ms", "speedup", "spread_pct", "correct"}
def verdict(speedup: float, correct: bool, target: dict) -> bool
```

**`runner/app/build.py`**

```python
class CompileError(Exception):
    log: str
    line: int | None

def native_flag(cc: str = "gcc") -> str      # закэширован
def build_c(work: Path, harness_dir: Path, units: dict[str, str],
            cflags: list[str], defines: dict[str, str | int]) -> Path
```

**Формат `meta.yml` харнесса**

```yaml
kind: ab            # ab | sweep
lang: c             # c | python
function: matrix_sum
cflags: ["-O3"]
sizes: [1024]
warmup: 3
repeats: 11
timeout_s: 30
tolerance: 1e-9
```

**Протокол вывода бенч-бинарника** — одна строка JSON в stdout:

```json
{"samples": [{"a": 12.4, "b": 3.9}], "check": {"a": 5.0, "b": 5.0}}
{"series": [{"size": 1024, "ms": 1.2, "ms_per_element": 0.0000011}]}
```

**Компиляционные `-D`, которые runner передаёт всегда:** `BENCH_WARMUP`, `BENCH_REPEATS`, `BENCH_SIZES` (вида `{1024,2048}`), `BENCH_NSIZES`. Для Python — те же значения через переменные окружения с теми же именами.

**Переименование функций.** Студенческий и baseline-код содержат функцию с одним и тем же именем из `meta.function`. Runner компилирует их в отдельные объектники с `-D<function>=fn_a` и `-D<function>=fn_b`; `bench.c` объявляет `fn_a` и `fn_b` как `extern`. Для `kind: sweep` собирается только `fn_a`.

**Что считается эталоном корректности.** Baseline (стартовый, наивный код) считается заведомо правильным; результат студента сравнивается с результатом baseline из того же прогона по относительной погрешности `tolerance`. Файл `reference:` используется **только** тестами `make verify-content` — он подставляется вместо кода студента, чтобы доказать достижимость порога.

---

### Task 1: Скелет проекта, compose, health-check

**Files:**
- Create: `docker-compose.yml`, `Makefile`, `.gitignore`
- Create: `web/Dockerfile`, `web/requirements.txt`, `web/pytest.ini`, `web/app/__init__.py`, `web/app/main.py`
- Create: `runner/Dockerfile`, `runner/requirements.txt`, `runner/pytest.ini`, `runner/app/__init__.py`, `runner/app/main.py`
- Test: `web/tests/test_health.py`, `runner/tests/test_health.py`

**Interfaces:**
- Consumes: ничего.
- Produces: приложения `web.app.main:app` и `runner.app.main:app` с `GET /health` → `{"status": "ok"}`; команды `make test`, `make up`, `make down`.

- [ ] **Step 1: Написать падающие тесты**

`web/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

`runner/tests/test_health.py` — то же самое, слово в слово (импорт `app.main` резолвится внутри своего контейнера).

- [ ] **Step 2: Создать инфраструктуру, чтобы тесты могли запуститься**

`web/requirements.txt`:

```
fastapi~=0.115
uvicorn[standard]~=0.30
jinja2~=3.1
markdown-it-py~=3.0
pyyaml~=6.0
httpx~=0.27
pytest~=8.3
```

`runner/requirements.txt`:

```
fastapi~=0.115
uvicorn[standard]~=0.30
pyyaml~=6.0
numpy~=2.1
httpx~=0.27
pytest~=8.3
```

`web/Dockerfile`:

```dockerfile
FROM node:22-alpine AS vendor
WORKDIR /vendor
RUN npm install --no-audit --no-fund ace-builds@1 uplot@1 katex@0
RUN mkdir -p /out/ace /out/uplot /out/katex \
 && cp node_modules/ace-builds/src-min-noconflict/ace.js \
       node_modules/ace-builds/src-min-noconflict/mode-c_cpp.js \
       node_modules/ace-builds/src-min-noconflict/mode-python.js \
       node_modules/ace-builds/src-min-noconflict/theme-github_dark.js \
       node_modules/ace-builds/src-min-noconflict/theme-github.js /out/ace/ \
 && cp node_modules/uplot/dist/uPlot.iife.min.js node_modules/uplot/dist/uPlot.min.css /out/uplot/ \
 && cp -r node_modules/katex/dist/katex.min.js node_modules/katex/dist/katex.min.css \
          node_modules/katex/dist/fonts node_modules/katex/dist/contrib/auto-render.min.js /out/katex/

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=vendor /out /app/static/vendor
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`runner/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --shell /usr/sbin/nologin bench
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`web/pytest.ini`:

```ini
[pytest]
testpaths = tests
markers =
    content: медленные проверки учебного материала (make verify-content)
addopts = -m "not content"
```

`runner/pytest.ini`:

```ini
[pytest]
testpaths = tests
```

`docker-compose.yml`:

```yaml
services:
  web:
    build: ./web
    ports:
      - "18080:8000"
    volumes:
      - ./content:/app/content:ro
    environment:
      RUNNER_URL: http://runner:8000
      CONTENT_ROOT: /app/content
    networks: [front, back]
    depends_on: [runner]

  runner:
    build: ./runner
    volumes:
      - ./content:/content:ro
    environment:
      CONTENT_ROOT: /content
    networks: [back]
    tmpfs:
      - /work:size=512m,mode=1777

networks:
  front:
  back:
    internal: true
```

`Makefile`:

```make
.PHONY: up down test test-web test-runner verify-content

up:
	docker compose up --build

down:
	docker compose down -v

test: test-web test-runner

test-web:
	docker compose run --rm --build --no-deps web python -m pytest -q

test-runner:
	docker compose run --rm --build --no-deps runner python -m pytest -q

verify-content:
	docker compose run --rm --build web python -m pytest -q -m content
```

`.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
```

Также создать пустые `web/app/__init__.py`, `runner/app/__init__.py` и пустую папку `content/` с файлом `content/.gitkeep`, иначе volume смонтируется как пустая директория, созданная root.

- [ ] **Step 3: Запустить тесты и убедиться, что они падают**

Run: `make test`
Expected: FAIL с `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 4: Написать минимальную реализацию**

`web/app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Курс: оптимизация инференса")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

`runner/app/main.py` — идентично, с `title="Runner"`.

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `make test`
Expected: PASS, два теста

- [ ] **Step 6: Проверить, что compose поднимается**

Run: `docker compose up --build -d && sleep 3 && curl -sf localhost:18080/health && docker compose down`
Expected: `{"status":"ok"}`

- [ ] **Step 7: Коммит**

```bash
git add -A
git commit -m "Скелет проекта: compose из двух сервисов, health-check, тесты"
```

---

### Task 2: Парсер разделов и оглавление

**Files:**
- Create: `web/app/content.py`
- Test: `web/tests/test_content.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `ContentError`, `Section`, `load_section(directory) -> Section`, `list_sections(root) -> list[Section]`.

- [ ] **Step 1: Написать падающие тесты**

`web/tests/test_content.py`:

```python
import pytest

from app.content import ContentError, list_sections, load_section

SECTION = """---
id: cpu-cache
title: Кэш процессора
order: 10
---

Текст раздела.
"""


def write_section(root, name, text):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "section.md").write_text(text, encoding="utf-8")
    return directory


def test_load_section_reads_frontmatter(tmp_path):
    directory = write_section(tmp_path, "01-cpu-cache", SECTION)

    section = load_section(directory)

    assert section.id == "cpu-cache"
    assert section.title == "Кэш процессора"
    assert section.order == 10
    assert section.draft is False
    assert section.body.strip() == "Текст раздела."


def test_load_section_without_frontmatter_fails(tmp_path):
    directory = write_section(tmp_path, "01-broken", "Просто текст\n")

    with pytest.raises(ContentError, match="фронтматтер"):
        load_section(directory)


def test_load_section_without_title_fails(tmp_path):
    directory = write_section(tmp_path, "01-broken", "---\nid: x\norder: 10\n---\n\nтекст\n")

    with pytest.raises(ContentError, match="title"):
        load_section(directory)


def test_list_sections_sorted_by_order(tmp_path):
    write_section(tmp_path, "b", "---\nid: b\ntitle: Б\norder: 20\n---\n\nb\n")
    write_section(tmp_path, "a", "---\nid: a\ntitle: А\norder: 10\n---\n\na\n")

    assert [s.id for s in list_sections(tmp_path)] == ["a", "b"]


def test_list_sections_skips_drafts(tmp_path):
    write_section(tmp_path, "a", "---\nid: a\ntitle: А\norder: 10\n---\n\na\n")
    write_section(tmp_path, "d", "---\nid: d\ntitle: Д\norder: 20\ndraft: true\n---\n\nd\n")

    assert [s.id for s in list_sections(tmp_path)] == ["a"]


def test_list_sections_ignores_dirs_without_section_md(tmp_path):
    (tmp_path / "images").mkdir()
    write_section(tmp_path, "a", "---\nid: a\ntitle: А\norder: 10\n---\n\na\n")

    assert [s.id for s in list_sections(tmp_path)] == ["a"]
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `make test-web`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.content'`

- [ ] **Step 3: Написать реализацию**

`web/app/content.py`:

```python
from dataclasses import dataclass
from pathlib import Path

import yaml


class ContentError(Exception):
    """Ошибка в учебных материалах: разметка, отсутствующие файлы, битые ссылки."""


@dataclass(frozen=True)
class Block:
    kind: str
    id: str
    lang: str | None
    params: dict


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    order: int
    draft: bool
    dir: Path
    body: str


def _split_frontmatter(text: str, source: Path) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ContentError(f"{source}: отсутствует фронтматтер (файл должен начинаться с ---)")
    _, _, rest = text.partition("---\n")
    raw_meta, sep, body = rest.partition("\n---\n")
    if not sep:
        raise ContentError(f"{source}: фронтматтер не закрыт строкой ---")
    try:
        meta = yaml.safe_load(raw_meta) or {}
    except yaml.YAMLError as exc:
        raise ContentError(f"{source}: не разобрался фронтматтер: {exc}") from exc
    if not isinstance(meta, dict):
        raise ContentError(f"{source}: фронтматтер должен быть словарём")
    return meta, body


def load_section(directory: Path) -> Section:
    source = directory / "section.md"
    if not source.exists():
        raise ContentError(f"{directory}: нет файла section.md")
    meta, body = _split_frontmatter(source.read_text(encoding="utf-8"), source)

    for field in ("id", "title", "order"):
        if field not in meta:
            raise ContentError(f"{source}: во фронтматтере нет обязательного поля {field}")

    return Section(
        id=str(meta["id"]),
        title=str(meta["title"]),
        order=int(meta["order"]),
        draft=bool(meta.get("draft", False)),
        dir=directory,
        body=body,
    )


def list_sections(root: Path) -> list[Section]:
    sections = [
        load_section(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and (child / "section.md").exists()
    ]
    return sorted((s for s in sections if not s.draft), key=lambda s: s.order)
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `make test-web`
Expected: PASS, 6 тестов

- [ ] **Step 5: Коммит**

```bash
git add web/app/content.py web/tests/test_content.py
git commit -m "Парсер разделов: фронтматтер, оглавление, черновики"
```

---

### Task 3: Интерактивные блоки и рендер Markdown

**Files:**
- Create: `web/app/render.py`
- Test: `web/tests/test_render.py`

**Interfaces:**
- Consumes: `Section`, `Block`, `ContentError` из Task 2.
- Produces: `render_section(section) -> tuple[str, list[Block]]`. HTML содержит `<div class="block" data-kind="..." data-id="..." data-lang="..." data-params='<json>'></div>` на месте каждого интерактивного блока.

Валидация, которую обязан выполнять рендер (каждое нарушение — `ContentError` с путём файла):

- неизвестный `kind`;
- отсутствует `id`;
- `exercise` без `starter`, `reference`, `harness`, `target`;
- файл из `starter`/`reference` не существует;
- папки `harness/<имя>` не существует;
- `benchmark` над харнессом `kind: ab` — не ровно два элемента в `variants`, либо нет файла `snippets/<harness>_<variant>.<ext>`;
- `benchmark` над харнессом `kind: sweep` — нет поля `source`, либо файла по этому пути;
- `viz`: нет файла `web/static/viz/<id>.js`.

**Почему `benchmark` валидируется по-разному.** Харнесс `kind: ab` сравнивает две
реализации и требует ровно двух вариантов. Харнесс `kind: sweep` гоняет одну
реализацию по возрастающим размерам (это лестница кэша) — вариантов у него нет
вовсе, есть единственный `source`. Рендер обязан заглянуть в
`harness/<имя>/meta.yml` и выбрать ветку по полю `kind`; иначе sweep-блок из
Task 16 не пройдёт валидацию.

- [ ] **Step 1: Написать падающие тесты**

`web/tests/test_render.py`:

```python
import json

import pytest

from app.content import ContentError, load_section
from app.render import render_section

def make_section(tmp_path, body, *, with_files=True):
    directory = tmp_path / "01-demo"
    directory.mkdir(parents=True)
    (directory / "section.md").write_text(
        "---\nid: demo\ntitle: Демо\norder: 10\n---\n\n" + body, encoding="utf-8"
    )
    if with_files:
        (directory / "snippets").mkdir()
        for name in ("sum_starter.c", "sum_ref.c", "sum_rows.c", "sum_cols.c", "walk.c"):
            (directory / "snippets" / name).write_text("int f(void){return 0;}\n")
        (directory / "harness" / "sum").mkdir(parents=True)
        (directory / "harness" / "sum" / "meta.yml").write_text("kind: ab\nlang: c\n")
        (directory / "harness" / "stride").mkdir(parents=True)
        (directory / "harness" / "stride" / "meta.yml").write_text("kind: sweep\nlang: c\n")
    return load_section(directory)


def test_markdown_renders_to_html(tmp_path):
    section = make_section(tmp_path, "# Заголовок\n\nАбзац с **жирным**.\n")

    html, blocks = render_section(section)

    assert "<h1>Заголовок</h1>" in html
    assert "<strong>жирным</strong>" in html
    assert blocks == []


def test_exercise_block_becomes_placeholder(tmp_path):
    section = make_section(
        tmp_path,
        "```exercise id=col-sum lang=c\n"
        "title: Ускорь обход\n"
        "target: speedup >= 3\n"
        "starter: snippets/sum_starter.c\n"
        "reference: snippets/sum_ref.c\n"
        "harness: sum\n"
        "```\n",
    )

    html, blocks = render_section(section)

    assert len(blocks) == 1
    assert blocks[0].kind == "exercise"
    assert blocks[0].id == "col-sum"
    assert blocks[0].lang == "c"
    assert blocks[0].params["target"] == "speedup >= 3"
    assert 'data-kind="exercise"' in html
    assert 'data-id="col-sum"' in html
    assert "Ускорь обход" in html


def test_exercise_starter_code_is_inlined_into_params(tmp_path):
    section = make_section(
        tmp_path,
        "```exercise id=col-sum lang=c\n"
        "title: Т\ntarget: speedup >= 3\n"
        "starter: snippets/sum_starter.c\nreference: snippets/sum_ref.c\nharness: sum\n```\n",
    )

    _, blocks = render_section(section)

    assert blocks[0].params["starter_code"] == "int f(void){return 0;}\n"
    assert "reference_code" not in blocks[0].params


def test_exercise_without_reference_fails(tmp_path):
    section = make_section(
        tmp_path,
        "```exercise id=x lang=c\ntitle: Т\ntarget: speedup >= 3\n"
        "starter: snippets/sum_starter.c\nharness: sum\n```\n",
    )

    with pytest.raises(ContentError, match="reference"):
        render_section(section)


def test_exercise_with_missing_starter_file_fails(tmp_path):
    section = make_section(
        tmp_path,
        "```exercise id=x lang=c\ntitle: Т\ntarget: speedup >= 3\n"
        "starter: snippets/nope.c\nreference: snippets/sum_ref.c\nharness: sum\n```\n",
    )

    with pytest.raises(ContentError, match="nope.c"):
        render_section(section)


def test_exercise_with_missing_harness_fails(tmp_path):
    section = make_section(
        tmp_path,
        "```exercise id=x lang=c\ntitle: Т\ntarget: speedup >= 3\n"
        "starter: snippets/sum_starter.c\nreference: snippets/sum_ref.c\nharness: missing\n```\n",
    )

    with pytest.raises(ContentError, match="missing"):
        render_section(section)


def test_benchmark_resolves_variant_files(tmp_path):
    section = make_section(
        tmp_path,
        "```benchmark id=rows-vs-cols lang=c\nharness: sum\nvariants: [rows, cols]\n```\n",
    )

    _, blocks = render_section(section)

    assert blocks[0].params["variant_sources"] == ["sum_rows.c", "sum_cols.c"]


def test_benchmark_with_missing_variant_file_fails(tmp_path):
    section = make_section(
        tmp_path,
        "```benchmark id=x lang=c\nharness: sum\nvariants: [rows, nope]\n```\n",
    )

    with pytest.raises(ContentError, match="sum_nope.c"):
        render_section(section)


def test_benchmark_requires_exactly_two_variants(tmp_path):
    section = make_section(
        tmp_path,
        "```benchmark id=x lang=c\nharness: sum\nvariants: [rows]\n```\n",
    )

    with pytest.raises(ContentError, match="ровно два"):
        render_section(section)


def test_sweep_benchmark_uses_single_source(tmp_path):
    section = make_section(
        tmp_path,
        "```benchmark id=ladder lang=c\nharness: stride\nsource: snippets/walk.c\n```\n",
    )

    _, blocks = render_section(section)

    assert blocks[0].params["source"] == "snippets/walk.c"
    assert "variant_sources" not in blocks[0].params


def test_sweep_benchmark_without_source_fails(tmp_path):
    section = make_section(tmp_path, "```benchmark id=ladder lang=c\nharness: stride\n```\n")

    with pytest.raises(ContentError, match="source"):
        render_section(section)


def test_unknown_block_kind_fails(tmp_path):
    section = make_section(tmp_path, "```quiz id=x\nfoo: bar\n```\n")

    with pytest.raises(ContentError, match="quiz"):
        render_section(section)


def test_plain_code_fence_is_not_a_block(tmp_path):
    section = make_section(tmp_path, "```c\nint main(void){return 0;}\n```\n")

    html, blocks = render_section(section)

    assert blocks == []
    assert "int main" in html
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `make test-web`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.render'`

- [ ] **Step 3: Написать реализацию**

`web/app/render.py`:

```python
import json
from html import escape
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

from app.content import Block, ContentError, Section

BLOCK_KINDS = {"viz", "benchmark", "exercise", "sandbox"}
EXT = {"c": "c", "python": "py"}
VIZ_DIR = Path(__file__).resolve().parent.parent / "static" / "viz"


def _parse_info(info: str) -> tuple[str, dict[str, str]]:
    parts = info.strip().split()
    kind = parts[0]
    attrs = {}
    for part in parts[1:]:
        key, _, value = part.partition("=")
        attrs[key] = value
    return kind, attrs


def _require_file(section: Section, relative: str, what: str) -> str:
    path = section.dir / relative
    if not path.exists():
        raise ContentError(f"{section.dir / 'section.md'}: {what} указывает на отсутствующий файл {relative}")
    return path.read_text(encoding="utf-8")


def _require_harness(section: Section, name: str) -> None:
    if not (section.dir / "harness" / name).is_dir():
        raise ContentError(f"{section.dir / 'section.md'}: нет харнесса harness/{name}")


def _harness_kind(section: Section, name: str) -> str:
    meta_path = section.dir / "harness" / name / "meta.yml"
    if not meta_path.exists():
        raise ContentError(f"{meta_path}: нет meta.yml у харнесса {name}")
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    return str(meta.get("kind", "ab"))


def _build_block(section: Section, info: str, body: str) -> Block:
    kind, attrs = _parse_info(info)
    if kind not in BLOCK_KINDS:
        raise ContentError(f"{section.dir / 'section.md'}: неизвестный тип блока {kind}")
    if "id" not in attrs:
        raise ContentError(f"{section.dir / 'section.md'}: блок {kind} без id")

    try:
        params = yaml.safe_load(body) or {}
    except yaml.YAMLError as exc:
        raise ContentError(f"{section.dir / 'section.md'}: блок {attrs['id']}: {exc}") from exc
    if not isinstance(params, dict):
        params = {"text": str(params).strip()}

    lang = attrs.get("lang")
    ext = EXT.get(lang or "", "")

    if kind == "viz":
        if not (VIZ_DIR / f"{attrs['id']}.js").exists():
            raise ContentError(
                f"{section.dir / 'section.md'}: для viz {attrs['id']} нет модуля static/viz/{attrs['id']}.js"
            )

    if kind == "exercise":
        for field in ("title", "target", "starter", "reference", "harness"):
            if field not in params:
                raise ContentError(
                    f"{section.dir / 'section.md'}: exercise {attrs['id']} без поля {field}"
                )
        _require_harness(section, params["harness"])
        params["starter_code"] = _require_file(section, params["starter"], "starter")
        _require_file(section, params["reference"], "reference")

    if kind == "benchmark":
        if "harness" not in params:
            raise ContentError(
                f"{section.dir / 'section.md'}: benchmark {attrs['id']} без поля harness"
            )
        _require_harness(section, params["harness"])
        if _harness_kind(section, params["harness"]) == "sweep":
            if "source" not in params:
                raise ContentError(
                    f"{section.dir / 'section.md'}: benchmark {attrs['id']} над sweep-харнессом "
                    f"требует поле source"
                )
            _require_file(section, params["source"], "source")
        else:
            if "variants" not in params:
                raise ContentError(
                    f"{section.dir / 'section.md'}: benchmark {attrs['id']} без поля variants"
                )
            variants = params["variants"]
            if not isinstance(variants, list) or len(variants) != 2:
                raise ContentError(
                    f"{section.dir / 'section.md'}: benchmark {attrs['id']}: нужно ровно два варианта"
                )
            sources = []
            for variant in variants:
                name = f"{params['harness']}_{variant}.{ext}"
                _require_file(section, f"snippets/{name}", f"вариант {variant}")
                sources.append(name)
            params["variant_sources"] = sources

    if kind == "sandbox":
        if "starter" in params:
            params["starter_code"] = _require_file(section, params["starter"], "starter")

    return Block(kind=kind, id=attrs["id"], lang=lang, params=params)


def render_section(section: Section) -> tuple[str, list[Block]]:
    blocks: list[Block] = []
    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")

    default_fence = md.renderer.rules["fence"]

    def fence(tokens, idx, options, env):
        token = tokens[idx]
        kind = token.info.strip().split()[0] if token.info.strip() else ""
        if kind not in BLOCK_KINDS:
            return default_fence(tokens, idx, options, env)
        block = _build_block(section, token.info, token.content)
        blocks.append(block)
        payload = escape(json.dumps(block.params, ensure_ascii=False), quote=True)
        return (
            f'<div class="block" data-kind="{block.kind}" data-id="{block.id}" '
            f'data-lang="{block.lang or ""}" data-params="{payload}"></div>\n'
        )

    md.renderer.rules["fence"] = fence
    html = md.render(section.body)
    return html, blocks
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `make test-web`
Expected: PASS. Тест `test_render.py` про `viz` пока не написан — модуль `static/viz/` появится в Task 12; отдельного теста на успешный `viz` здесь нет намеренно, есть только на неуспешный путь через другие блоки.

- [ ] **Step 5: Коммит**

```bash
git add web/app/render.py web/tests/test_render.py
git commit -m "Рендер Markdown и разбор интерактивных блоков с валидацией"
```

---

### Task 4: Страницы курса

**Files:**
- Create: `web/app/templates/base.html`, `web/app/templates/index.html`, `web/app/templates/section.html`
- Create: `web/static/style.css`
- Modify: `web/app/main.py`
- Test: `web/tests/test_pages.py`

**Interfaces:**
- Consumes: `list_sections`, `load_section`, `render_section`.
- Produces: `GET /` (оглавление), `GET /section/{section_id}` (раздел), отдача `/static`. Переменная окружения `CONTENT_ROOT` задаёт корень контента; в тестах подменяется через `app.main.content_root()`.

- [ ] **Step 1: Написать падающие тесты**

`web/tests/test_pages.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    directory = tmp_path / "01-demo"
    directory.mkdir(parents=True)
    (directory / "section.md").write_text(
        "---\nid: demo\ntitle: Демо-раздел\norder: 10\n---\n\n## Привет\n\nТекст.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_ROOT", str(tmp_path))
    return TestClient(main.app)


def test_index_lists_sections(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Демо-раздел" in response.text
    assert "/section/demo" in response.text


def test_section_page_renders_markdown(client):
    response = client.get("/section/demo")

    assert response.status_code == 200
    assert "<h2>Привет</h2>" in response.text


def test_unknown_section_returns_404(client):
    assert client.get("/section/nope").status_code == 404


def test_broken_content_returns_500_with_reason(client, tmp_path):
    (tmp_path / "02-broken").mkdir()
    (tmp_path / "02-broken" / "section.md").write_text("нет фронтматтера\n", encoding="utf-8")

    response = client.get("/")

    assert response.status_code == 500
    assert "фронтматтер" in response.text
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `make test-web`
Expected: FAIL, 404 на `/` (маршрута ещё нет)

- [ ] **Step 3: Написать шаблоны**

`web/app/templates/base.html`:

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Оптимизация инференса{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="/static/vendor/uplot/uPlot.min.css">
  <link rel="stylesheet" href="/static/vendor/katex/katex.min.css">
</head>
<body>
  <header class="site-header"><a href="/">Оптимизация инференса</a></header>
  <main>{% block content %}{% endblock %}</main>
  {% block scripts %}{% endblock %}
</body>
</html>
```

`web/app/templates/index.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Разделы курса</h1>
<ol class="toc">
  {% for section in sections %}
  <li><a href="/section/{{ section.id }}">{{ section.title }}</a></li>
  {% endfor %}
</ol>
{% endblock %}
```

`web/app/templates/section.html`:

```html
{% extends "base.html" %}
{% block title %}{{ section.title }}{% endblock %}
{% block content %}
<article class="section" data-section="{{ section.id }}">
  {{ body | safe }}
</article>
{% endblock %}
{% block scripts %}
<script src="/static/vendor/ace/ace.js"></script>
<script src="/static/vendor/uplot/uPlot.iife.min.js"></script>
<script src="/static/vendor/katex/katex.min.js"></script>
<script src="/static/vendor/katex/auto-render.min.js"></script>
<script type="module" src="/static/app.js"></script>
{% endblock %}
```

`web/static/style.css` — минимальная типографика: колонка `max-width: 46rem`, системный шрифт, `color-scheme: light dark`, переменные цвета в `:root` и переопределение в `@media (prefers-color-scheme: dark)`, стили для `.block`, `.toc`, таблиц и `blockquote`-врезок.

- [ ] **Step 4: Написать маршруты**

`web/app/main.py`:

```python
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.content import ContentError, Section, list_sections, load_section
from app.render import render_section

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Курс: оптимизация инференса")
app.mount("/static", StaticFiles(directory=BASE_DIR.parent / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def content_root() -> Path:
    return Path(os.environ.get("CONTENT_ROOT", BASE_DIR.parent / "content"))


def find_section(section_id: str) -> Section:
    for section in list_sections(content_root()):
        if section.id == section_id:
            return section
    raise HTTPException(status_code=404, detail=f"Раздел {section_id} не найден")


@app.exception_handler(ContentError)
def content_error_handler(request: Request, exc: ContentError) -> PlainTextResponse:
    return PlainTextResponse(f"Ошибка в материалах курса:\n\n{exc}", status_code=500)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"sections": list_sections(content_root())}
    )


@app.get("/section/{section_id}", response_class=HTMLResponse)
def section_page(request: Request, section_id: str):
    section = find_section(section_id)
    body, _blocks = render_section(section)
    return templates.TemplateResponse(request, "section.html", {"section": section, "body": body})
```

Создать пустой `web/static/app.js` с содержимым `export {};`, иначе тег `<script type="module">` даст 404.

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `make test-web`
Expected: PASS, 4 теста

- [ ] **Step 6: Коммит**

```bash
git add web/app/main.py web/app/templates web/static web/tests/test_pages.py
git commit -m "Страницы курса: оглавление, раздел, обработка ошибок материалов"
```

---

### Task 5: Runner — песочница с лимитами

**Files:**
- Create: `runner/app/sandbox.py`
- Test: `runner/tests/test_sandbox.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `ProcResult`, `run(cmd, cwd, timeout_s, memory_mb, env=None) -> ProcResult`.

- [ ] **Step 1: Написать падающие тесты**

`runner/tests/test_sandbox.py`:

```python
import sys

from app.sandbox import run


def test_run_captures_stdout(tmp_path):
    result = run([sys.executable, "-c", "print('привет')"], tmp_path, timeout_s=10, memory_mb=512)

    assert result.returncode == 0
    assert result.stdout.strip() == "привет"
    assert result.timed_out is False


def test_run_captures_stderr_and_returncode(tmp_path):
    result = run(
        [sys.executable, "-c", "import sys; sys.stderr.write('плохо'); sys.exit(3)"],
        tmp_path,
        timeout_s=10,
        memory_mb=512,
    )

    assert result.returncode == 3
    assert "плохо" in result.stderr


def test_run_times_out(tmp_path):
    result = run(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, timeout_s=1, memory_mb=512
    )

    assert result.timed_out is True


def test_run_enforces_memory_limit(tmp_path):
    result = run(
        [sys.executable, "-c", "x = bytearray(400 * 1024 * 1024)"],
        tmp_path,
        timeout_s=20,
        memory_mb=128,
    )

    assert result.returncode != 0
    assert result.timed_out is False


def test_run_uses_given_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("тут")
    result = run(
        [sys.executable, "-c", "import pathlib; print(pathlib.Path('marker.txt').read_text())"],
        tmp_path,
        timeout_s=10,
        memory_mb=512,
    )

    assert "тут" in result.stdout
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `make test-runner`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.sandbox'`

- [ ] **Step 3: Написать реализацию**

`runner/app/sandbox.py`:

```python
import resource
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_PROCESSES = 64
MAX_FILE_MB = 64


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def _limits(memory_mb: int):
    def apply() -> None:
        memory = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCESSES, MAX_PROCESSES))
        file_size = MAX_FILE_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def run(
    cmd: list[str],
    cwd: Path,
    timeout_s: float,
    memory_mb: int,
    env: dict[str, str] | None = None,
) -> ProcResult:
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=_limits(memory_mb),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ProcResult(
            returncode=-1,
            stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            timed_out=True,
        )
    return ProcResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `make test-runner`
Expected: PASS, 5 тестов

- [ ] **Step 5: Коммит**

```bash
git add runner/app/sandbox.py runner/tests/test_sandbox.py
git commit -m "Песочница runner: лимиты памяти и процессов, таймаут, рабочая директория"
```

---

### Task 6: Runner — статистика замеров

**Files:**
- Create: `runner/app/measure.py`
- Test: `runner/tests/test_measure.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `median`, `spread_pct`, `ab_result`, `verdict`.

`ab_result(samples, check, tolerance)` принимает `samples = [{"a": ms, "b": ms}, ...]` и `check = {"a": value, "b": value}` и возвращает словарь с ключами `baseline_ms`, `student_ms`, `speedup`, `spread_pct`, `correct`. `verdict(speedup, correct, target)` принимает `target = {"metric": "speedup", "op": ">=", "value": 3.0}`.

- [ ] **Step 1: Написать падающие тесты**

`runner/tests/test_measure.py`:

```python
import pytest

from app.measure import ab_result, median, spread_pct, verdict


def test_median_of_odd_count():
    assert median([3.0, 1.0, 2.0]) == 2.0


def test_median_ignores_single_outlier():
    assert median([1.0, 1.0, 1.0, 1.0, 100.0]) == 1.0


def test_spread_pct_is_zero_for_identical_samples():
    assert spread_pct([5.0] * 11) == 0.0


def test_spread_pct_grows_with_noise():
    quiet = spread_pct([10.0, 10.1, 9.9, 10.0, 10.05, 9.95, 10.0, 10.02, 9.98, 10.01, 10.0])
    noisy = spread_pct([10.0, 14.0, 6.0, 12.0, 8.0, 11.0, 9.0, 13.0, 7.0, 10.0, 10.0])
    assert noisy > quiet


def test_ab_result_computes_speedup():
    samples = [{"a": 12.0, "b": 4.0} for _ in range(5)]

    result = ab_result(samples, {"a": 1.0, "b": 1.0}, tolerance=1e-9)

    assert result["baseline_ms"] == 12.0
    assert result["student_ms"] == 4.0
    assert result["speedup"] == pytest.approx(3.0)
    assert result["correct"] is True


def test_ab_result_marks_wrong_answer_incorrect_even_when_fast():
    samples = [{"a": 12.0, "b": 0.1} for _ in range(5)]

    result = ab_result(samples, {"a": 1.0, "b": 2.0}, tolerance=1e-9)

    assert result["speedup"] > 100
    assert result["correct"] is False


def test_ab_result_accepts_float_noise_within_tolerance():
    samples = [{"a": 12.0, "b": 4.0} for _ in range(5)]

    result = ab_result(samples, {"a": 1.0, "b": 1.0 + 1e-12}, tolerance=1e-9)

    assert result["correct"] is True


def test_ab_result_accepts_relatively_tiny_difference_on_large_values():
    samples = [{"a": 1.0, "b": 1.0}]

    result = ab_result(samples, {"a": 1e9, "b": 1e9 + 1e-3}, tolerance=1e-9)

    assert result["correct"] is True


def test_ab_result_rejects_relatively_large_difference_on_large_values():
    samples = [{"a": 1.0, "b": 1.0}]

    result = ab_result(samples, {"a": 1e9, "b": 1.1e9}, tolerance=1e-9)

    assert result["correct"] is False


def test_verdict_requires_both_correctness_and_target():
    target = {"metric": "speedup", "op": ">=", "value": 3.0}

    assert verdict(3.5, True, target) is True
    assert verdict(3.5, False, target) is False
    assert verdict(2.5, True, target) is False
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `make test-runner`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.measure'`

- [ ] **Step 3: Написать реализацию**

`runner/app/measure.py`:

```python
import statistics


def median(xs: list[float]) -> float:
    return float(statistics.median(xs))


def spread_pct(xs: list[float]) -> float:
    """Разброс замеров: (p90 - p10) / медиана, в процентах."""
    if len(xs) < 2:
        return 0.0
    ordered = sorted(xs)
    p10 = ordered[max(0, round(0.1 * (len(ordered) - 1)))]
    p90 = ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]
    mid = median(xs)
    if mid == 0:
        return 0.0
    return (p90 - p10) / mid * 100.0


def _close(a: float, b: float, tolerance: float) -> bool:
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= tolerance * scale


def ab_result(samples: list[dict], check: dict, tolerance: float) -> dict:
    a_times = [s["a"] for s in samples]
    b_times = [s["b"] for s in samples]
    baseline = median(a_times)
    student = median(b_times)
    return {
        "baseline_ms": baseline,
        "student_ms": student,
        "speedup": baseline / student if student > 0 else float("inf"),
        "spread_pct": max(spread_pct(a_times), spread_pct(b_times)),
        "correct": _close(float(check["a"]), float(check["b"]), tolerance),
    }


def verdict(speedup: float, correct: bool, target: dict) -> bool:
    if not correct:
        return False
    if target["metric"] != "speedup":
        raise ValueError(f"Неизвестная метрика цели: {target['metric']}")
    if target["op"] not in (">=", ">"):
        raise ValueError(f"Неизвестная операция сравнения: {target['op']}")
    value = float(target["value"])
    return speedup >= value if target["op"] == ">=" else speedup > value
```

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `make test-runner`
Expected: PASS, 11 тестов

- [ ] **Step 5: Коммит**

```bash
git add runner/app/measure.py runner/tests/test_measure.py
git commit -m "Статистика замеров: медиана, разброс, ускорение, вердикт"
```

---

### Task 7: Runner — сборка и прогон C в режиме A/B

**Files:**
- Create: `runner/app/build.py`, `runner/app/jobs.py`
- Create: `runner/tests/fixtures/harness/sumtest/meta.yml`, `runner/tests/fixtures/harness/sumtest/bench.c`
- Create: `runner/tests/fixtures/snippets/sumtest_slow.c`, `runner/tests/fixtures/snippets/sumtest_fast.c`, `runner/tests/fixtures/snippets/sumtest_wrong.c`
- Test: `runner/tests/test_build.py`, `runner/tests/test_jobs_c.py`

**Interfaces:**
- Consumes: `sandbox.run`, `measure.ab_result`, `measure.verdict`.
- Produces: `native_flag(cc)`, `CompileError`, `build_c(work, harness_dir, units, cflags, defines) -> Path`, `run_job(job: dict) -> dict`.

Формат `job`, который приходит от `web` (Task 10 его строит):

```python
{
  "mode": "exercise",              # exercise | benchmark | sandbox
  "lang": "c",
  "harness_dir": "01-cpu-cache/harness/matrix_sum",   # относительно CONTENT_ROOT
  "units": {"a": "<код baseline>", "b": "<код студента>"},
  "target": {"metric": "speedup", "op": ">=", "value": 3.0},
}
```

- [ ] **Step 1: Создать фикстуру харнесса**

`runner/tests/fixtures/harness/sumtest/meta.yml`:

```yaml
kind: ab
lang: c
function: total
cflags: ["-O2"]
sizes: [200000]
warmup: 2
repeats: 5
timeout_s: 30
tolerance: 1e-9
```

`runner/tests/fixtures/harness/sumtest/bench.c`:

```c
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const double *data, int n);
extern double fn_b(const double *data, int n);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    double *data = malloc((size_t)n * sizeof(double));
    for (int i = 0; i < n; i++) data[i] = (double)(i % 17) * 0.5;

    double check_a = 0, check_b = 0;
    for (int w = 0; w < BENCH_WARMUP; w++) { check_a = fn_a(data, n); check_b = fn_b(data, n); }

    printf("{\"samples\":[");
    for (int r = 0; r < BENCH_REPEATS; r++) {
        double t0 = now_ms(); check_a = fn_a(data, n); double t1 = now_ms();
        double t2 = now_ms(); check_b = fn_b(data, n); double t3 = now_ms();
        printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", t1 - t0, t3 - t2);
    }
    printf("],\"check\":{\"a\":%.17g,\"b\":%.17g}}\n", check_a, check_b);
    free(data);
    return 0;
}
```

`runner/tests/fixtures/snippets/sumtest_slow.c`:

```c
double total(const double *data, int n) {
    double s = 0;
    for (int step = 0; step < 16; step++)
        for (int i = step; i < n; i += 16) s += data[i];
    return s;
}
```

`runner/tests/fixtures/snippets/sumtest_fast.c`:

```c
double total(const double *data, int n) {
    double s = 0;
    for (int i = 0; i < n; i++) s += data[i];
    return s;
}
```

`runner/tests/fixtures/snippets/sumtest_wrong.c`:

```c
double total(const double *data, int n) {
    (void)data;
    return (double)n;
}
```

- [ ] **Step 2: Написать падающие тесты**

`runner/tests/test_build.py`:

```python
import pytest

from app.build import CompileError, build_c, native_flag

HARNESS = "tests/fixtures/harness/sumtest"


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def test_native_flag_is_supported_by_compiler():
    flag = native_flag()
    assert flag in {"-march=native", "-mcpu=native", ""}


def test_build_produces_runnable_binary(tmp_path):
    binary = build_c(
        tmp_path,
        HARNESS,
        {"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")},
        cflags=["-O2"],
        defines={"BENCH_WARMUP": 1, "BENCH_REPEATS": 2, "BENCH_SIZES": "{1000}", "BENCH_NSIZES": 1},
    )

    assert binary.exists()


def test_build_reports_compile_error_with_line(tmp_path):
    with pytest.raises(CompileError) as exc:
        build_c(
            tmp_path,
            HARNESS,
            {"a": read("sumtest_slow.c"), "b": "double total(const double *d, int n) { syntax error }"},
            cflags=["-O2"],
            defines={"BENCH_WARMUP": 1, "BENCH_REPEATS": 2, "BENCH_SIZES": "{1000}", "BENCH_NSIZES": 1},
        )

    assert exc.value.line == 1
    assert "error" in exc.value.log
```

`runner/tests/test_jobs_c.py`:

```python
from app.jobs import run_job

HARNESS = "tests/fixtures/harness/sumtest"


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def job(units, mode="exercise", target=None):
    return {
        "mode": mode,
        "lang": "c",
        "harness_dir": HARNESS,
        "units": units,
        "target": target or {"metric": "speedup", "op": ">=", "value": 1.2},
    }


def test_faster_correct_solution_passes():
    result = run_job(job({"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")}))

    assert result["status"] == "ok"
    assert result["correct"] is True
    assert result["speedup"] > 1.0
    assert result["passed"] is True
    assert "-O2" in result["compile_command"]


def test_wrong_answer_fails_even_if_fast():
    result = run_job(job({"a": read("sumtest_slow.c"), "b": read("sumtest_wrong.c")}))

    assert result["correct"] is False
    assert result["passed"] is False


def test_identical_code_does_not_reach_target():
    code = read("sumtest_slow.c")
    result = run_job(job({"a": code, "b": code}, target={"metric": "speedup", "op": ">=", "value": 3}))

    assert result["passed"] is False


def test_compile_error_is_reported_to_student():
    result = run_job(job({"a": read("sumtest_slow.c"), "b": "не код"}))

    assert result["status"] == "compile_error"
    assert result["line"] == 1
    assert "error" in result["message"] or "error" in result["log"]


def test_infinite_loop_reports_timeout():
    slow = "double total(const double *d, int n){ (void)d; while (n) { } return 0; }"
    result = run_job(job({"a": read("sumtest_slow.c"), "b": slow}))

    assert result["status"] == "timeout"
    assert "бесконечн" in result["message"]
```

Для теста таймаута `meta.yml` фикстуры даёт 30 с; чтобы тест не шёл полминуты, `run_job` обязан уважать поле `timeout_s` из job'а, если оно есть. Добавить в `job()` хелпер теста ключ `"timeout_s": 3`.

- [ ] **Step 3: Запустить тесты и убедиться, что они падают**

Run: `make test-runner`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.build'`

- [ ] **Step 4: Написать `build.py`**

```python
import functools
import re
import shutil
import subprocess
from pathlib import Path

CC = "gcc"
COMPILE_TIMEOUT_S = 10
ERROR_LINE = re.compile(r"^[^:]+:(\d+):\d+:\s*error", re.MULTILINE)


class CompileError(Exception):
    def __init__(self, log: str, line: int | None) -> None:
        super().__init__(log)
        self.log = log
        self.line = line


@functools.cache
def native_flag(cc: str = CC) -> str:
    """Подбирает флаг нативной оптимизации: он разный на x86 и aarch64."""
    for flag in ("-march=native", "-mcpu=native"):
        probe = subprocess.run(
            [cc, flag, "-x", "c", "-c", "-", "-o", "/dev/null"],
            input="int main(void){return 0;}",
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return flag
    return ""


def _defines(defines: dict) -> list[str]:
    return [f"-D{key}={value}" for key, value in defines.items()]


def build_c(
    work: Path,
    harness_dir: str | Path,
    units: dict[str, str],
    cflags: list[str],
    defines: dict,
) -> Path:
    harness = Path(harness_dir)
    meta_function = _function_name(harness)
    flags = [*cflags, native_flag(), *_defines(defines)]
    flags = [flag for flag in flags if flag]

    objects = []
    for name, source in units.items():
        source_path = work / f"unit_{name}.c"
        source_path.write_text(source, encoding="utf-8")
        object_path = work / f"unit_{name}.o"
        command = [CC, *flags, f"-D{meta_function}=fn_{name}", "-c", str(source_path), "-o", str(object_path)]
        _run_compiler(command)
        objects.append(str(object_path))

    binary = work / "bench"
    command = [CC, *flags, str(harness / "bench.c"), *objects, "-o", str(binary), "-lm"]
    _run_compiler(command)
    build_c.last_command = " ".join(command)
    return binary


def _function_name(harness: Path) -> str:
    import yaml

    meta = yaml.safe_load((harness / "meta.yml").read_text(encoding="utf-8"))
    return meta["function"]


def _run_compiler(command: list[str]) -> None:
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=COMPILE_TIMEOUT_S, check=False
    )
    if completed.returncode != 0:
        match = ERROR_LINE.search(completed.stderr)
        raise CompileError(completed.stderr, int(match.group(1)) if match else None)
```

Убедиться, что `shutil` не остался неиспользованным импортом — убрать его, если так.

- [ ] **Step 5: Написать `jobs.py`**

```python
import json
import os
import tempfile
from pathlib import Path

import yaml

from app.build import CompileError, build_c
from app.measure import ab_result, verdict
from app.sandbox import run

CONTENT_ROOT = Path(os.environ.get("CONTENT_ROOT", "/content"))
WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/work"))
MEMORY_MB = int(os.environ.get("BENCH_MEMORY_MB", "2048"))


def load_meta(harness_dir: str) -> tuple[Path, dict]:
    path = Path(harness_dir)
    if not path.is_absolute() and not path.exists():
        path = CONTENT_ROOT / harness_dir
    meta = yaml.safe_load((path / "meta.yml").read_text(encoding="utf-8"))
    return path, meta


def run_job(job: dict) -> dict:
    harness, meta = load_meta(job["harness_dir"])
    timeout_s = float(job.get("timeout_s", meta.get("timeout_s", 30)))
    sizes = meta.get("sizes", [1024])
    defines = {
        "BENCH_WARMUP": meta.get("warmup", 3),
        "BENCH_REPEATS": meta.get("repeats", 11),
        "BENCH_SIZES": "{" + ",".join(str(s) for s in sizes) + "}",
        "BENCH_NSIZES": len(sizes),
    }

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK_ROOT) as tmp:
        work = Path(tmp)
        try:
            binary = build_c(work, harness, job["units"], meta.get("cflags", ["-O3"]), defines)
        except CompileError as exc:
            return {
                "status": "compile_error",
                "message": "Код не скомпилировался",
                "log": exc.log,
                "line": exc.line,
            }

        proc = run([str(binary)], work, timeout_s=timeout_s, memory_mb=MEMORY_MB)
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

        payload = json.loads(proc.stdout.strip().splitlines()[-1])

    stats = ab_result(payload["samples"], payload["check"], float(meta.get("tolerance", 1e-9)))
    result = {
        "status": "ok",
        "compile_command": build_c.last_command,
        "stdout": "",
        "stderr": proc.stderr[-4000:],
        **stats,
    }
    if job["mode"] == "exercise":
        result["passed"] = verdict(stats["speedup"], stats["correct"], job["target"])
    return result
```

- [ ] **Step 6: Запустить тесты и убедиться, что они проходят**

Run: `make test-runner`
Expected: PASS. Если `test_faster_correct_solution_passes` даёт `speedup` около 1.0 — значит компилятор сам развернул медленный вариант; увеличить `sizes` в фикстуре до `[2000000]`, чтобы промахи кэша были заметны.

- [ ] **Step 7: Коммит**

```bash
git add runner/app/build.py runner/app/jobs.py runner/tests
git commit -m "Runner: сборка C с переименованием функций и A/B-прогон с вердиктом"
```

---

### Task 8: Runner — режим sweep

**Files:**
- Modify: `runner/app/jobs.py`
- Create: `runner/tests/fixtures/harness/sweeptest/meta.yml`, `runner/tests/fixtures/harness/sweeptest/bench.c`
- Test: `runner/tests/test_jobs_sweep.py`

**Interfaces:**
- Consumes: `build_c`, `sandbox.run`.
- Produces: `run_job` для `meta.kind == "sweep"` возвращает `{"status": "ok", "series": [{"size": int, "ms": float, "ms_per_element": float}], "compile_command": str}`.

- [ ] **Step 1: Создать фикстуру sweep-харнесса**

`runner/tests/fixtures/harness/sweeptest/meta.yml`:

```yaml
kind: sweep
lang: c
function: walk
cflags: ["-O2"]
sizes: [1024, 4096, 16384]
warmup: 2
repeats: 5
timeout_s: 30
tolerance: 1e-9
```

`runner/tests/fixtures/harness/sweeptest/bench.c`:

```c
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const double *data, int n);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static int cmp(const void *x, const void *y) {
    double a = *(const double *)x, b = *(const double *)y;
    return (a > b) - (a < b);
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    double sink = 0;
    printf("{\"series\":[");
    for (int s = 0; s < BENCH_NSIZES; s++) {
        int n = sizes[s];
        double *data = malloc((size_t)n * sizeof(double));
        for (int i = 0; i < n; i++) data[i] = (double)(i % 13);

        for (int w = 0; w < BENCH_WARMUP; w++) sink += fn_a(data, n);

        double times[BENCH_REPEATS];
        for (int r = 0; r < BENCH_REPEATS; r++) {
            double t0 = now_ms(); sink += fn_a(data, n); times[r] = now_ms() - t0;
        }
        qsort(times, BENCH_REPEATS, sizeof(double), cmp);
        double ms = times[BENCH_REPEATS / 2];
        printf("%s{\"size\":%d,\"ms\":%.6f,\"ms_per_element\":%.12f}", s ? "," : "", n, ms, ms / n);
        free(data);
    }
    printf("],\"sink\":%.17g}\n", sink);
    return 0;
}
```

Фикстурный сниппет `runner/tests/fixtures/snippets/sweeptest_walk.c`:

```c
double walk(const double *data, int n) {
    double s = 0;
    for (int rep = 0; rep < 64; rep++)
        for (int i = 0; i < n; i++) s += data[i];
    return s;
}
```

- [ ] **Step 2: Написать падающий тест**

`runner/tests/test_jobs_sweep.py`:

```python
from app.jobs import run_job


def test_sweep_returns_series_for_each_size():
    with open("tests/fixtures/snippets/sweeptest_walk.c", encoding="utf-8") as handle:
        code = handle.read()

    result = run_job(
        {
            "mode": "benchmark",
            "lang": "c",
            "harness_dir": "tests/fixtures/harness/sweeptest",
            "units": {"a": code},
            "timeout_s": 30,
        }
    )

    assert result["status"] == "ok"
    assert [point["size"] for point in result["series"]] == [1024, 4096, 16384]
    assert all(point["ms_per_element"] > 0 for point in result["series"])
    assert "speedup" not in result
```

- [ ] **Step 3: Запустить тест и убедиться, что он падает**

Run: `make test-runner`
Expected: FAIL — `KeyError: 'b'` либо `KeyError: 'samples'`

- [ ] **Step 4: Развести режимы в `run_job`**

В `jobs.py` после парсинга `payload` разделить обработку по `meta["kind"]`:

```python
        payload = json.loads(proc.stdout.strip().splitlines()[-1])

    if meta.get("kind", "ab") == "sweep":
        return {
            "status": "ok",
            "compile_command": build_c.last_command,
            "series": payload["series"],
        }

    stats = ab_result(...)
```

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `make test-runner`
Expected: PASS, включая тесты из Task 7

- [ ] **Step 6: Коммит**

```bash
git add runner/app/jobs.py runner/tests
git commit -m "Runner: режим sweep для лестницы кэша"
```

---

### Task 9: Runner — исполнение Python и HTTP-эндпоинт

**Files:**
- Modify: `runner/app/jobs.py`, `runner/app/main.py`
- Create: `runner/tests/fixtures/harness/pytest_sum/meta.yml`, `runner/tests/fixtures/harness/pytest_sum/bench.py`
- Test: `runner/tests/test_jobs_python.py`, `runner/tests/test_run_endpoint.py`

**Interfaces:**
- Consumes: `run_job`.
- Produces: `POST /run` в runner, принимающий job и возвращающий результат; поддержка `lang: "python"` в `run_job`.

- [ ] **Step 1: Создать Python-харнесс фикстуры**

`runner/tests/fixtures/harness/pytest_sum/meta.yml`:

```yaml
kind: ab
lang: python
function: total
sizes: [200000]
warmup: 1
repeats: 5
timeout_s: 60
tolerance: 1e-9
```

`runner/tests/fixtures/harness/pytest_sum/bench.py`:

```python
import json
import os
import time

import numpy as np

import unit_a
import unit_b

WARMUP = int(os.environ["BENCH_WARMUP"])
REPEATS = int(os.environ["BENCH_REPEATS"])
SIZES = [int(s) for s in os.environ["BENCH_SIZES"].split(",")]


def main() -> None:
    data = np.arange(SIZES[0], dtype=np.float64) % 17 * 0.5
    fn_a, fn_b = unit_a.total, unit_b.total

    check_a = check_b = 0.0
    for _ in range(WARMUP):
        check_a, check_b = fn_a(data), fn_b(data)

    samples = []
    for _ in range(REPEATS):
        t0 = time.perf_counter(); check_a = fn_a(data); t1 = time.perf_counter()
        t2 = time.perf_counter(); check_b = fn_b(data); t3 = time.perf_counter()
        samples.append({"a": (t1 - t0) * 1e3, "b": (t3 - t2) * 1e3})

    print(json.dumps({"samples": samples, "check": {"a": float(check_a), "b": float(check_b)}}))


main()
```

Фикстурные сниппеты `runner/tests/fixtures/snippets/pysum_slow.py`:

```python
def total(data):
    s = 0.0
    for x in data:
        s += float(x)
    return s
```

и `runner/tests/fixtures/snippets/pysum_fast.py`:

```python
def total(data):
    return float(data.sum())
```

- [ ] **Step 2: Написать падающие тесты**

`runner/tests/test_jobs_python.py`:

```python
from app.jobs import run_job


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def test_numpy_beats_python_loop():
    result = run_job(
        {
            "mode": "exercise",
            "lang": "python",
            "harness_dir": "tests/fixtures/harness/pytest_sum",
            "units": {"a": read("pysum_slow.py"), "b": read("pysum_fast.py")},
            "target": {"metric": "speedup", "op": ">=", "value": 10},
        }
    )

    assert result["status"] == "ok"
    assert result["correct"] is True
    assert result["passed"] is True


def test_python_syntax_error_is_reported():
    result = run_job(
        {
            "mode": "exercise",
            "lang": "python",
            "harness_dir": "tests/fixtures/harness/pytest_sum",
            "units": {"a": read("pysum_slow.py"), "b": "def total(data)\n    return 1\n"},
            "target": {"metric": "speedup", "op": ">=", "value": 10},
        }
    )

    assert result["status"] == "runtime_error"
    assert "SyntaxError" in result["log"]
```

`runner/tests/test_run_endpoint.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def test_run_endpoint_returns_result():
    client = TestClient(app)

    response = client.post(
        "/run",
        json={
            "mode": "exercise",
            "lang": "c",
            "harness_dir": "tests/fixtures/harness/sumtest",
            "units": {"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")},
            "target": {"metric": "speedup", "op": ">=", "value": 1.2},
            "timeout_s": 30,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 3: Запустить тесты и убедиться, что они падают**

Run: `make test-runner`
Expected: FAIL — Python-путь не реализован, `/run` возвращает 404

- [ ] **Step 4: Реализовать Python-путь и эндпоинт**

В `jobs.py` вынести подготовку и разветвить по `job["lang"]`:

```python
def _prepare_python(work: Path, harness: Path, units: dict[str, str], meta: dict) -> tuple[list[str], dict]:
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
```

Добавить в шапку `jobs.py` недостающие импорты: `import shutil` и `import sys`.

`OMP_NUM_THREADS=1` обязателен: без него NumPy с OpenBLAS уводит замер в многопоточность и урок про память превращается в урок про потоки.

Структура `run_job` после этой задачи — сначала развилка по языку, потом общий разбор результата:

```python
        if job["lang"] == "python":
            command, env = _prepare_python(work, harness, job["units"], meta)
            compile_command = None
        else:
            try:
                binary = build_c(work, harness, job["units"], meta.get("cflags", ["-O3"]), defines)
            except CompileError as exc:
                return {"status": "compile_error", "message": "Код не скомпилировался",
                        "log": exc.log, "line": exc.line}
            command, env = [str(binary)], None
            compile_command = build_c.last_command

        proc = run(command, work, timeout_s=timeout_s, memory_mb=MEMORY_MB, env=env)
```

Дальше `compile_command` кладётся в результат вместо `build_c.last_command`.
Обращаться к `build_c.last_command` на Python-пути нельзя: атрибут там не выставлен,
и получится `AttributeError` вместо результата замера.

Синтаксическая ошибка в коде студента на Python всплывает при импорте, то есть как
ненулевой код возврата — ветка `runtime_error` с `log` из stderr, где `SyntaxError`
уже указывает строку.

`runner/app/main.py`:

```python
from fastapi import FastAPI

from app.jobs import run_job

app = FastAPI(title="Runner")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run(job: dict) -> dict:
    return run_job(job)
```

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `make test-runner`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add runner/app runner/tests
git commit -m "Runner: исполнение Python-заданий и HTTP-эндпоинт /run"
```

---

### Task 10: web → runner: разрешение блока в job

**Files:**
- Create: `web/app/jobs.py`
- Modify: `web/app/main.py`
- Test: `web/tests/test_api_run.py`

**Interfaces:**
- Consumes: `Section`, `Block`, `render_section`.
- Produces: `build_job(section, block, code) -> dict`; `POST /api/run` с телом `{"section": str, "block": str, "code": str}`, проксирующий job на `RUNNER_URL`.

`build_job` обязан:
- для `exercise` — положить в `units["a"]` содержимое `starter`, в `units["b"]` код студента, распарсить `target: "speedup >= 3"` в `{"metric": "speedup", "op": ">=", "value": 3.0}`;
- для `benchmark` — положить в `units["a"]` и `units["b"]` содержимое двух вариантов, `mode="benchmark"`, `target=None`;
- для `sandbox` — `units["a"]` = код студента, `mode="sandbox"`;
- собрать `harness_dir` как `<имя папки раздела>/harness/<harness>` относительно `CONTENT_ROOT` (то есть в терминах пути внутри `content/`, одинакового для обоих контейнеров). **Именно имя папки (`section.dir.name`, например `01-cpu-cache`), а не `section.id`**: папка несёт числовой префикс порядка, а `id` — нет, и runner резолвит путь от корня контента по имени папки.

Важно: `web` монтирует контент в `/app/content`, а `runner` — в `/content`. Поэтому `harness_dir` передаётся **относительным** путём от корня контента, а не абсолютным.

- [ ] **Step 1: Написать падающие тесты**

`web/tests/test_api_run.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app import main
from app.content import load_section
from app.jobs import build_job, parse_target
from app.render import render_section

SECTION = """---
id: demo
title: Демо
order: 10
---

```exercise id=col-sum lang=c
title: Ускорь обход
target: speedup >= 3
starter: snippets/sum_starter.c
reference: snippets/sum_ref.c
harness: sum
```

```benchmark id=rows-vs-cols lang=c
harness: sum
variants: [rows, cols]
```
"""


@pytest.fixture
def section(tmp_path):
    directory = tmp_path / "01-demo"
    (directory / "snippets").mkdir(parents=True)
    (directory / "harness" / "sum").mkdir(parents=True)
    (directory / "harness" / "sum" / "meta.yml").write_text("kind: ab\nlang: c\nfunction: f\n")
    for name, text in [
        ("sum_starter.c", "// starter\n"),
        ("sum_ref.c", "// ref\n"),
        ("sum_rows.c", "// rows\n"),
        ("sum_cols.c", "// cols\n"),
    ]:
        (directory / "snippets" / name).write_text(text)
    (directory / "section.md").write_text(SECTION, encoding="utf-8")
    return load_section(directory)


def blocks_of(section):
    _, blocks = render_section(section)
    return {block.id: block for block in blocks}


def test_parse_target():
    assert parse_target("speedup >= 3") == {"metric": "speedup", "op": ">=", "value": 3.0}


def test_exercise_job_uses_starter_as_baseline(section):
    block = blocks_of(section)["col-sum"]

    job = build_job(section, block, "// студент\n")

    assert job["mode"] == "exercise"
    assert job["lang"] == "c"
    assert job["harness_dir"] == "01-demo/harness/sum"
    assert job["units"]["a"] == "// starter\n"
    assert job["units"]["b"] == "// студент\n"
    assert job["target"]["value"] == 3.0


def test_benchmark_job_uses_two_variants(section):
    block = blocks_of(section)["rows-vs-cols"]

    job = build_job(section, block, "")

    assert job["mode"] == "benchmark"
    assert job["units"] == {"a": "// rows\n", "b": "// cols\n"}
    assert job.get("target") is None


def test_api_run_proxies_to_runner(tmp_path, monkeypatch, section):
    monkeypatch.setenv("CONTENT_ROOT", str(section.dir.parent))
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["job"] = json

        class Response:
            status_code = 200

            def json(self):
                return {"status": "ok", "speedup": 3.4, "passed": True}

        return Response()

    monkeypatch.setattr(main.httpx, "post", fake_post)
    client = TestClient(main.app)

    response = client.post(
        "/api/run", json={"section": "demo", "block": "col-sum", "code": "// студент\n"}
    )

    assert response.status_code == 200
    assert response.json()["passed"] is True
    assert captured["job"]["units"]["b"] == "// студент\n"


def test_api_run_unknown_block_returns_404(tmp_path, monkeypatch, section):
    monkeypatch.setenv("CONTENT_ROOT", str(section.dir.parent))
    client = TestClient(main.app)

    response = client.post("/api/run", json={"section": "demo", "block": "nope", "code": ""})

    assert response.status_code == 404
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `make test-web`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.jobs'`

- [ ] **Step 3: Написать `web/app/jobs.py`**

```python
import re

from app.content import Block, ContentError, Section

TARGET = re.compile(r"^\s*(?P<metric>\w+)\s*(?P<op>>=|>)\s*(?P<value>[\d.]+)\s*$")


def parse_target(text: str) -> dict:
    match = TARGET.match(text)
    if not match:
        raise ContentError(f"Не разобралась цель задания: {text!r}. Ожидается вид 'speedup >= 3'")
    return {
        "metric": match.group("metric"),
        "op": match.group("op"),
        "value": float(match.group("value")),
    }


def build_job(section: Section, block: Block, code: str) -> dict:
    harness = block.params.get("harness")
    job = {
        "mode": block.kind,
        "lang": block.lang,
        # Имя папки, а не section.id: папка несёт префикс порядка (01-cpu-cache),
        # и именно от него runner резолвит путь внутри CONTENT_ROOT.
        "harness_dir": f"{section.dir.name}/harness/{harness}" if harness else None,
    }

    if block.kind == "exercise":
        job["units"] = {"a": block.params["starter_code"], "b": code}
        job["target"] = parse_target(str(block.params["target"]))
    elif block.kind == "benchmark":
        if "source" in block.params:
            # sweep-харнесс: одна реализация, много размеров — второй юнит не нужен
            job["units"] = {"a": (section.dir / block.params["source"]).read_text(encoding="utf-8")}
        else:
            sources = [
                (section.dir / "snippets" / name).read_text(encoding="utf-8")
                for name in block.params["variant_sources"]
            ]
            job["units"] = {"a": sources[0], "b": sources[1]}
        job["target"] = None
    elif block.kind == "sandbox":
        job["units"] = {"a": code}
        job["target"] = None
    else:
        raise ContentError(f"Блок {block.kind} не запускается")

    return job
```

Добавить в тесты Task 10 проверку sweep-ветки:

```python
def test_sweep_benchmark_job_has_single_unit(tmp_path, section_with_sweep):
    block = blocks_of(section_with_sweep)["ladder"]

    job = build_job(section_with_sweep, block, "")

    assert list(job["units"]) == ["a"]
```

Фикстура `section_with_sweep` строится так же, как `section`, но с харнессом
`kind: sweep`, блоком `benchmark id=ladder harness: stride source: snippets/walk.c`
и файлом `snippets/walk.c`.

- [ ] **Step 4: Добавить `/api/run` в `web/app/main.py`**

```python
import httpx
from pydantic import BaseModel

from app.jobs import build_job

RUNNER_URL = os.environ.get("RUNNER_URL", "http://runner:8000")
RUN_TIMEOUT_S = 120


class RunRequest(BaseModel):
    section: str
    block: str
    code: str = ""


@app.post("/api/run")
def api_run(request: RunRequest) -> dict:
    section = find_section(request.section)
    _, blocks = render_section(section)
    block = next((b for b in blocks if b.id == request.block), None)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Блок {request.block} не найден")

    job = build_job(section, block, request.code)
    response = httpx.post(f"{RUNNER_URL}/run", json=job, timeout=RUN_TIMEOUT_S)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Runner недоступен")
    return response.json()
```

- [ ] **Step 5: Запустить тесты и убедиться, что они проходят**

Run: `make test-web`
Expected: PASS, 6 тестов

- [ ] **Step 6: Коммит**

```bash
git add web/app/jobs.py web/app/main.py web/tests/test_api_run.py
git commit -m "Разрешение блока в job и проксирование запусков в runner"
```

---

### Task 11: Фронтенд — редактор, запуск, результат, прогресс

**Files:**
- Modify: `web/static/app.js`, `web/static/style.css`
- Create: `web/static/blocks/exercise.js`, `web/static/blocks/benchmark.js`, `web/static/blocks/sandbox.js`, `web/static/progress.js`
- Test: ручная проверка по чек-листу (браузерных тестов в проекте нет; логика на фронте тонкая, вся проверяемая логика живёт на сервере)

**Interfaces:**
- Consumes: разметку `<div class="block" data-kind data-id data-lang data-params>` из Task 3; `POST /api/run`.
- Produces: `mountBlock(element)` в `app.js`, регистрирующий обработчики по `data-kind`; `progress.js` с `markDone(sectionId, blockId)` и `isDone(sectionId, blockId)` поверх `localStorage`.

- [ ] **Step 1: Написать `progress.js`**

```javascript
const KEY = "course.progress";

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}");
  } catch {
    return {};
  }
}

export function markDone(sectionId, blockId) {
  const state = read();
  state[sectionId] = { ...(state[sectionId] || {}), [blockId]: true };
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* приватный режим: прогресс просто не сохранится */
  }
}

export function isDone(sectionId, blockId) {
  return Boolean(read()[sectionId]?.[blockId]);
}
```

`localStorage` обёрнут в try/catch намеренно: в приватном окне обращение к нему бросает, и страница не должна из-за этого падать.

- [ ] **Step 2: Написать `app.js`**

```javascript
import { mountExercise } from "./blocks/exercise.js";
import { mountBenchmark } from "./blocks/benchmark.js";
import { mountSandbox } from "./blocks/sandbox.js";

const MOUNTERS = {
  exercise: mountExercise,
  benchmark: mountBenchmark,
  sandbox: mountSandbox,
};

export async function run(sectionId, blockId, code) {
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section: sectionId, block: blockId, code }),
  });
  if (!response.ok) throw new Error(`Сервер ответил ${response.status}`);
  return response.json();
}

document.addEventListener("DOMContentLoaded", async () => {
  const sectionId = document.querySelector(".section")?.dataset.section;
  if (!sectionId) return;

  for (const element of document.querySelectorAll(".block")) {
    const params = JSON.parse(element.dataset.params || "{}");
    const mount = MOUNTERS[element.dataset.kind];
    if (mount) {
      mount(element, { sectionId, blockId: element.dataset.id, lang: element.dataset.lang, params });
    } else if (element.dataset.kind === "viz") {
      const module = await import(`./viz/${element.dataset.id}.js`);
      module.mount(element, params);
    }
  }

  if (window.renderMathInElement) {
    window.renderMathInElement(document.querySelector("main"), {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
    });
  }
});
```

- [ ] **Step 3: Написать `blocks/exercise.js`**

Требования к поведению:

- заголовок задания (`params.title`) и цель (`params.target`) выводятся текстом;
- редактор Ace, режим `ace/mode/c_cpp` для `lang === "c"` и `ace/mode/python` для `python`, тема по `prefers-color-scheme`, начальное содержимое `params.starter_code`;
- кнопка «Проверить» шлёт `run(...)`, на время запроса блокируется и показывает «Считаю замеры…»;
- результат `status: "ok"` показывает: время baseline, время решения, ускорение с двумя знаками, разброс в процентах, вердикт («Зачёт» / «Пока нет: нужно ≥ N, получилось M»), команду компиляции в свёрнутом `<details>`;
- `status: "compile_error"` показывает сообщение, номер строки и лог; `status: "timeout"` и `runtime_error` — своё сообщение;
- при `passed === true` вызывается `markDone(sectionId, blockId)` и блок помечается классом `is-done`;
- при загрузке страницы `isDone(...)` восстанавливает пометку;
- кнопка «Вернуть исходный код» возвращает `params.starter_code`.

```javascript
import { run } from "../app.js";
import { isDone, markDone } from "../progress.js";

export function mountExercise(element, { sectionId, blockId, lang, params }) {
  element.innerHTML = `
    <h3 class="block-title">${params.title}</h3>
    <p class="block-goal">Цель: <code>${params.target}</code></p>
    <div class="editor"></div>
    <div class="controls">
      <button class="run">Проверить</button>
      <button class="reset" type="button">Вернуть исходный код</button>
    </div>
    <div class="result" aria-live="polite"></div>`;

  const editor = ace.edit(element.querySelector(".editor"), {
    mode: lang === "python" ? "ace/mode/python" : "ace/mode/c_cpp",
    theme: matchMedia("(prefers-color-scheme: dark)").matches
      ? "ace/theme/github_dark"
      : "ace/theme/github",
    value: params.starter_code,
    minLines: 12,
    maxLines: 40,
    fontSize: 14,
  });

  if (isDone(sectionId, blockId)) element.classList.add("is-done");

  const result = element.querySelector(".result");
  const button = element.querySelector(".run");

  element.querySelector(".reset").addEventListener("click", () => {
    editor.setValue(params.starter_code, -1);
  });

  button.addEventListener("click", async () => {
    button.disabled = true;
    result.textContent = "Считаю замеры…";
    try {
      const data = await run(sectionId, blockId, editor.getValue());
      result.innerHTML = renderResult(data);
      if (data.passed) {
        markDone(sectionId, blockId);
        element.classList.add("is-done");
      }
    } catch (error) {
      result.textContent = `Не получилось запустить: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
}

function renderResult(data) {
  if (data.status === "compile_error") {
    return `<p class="bad">Код не скомпилировался${data.line ? `, строка ${data.line}` : ""}.</p>
            <pre>${escapeHtml(data.log || "")}</pre>`;
  }
  if (data.status !== "ok") {
    return `<p class="bad">${escapeHtml(data.message || "Неизвестная ошибка")}</p>
            ${data.log ? `<pre>${escapeHtml(data.log)}</pre>` : ""}`;
  }
  const verdict = data.passed
    ? `<p class="good">Зачёт: ускорение ${data.speedup.toFixed(2)}×</p>`
    : data.correct === false
      ? `<p class="bad">Результат не совпадает с эталонным — оптимизация что-то сломала.</p>`
      : `<p class="bad">Пока нет: ускорение ${data.speedup.toFixed(2)}×.</p>`;
  return `${verdict}
    <table class="numbers">
      <tr><td>baseline</td><td>${data.baseline_ms.toFixed(3)} мс</td></tr>
      <tr><td>ваш код</td><td>${data.student_ms.toFixed(3)} мс</td></tr>
      <tr><td>разброс замеров</td><td>${data.spread_pct.toFixed(1)} %</td></tr>
    </table>
    ${data.compile_command ? `<details><summary>Как это скомпилировано</summary><pre>${escapeHtml(data.compile_command)}</pre></details>` : ""}`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
```

- [ ] **Step 4: Написать `blocks/sandbox.js`**

То же самое, но без цели, вердикта и baseline: кнопка «Запустить», вывод `stdout`/`stderr` и времени.

- [ ] **Step 5: Проверить вручную**

Run: `docker compose up --build`, открыть `localhost:18080`
Expected: пока разделов нет — пустое оглавление без ошибок в консоли браузера. Полная проверка редактора произойдёт в Task 13, когда появится первое задание.

- [ ] **Step 6: Коммит**

```bash
git add web/static
git commit -m "Фронтенд: редактор Ace, запуск заданий, вывод замеров, прогресс в localStorage"
```

---

### Task 12: Фронтенд — график лестницы и анимация обхода

**Files:**
- Create: `web/static/blocks/benchmark.js`, `web/static/viz/stride-walk.js`
- Modify: `web/static/style.css`

**Interfaces:**
- Consumes: `run()` из `app.js`; ответ runner'а с полем `series` (Task 8) либо с A/B-полями (Task 7).
- Produces: `mountBenchmark(element, ctx)`, `mount(element, params)` в `viz/stride-walk.js`.

- [ ] **Step 1: Написать `blocks/benchmark.js`**

Поведение:

- кнопка «Замерить»;
- если ответ содержит `series` — рисуется график uPlot: ось X логарифмическая по размеру рабочего множества в килобайтах, ось Y — наносекунды на элемент; под графиком подпись «Излом кривой — граница уровня кэша»;
- если ответ содержит `baseline_ms`/`student_ms` — рисуется таблица двух вариантов с их именами из `params.variants` и отношением времён;
- ошибки выводятся так же, как в `exercise.js`.

```javascript
import { run } from "../app.js";

export function mountBenchmark(element, { sectionId, blockId, params }) {
  element.innerHTML = `
    <div class="controls"><button class="run">Замерить</button></div>
    <div class="result" aria-live="polite"></div>
    <div class="chart"></div>`;

  const button = element.querySelector(".run");
  const result = element.querySelector(".result");
  const chart = element.querySelector(".chart");

  button.addEventListener("click", async () => {
    button.disabled = true;
    result.textContent = "Считаю замеры…";
    try {
      const data = await run(sectionId, blockId, "");
      if (data.status !== "ok") {
        result.textContent = data.message || "Ошибка запуска";
        return;
      }
      if (data.series) {
        result.textContent = "Излом кривой — граница уровня кэша.";
        drawSweep(chart, data.series);
      } else {
        result.innerHTML = renderPair(data, params.variants);
      }
    } catch (error) {
      result.textContent = `Не получилось запустить: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
}

function drawSweep(container, series) {
  container.innerHTML = "";
  const kb = series.map((p) => (p.size * 8) / 1024);
  const nsPerElement = series.map((p) => p.ms_per_element * 1e6);
  new uPlot(
    {
      width: container.clientWidth || 640,
      height: 280,
      scales: { x: { distr: 3 }, y: { distr: 3 } },
      axes: [{ label: "рабочее множество, КБ" }, { label: "нс на элемент" }],
      series: [{}, { label: "время", stroke: "#2f6feb", width: 2, points: { show: true } }],
    },
    [kb, nsPerElement],
    container
  );
}

function renderPair(data, variants) {
  const [first, second] = variants || ["вариант A", "вариант B"];
  return `<table class="numbers">
    <tr><td>${first}</td><td>${data.baseline_ms.toFixed(3)} мс</td></tr>
    <tr><td>${second}</td><td>${data.student_ms.toFixed(3)} мс</td></tr>
    <tr><td>отношение</td><td>${data.speedup.toFixed(2)}×</td></tr>
    <tr><td>разброс</td><td>${data.spread_pct.toFixed(1)} %</td></tr>
  </table>`;
}
```

- [ ] **Step 2: Написать `viz/stride-walk.js`**

Анимация на `<canvas>`: сетка N×N, два режима — обход по строкам и по столбцам, переключатель и кнопка «пуск/пауза». Подсвечивается текущая ячейка и **вся кэш-линия**, которая была подтянута вместе с ней (восемь соседних `double` по горизонтали). Смысл картинки: при обходе по строкам подтянутая линия используется целиком, при обходе по столбцам — из восьми значений используется одно, а остальные вытесняются раньше, чем понадобятся.

```javascript
const CELL = 14;
const LINE = 8; // сколько double влезает в кэш-линию 64 байта

export function mount(element, params) {
  const n = params.size || 24;
  element.innerHTML = `
    <div class="controls">
      <label><input type="radio" name="order" value="rows" checked> по строкам</label>
      <label><input type="radio" name="order" value="cols"> по столбцам</label>
      <button class="toggle" type="button">Пауза</button>
    </div>
    <canvas width="${n * CELL + 1}" height="${n * CELL + 1}"></canvas>
    <p class="viz-note"></p>`;

  const canvas = element.querySelector("canvas");
  const context = canvas.getContext("2d");
  const note = element.querySelector(".viz-note");
  let index = 0;
  let running = true;
  let order = "rows";

  element.querySelectorAll("input[name=order]").forEach((input) =>
    input.addEventListener("change", () => {
      order = input.value;
      index = 0;
    })
  );
  element.querySelector(".toggle").addEventListener("click", (event) => {
    running = !running;
    event.target.textContent = running ? "Пауза" : "Продолжить";
  });

  function draw() {
    const row = order === "rows" ? Math.floor(index / n) : index % n;
    const col = order === "rows" ? index % n : Math.floor(index / n);
    const lineStart = Math.floor(col / LINE) * LINE;

    context.clearRect(0, 0, canvas.width, canvas.height);
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const inLine = i === row && j >= lineStart && j < lineStart + LINE;
        context.fillStyle = i === row && j === col ? "#2f6feb" : inLine ? "#bcd2f7" : "#e9e9ec";
        context.fillRect(j * CELL, i * CELL, CELL - 1, CELL - 1);
      }
    }
    note.textContent =
      order === "rows"
        ? "Обход по строкам: подтянутая кэш-линия используется целиком — восемь значений на один поход в память."
        : "Обход по столбцам: из восьми подтянутых значений используется одно, остальные вытесняются раньше, чем понадобятся.";

    if (running) index = (index + 1) % (n * n);
    requestAnimationFrame(draw);
  }

  draw();
}
```

- [ ] **Step 3: Проверить вручную**

Run: `docker compose up --build`
Expected: страница загружается, ошибок в консоли нет. Полная проверка — в Task 16, когда viz попадёт в раздел.

- [ ] **Step 4: Коммит**

```bash
git add web/static
git commit -m "Фронтенд: график лестницы кэша на uPlot и анимация обхода матрицы"
```

---

### Task 13: Контент — харнесс matrix_sum, задание 1, проверка материала

**Files:**
- Create: `content/01-cpu-cache/section.md` (черновой, только этот блок)
- Create: `content/01-cpu-cache/harness/matrix_sum/{meta.yml,bench.c}`
- Create: `content/01-cpu-cache/snippets/{matrix_sum_starter.c,matrix_sum_ref.c}`
- Create: `web/tests/test_content_targets.py`
- Test: `make verify-content`

**Interfaces:**
- Consumes: всё из задач 1–12.
- Produces: рабочее задание `col-sum`; тест-проверку материала, применимую ко всем будущим заданиям.

Сигнатура: `double matrix_sum(const double *a, int n)` — сумма всех элементов матрицы `n × n`, лежащей построчно. Стартовый код обходит по столбцам, эталон — по строкам; результат один и тот же, время различается.

- [ ] **Step 1: Написать харнесс**

`content/01-cpu-cache/harness/matrix_sum/meta.yml`:

```yaml
kind: ab
lang: c
function: matrix_sum
cflags: ["-O3"]
sizes: [2048]
warmup: 2
repeats: 11
timeout_s: 60
tolerance: 1e-9
```

`content/01-cpu-cache/harness/matrix_sum/bench.c` — как фикстурный `sumtest/bench.c` из Task 7, но данные выделяются как матрица `n × n` (`(size_t)n * n * sizeof(double)`), и в `fn_a`/`fn_b` передаётся `n`.

- [ ] **Step 2: Написать стартовый код и эталон**

`content/01-cpu-cache/snippets/matrix_sum_starter.c`:

```c
/* Суммируем все элементы матрицы n×n, которая лежит в памяти построчно.
   Сейчас обход идёт по столбцам. Результат правильный, а вот скорость — нет. */
double matrix_sum(const double *a, int n) {
    double total = 0.0;
    for (int j = 0; j < n; j++)
        for (int i = 0; i < n; i++)
            total += a[(long)i * n + j];
    return total;
}
```

`content/01-cpu-cache/snippets/matrix_sum_ref.c`:

```c
double matrix_sum(const double *a, int n) {
    double total = 0.0;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            total += a[(long)i * n + j];
    return total;
}
```

- [ ] **Step 3: Написать блок задания в `section.md`**

```markdown
---
id: cpu-cache
title: Память, которую вы уже понимаете
order: 10
---

## Задание: переставьте два цикла

```exercise id=col-sum lang=c
title: Ускорьте суммирование матрицы
target: speedup >= 3
starter: snippets/matrix_sum_starter.c
reference: snippets/matrix_sum_ref.c
harness: matrix_sum
```
```

- [ ] **Step 4: Написать проверку материала**

`web/tests/test_content_targets.py`:

```python
import os
from pathlib import Path

import httpx
import pytest

from app.content import list_sections
from app.jobs import build_job
from app.render import render_section

RUNNER_URL = os.environ.get("RUNNER_URL", "http://runner:8000")
CONTENT_ROOT = Path(os.environ.get("CONTENT_ROOT", "/app/content"))


def exercises():
    for section in list_sections(CONTENT_ROOT):
        _, blocks = render_section(section)
        for block in blocks:
            if block.kind == "exercise":
                yield pytest.param(section, block, id=f"{section.id}/{block.id}")


def execute(section, block, code):
    job = build_job(section, block, code)
    response = httpx.post(f"{RUNNER_URL}/run", json=job, timeout=300)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.content
@pytest.mark.parametrize("section,block", list(exercises()))
def test_reference_solution_reaches_target(section, block):
    reference = (section.dir / block.params["reference"]).read_text(encoding="utf-8")

    result = execute(section, block, reference)

    assert result["status"] == "ok", result
    assert result["correct"] is True
    assert result["passed"] is True, (
        f"Эталон не берёт порог {block.params['target']}: получилось {result['speedup']:.2f}×"
    )


@pytest.mark.content
@pytest.mark.parametrize("section,block", list(exercises()))
def test_starter_code_does_not_reach_target(section, block):
    result = execute(section, block, block.params["starter_code"])

    assert result["status"] == "ok", result
    assert result["passed"] is False, (
        "Стартовый код уже проходит порог — задание ничему не учит"
    )
```

- [ ] **Step 5: Запустить проверку материала**

Run: `make verify-content`
Expected: PASS. Если эталон не берёт `speedup >= 3` — увеличить `sizes` в `meta.yml` (матрица должна заметно превышать последний уровень кэша) и повторить. Если и это не помогает, снизить порог в `section.md` до реально достижимого и записать полученное число в коммит-сообщение.

- [ ] **Step 6: Коммит**

```bash
git add content web/tests/test_content_targets.py
git commit -m "Задание 1: обход матрицы по строкам против столбцов, проверка материала"
```

---

### Task 14: Контент — харнесс matmul, задание 2

**Files:**
- Create: `content/01-cpu-cache/harness/matmul/{meta.yml,bench.c}`
- Create: `content/01-cpu-cache/snippets/{matmul_starter.c,matmul_ref.c}`
- Modify: `content/01-cpu-cache/section.md`
- Test: `make verify-content`

**Interfaces:**
- Consumes: механику Task 13.
- Produces: задание `blocked-matmul` с порогом `speedup >= 2`.

Сигнатура: `double matmul(const double *a, const double *b, int n)` — перемножает две матрицы `n × n` во временный буфер и возвращает контрольную сумму результата. Возврат контрольной суммы вместо записи в выходной буфер выбран специально: так `bench.c` остаётся одинаковым для всех A/B-харнессов, а проверка корректности сравнивает одно число.

- [ ] **Step 1: Написать харнесс и код**

`meta.yml`: `kind: ab`, `function: matmul`, `sizes: [512]`, `repeats: 7`, `timeout_s: 120`, `tolerance: 1e-9`.

`bench.c` выделяет две матрицы `n × n`, заполняет их детерминированно (`(i * 31 + j * 17) % 13 * 0.25`) и вызывает `fn_a`/`fn_b` по A/B-протоколу.

`matmul_starter.c` — наивные три вложенных цикла `i, j, k` с накоплением в локальную переменную и контрольной суммой результата. `matmul_ref.c` — тайлинг по всем трём индексам с размером блока 64, дающий переиспользование данных внутри L1.

Внутри стартового файла — комментарий, объясняющий задачу: «Матрица `b` обходится по столбцам, и на каждый элемент результата вы проходите её целиком. Найдите способ переиспользовать то, что уже лежит в кэше».

- [ ] **Step 2: Добавить блок в `section.md`**

```markdown
```exercise id=blocked-matmul lang=c
title: Умножение матриц, которое помещается в кэш
target: speedup >= 2
starter: snippets/matmul_starter.c
reference: snippets/matmul_ref.c
harness: matmul
```
```

- [ ] **Step 3: Запустить проверку материала**

Run: `make verify-content`
Expected: PASS для обоих заданий. При недостижимом пороге — увеличить `sizes` до 768 или скорректировать порог, как в Task 13.

- [ ] **Step 4: Коммит**

```bash
git add content
git commit -m "Задание 2: блочное умножение матриц"
```

---

### Task 15: Контент — Python, NumPy, ось редукции

**Files:**
- Create: `content/01-cpu-cache/harness/py_reduce/{meta.yml,bench.py}`
- Create: `content/01-cpu-cache/harness/axis/{meta.yml,bench.py}`
- Create: `content/01-cpu-cache/snippets/{py_reduce_starter.py,py_reduce_ref.py,axis_rows.py,axis_cols.py}`
- Modify: `content/01-cpu-cache/section.md`
- Test: `make verify-content`

**Interfaces:**
- Consumes: Python-путь runner'а из Task 9.
- Produces: задание `vectorize` (порог `speedup >= 20`) и бенчмарк `axis-order`.

**Отступление от спеки, сделанное осознанно.** Спека (§7.8) описывала задание 3 как «выбор оси и устранение копий». Порог там получается порядка 2–3×, то есть на уровне шума между машинами, и задание становится лотереей. Поэтому задание 3 — про векторизацию Python-цикла (порог 20× берётся с огромным запасом и устойчив), а урок про ось подаётся отдельным блоком `benchmark`, где число измеряется, а не проверяется. Педагогическая нагрузка обоих пунктов сохранена.

- [ ] **Step 1: Написать харнесс `py_reduce`**

`meta.yml`: `kind: ab`, `lang: python`, `function: reduce_rows`, `sizes: [2000]`, `warmup: 1`, `repeats: 5`, `timeout_s: 180`, `tolerance: 1e-9`.

`bench.py` — как фикстура из Task 9, но данные — двумерный `np.ndarray` формы `(n, n)`, функция возвращает `float`. Обязательно `OMP_NUM_THREADS=1` (устанавливается runner'ом).

`py_reduce_starter.py`:

```python
def reduce_rows(a):
    """Сумма построчных максимумов. Сейчас — честный цикл на Python."""
    total = 0.0
    for i in range(a.shape[0]):
        best = a[i, 0]
        for j in range(a.shape[1]):
            if a[i, j] > best:
                best = a[i, j]
        total += float(best)
    return total
```

`py_reduce_ref.py`:

```python
def reduce_rows(a):
    return float(a.max(axis=1).sum())
```

- [ ] **Step 2: Написать харнесс `axis`**

`kind: ab`, `lang: python`, `function: reduce_axis`, `sizes: [4000]`. Варианты `axis_rows.py` (`a.sum(axis=1)`) и `axis_cols.py` (`a.sum(axis=0)`) — одна и та же арифметика, разный порядок обхода C-непрерывного массива.

Внимание: у этих двух вариантов **разные результаты как векторы**, поэтому обе функции обязаны возвращать сумму получившегося вектора — тогда числа совпадают и проверка корректности проходит.

- [ ] **Step 3: Добавить блоки в `section.md`**

```markdown
```exercise id=vectorize lang=python
title: Уберите цикл, оставьте смысл
target: speedup >= 20
starter: snippets/py_reduce_starter.py
reference: snippets/py_reduce_ref.py
harness: py_reduce
```

```benchmark id=axis-order lang=python
harness: axis
variants: [rows, cols]
```
```

- [ ] **Step 4: Запустить проверку материала**

Run: `make verify-content`
Expected: PASS для трёх заданий. Прогон медленный (Python-цикл по матрице 2000×2000) — это ожидаемо; при выходе за `timeout_s` уменьшить `sizes` до 1200.

- [ ] **Step 5: Коммит**

```bash
git add content
git commit -m "Задание 3: векторизация Python-цикла и бенчмарк порядка обхода в NumPy"
```

---

### Task 16: Контент — текст раздела целиком

**Files:**
- Modify: `content/01-cpu-cache/section.md`
- Create: `content/01-cpu-cache/harness/stride/{meta.yml,bench.c}`, `content/01-cpu-cache/snippets/stride_walk.c`
- Create: `content/01-cpu-cache/harness/prefetch/{meta.yml,bench.c}`, `content/01-cpu-cache/snippets/prefetch_walk.c`
- Create: `content/01-cpu-cache/images/hierarchy.svg`
- Test: ручная проверка + `make verify-content`

**Interfaces:**
- Consumes: все блоки из задач 13–15, `viz/stride-walk.js` из Task 12, sweep-режим из Task 8.
- Produces: законченный раздел из девяти частей.

Порядок частей и их содержание — по спеке §7. Ниже — обязательные элементы каждой части.

- [ ] **Step 1: Написать части 1–3**

Часть 1 «Вы это уже знаете» — прозой, примерно так по тону и плотности:

> Когда вы решаете, класть ли ответ в Redis, вы уже рассуждаете об иерархии памяти. Поход в Postgres — это миллисекунды, попадание в Redis — сотни микросекунд, словарь в памяти процесса — десятки наносекунд. Никто не называет это «оптимизацией под кэш», это просто здравый смысл бэкендера.
>
> Дальше — неприятная новость: ровно такая же лестница существует внутри одного процесса, на шесть порядков ниже, и вы про неё, скорее всего, никогда не думали. Обращение к L1 — примерно секунда, если бы мы жили в масштабе процессора. Поход в оперативную память в том же масштабе — около трёх минут. Между этими двумя случаями в вашем коде нет ни одной видимой строчки разницы: и то и другое выглядит как `a[i]`.

Часть 1 содержит `images/hierarchy.svg` — схема из пяти прямоугольников (регистры, L1, L2, L3/SLC, RAM) с относительными латентностями, подписи на русском, без конкретных размеров кэшей.

Часть 2 «Найдите свой L1» содержит sweep-бенчмарк:

````markdown
```benchmark id=cache-ladder lang=c
harness: stride
source: snippets/stride_walk.c
```
````

Текст обязан просить студента **сначала предсказать** форму кривой, а потом нажать кнопку — иначе график читается как иллюстрация, а не как открытие.

Часть 3 «Кэш-линия» содержит `viz id=stride-walk` и объяснение, почему полки на графике плоские, а между ними — ступеньки.

- [ ] **Step 2: Написать харнесс `stride`**

`meta.yml`: `kind: sweep`, `function: walk`, `sizes: [1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216]`, `repeats: 7`, `timeout_s: 120`. Размеры даны в элементах `double`, то есть от 8 КБ до 128 МБ — диапазон гарантированно перекрывает L1, L2 и последний уровень на любой разумной машине.

`stride_walk.c` — многократный последовательный обход массива с накоплением суммы; число повторов внутри функции подобрано так, чтобы на маленьких размерах замер не тонул в накладных расходах (например, суммарно не менее 10⁸ обращений на каждый размер).

- [ ] **Step 3: Написать части 4–6**

Часть 4 — врезка перед заданием 1: почему перестановка циклов даёт не «немного быстрее», а кратно.
Часть 5 «Префетчер» — второй sweep-бенчмарк на **отдельном** харнессе
`harness/prefetch/` (`kind: sweep`, `function: walk_stride`, `sizes` здесь означают
шаг обхода в элементах: `[1, 2, 4, 8, 16, 32, 64, 128]`, размер массива фиксирован
внутри `bench.c`). Отдельный харнесс нужен потому, что набор точек задаётся в
`meta.yml` и переиспользовать `stride` с другими значениями нельзя. Блок:

````markdown
```benchmark id=prefetch-stride lang=c
harness: prefetch
source: snippets/prefetch_walk.c
```
````

Плюс текст о том, что процессор угадывает предсказуемый паттерн и сдаётся на
случайном. На графике ось X подписывается как шаг в байтах, и выход на плато после
64 байт — это ровно момент, когда на каждый доступ приходится своя кэш-линия.
Часть 6 — врезка перед заданием 2 с подсказкой про то, что размер тайла упирается в измеренный в части 2 объём L1.

- [ ] **Step 4: Написать части 7–9**

Часть 7 — почему чистый Python медленный: объекты в куче, список указателей, отсутствие локальности. Явно отвергнуть объяснение «потому что интерпретируемый».
Часть 8 — `ndarray` как непрерывный блок; задание 3 и бенчмарк `axis-order`.
Часть 9 — вывод: понимание памяти важнее выбора языка; NumPy — это чужая многолетняя работа над кэшем, которой теперь можно пользоваться осознанно; у GPU иерархия та же, только правила жёстче.

- [ ] **Step 5: Проверить целиком**

Run: `docker compose up --build`, пройти раздел от начала до конца в браузере
Expected: все блоки монтируются, sweep рисует кривую с видимыми полками, анимация идёт, три задания решаются эталонными решениями, отметки о прохождении переживают перезагрузку страницы.

Run: `make verify-content && make test`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add content
git commit -m "Раздел «Память, которую вы уже понимаете» целиком"
```

---

## Самопроверка плана

**Покрытие спеки:**

| Раздел спеки | Задача |
| --- | --- |
| §4 архитектура, два сервиса, internal-сеть | 1 |
| §4 структура репозитория | 1, распределена по остальным |
| §5 фронтматтер, оглавление, draft | 2 |
| §5 блоки, связь `variants`/`viz` с файлами, валидация | 3 |
| §5 volume + рендер на запрос | 1 (compose), 4 (маршруты) |
| §6 harness рядом с контентом | 7, 13 |
| §6 прогрев, медиана, A/B | 6, 7 |
| §6 sweep и лестница | 8, 12, 16 |
| §6 вердикт и корректность | 6, 7 |
| §6 лимиты и tmpfs | 5, 1 |
| §6 `-march=native` с фолбэком | 7 |
| §6 команда компиляции студенту | 7, 11 |
| §6 сообщения об ошибках | 7, 11 |
| §6 API `/api/run`, режимы | 9, 10 |
| §6 Python-путь | 9, 15 |
| §7 девять частей раздела | 13–16 |
| §8 тесты парсера | 2, 3 |
| §8 тесты runner'а | 5, 6, 7, 9 |
| §8 тесты материала | 13 |
| §8 smoke | 1, 16 |
| §9 критерии готовности | 16 |

Пробелов не осталось.

**Известные риски, заложенные в план:**

- Пороги 3× и 2× проверяются только на живом железе; в задачах 13 и 14 прописано, что делать, если эталон их не берёт.
- `RLIMIT_NPROC` считается по пользователю, а не по процессу: если runner в контейнере ходит от одного пользователя, лимит может сработать раньше ожидаемого. Тест в Task 5 это поймает — при провале ослабить `MAX_PROCESSES` или отказаться от этого лимита, оставив память и таймаут.
- Ace, uPlot и KaTeX тянутся npm-стадией по мажорным версиям; при мажорном обновлении API имена файлов в `Dockerfile` могут поехать — это сломает сборку явно, а не тихо.
