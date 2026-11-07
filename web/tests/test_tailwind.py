"""Сборка Tailwind и каркас страницы.

app.css собирается в стадии vendor образа web; Tailwind кладёт в него только
утилиты, которые нашёл в исходниках по @source. Если путь в @source сломан
или класс склеен из кусков строки, элемент молча останется без стиля —
поэтому проверяем результат сборки, а не исходник.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main

APP = Path(main.__file__).resolve().parent
STATIC = APP.parent / "static"


@pytest.fixture
def client(tmp_path, monkeypatch):
    directory = tmp_path / "20-demo"
    directory.mkdir(parents=True)
    (directory / "section.md").write_text(
        "---\nid: demo\ntitle: Демо\norder: 10\n---\n\n## Первая\n\n### Подзаголовок\n\nТекст.\n\n## Вторая\n\nЕщё.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_ROOT", str(tmp_path))
    return TestClient(main.app)


def test_app_css_contains_layout_utility(client):
    response = client.get(f"{main.ASSET_PREFIX}/app.css")
    assert response.status_code == 200
    css = response.text.replace("\\", "")
    assert "xl:grid-cols-[260px_minmax(0,1fr)_220px]" in css


def test_no_dynamic_utility_fragments():
    pattern = re.compile(
        r"""["'`](?:bg|text|border|ring|grid-cols|w|h|p|m)-["'`]\s*\+|\b(?:bg|text|border|ring)-\$\{"""
    )
    files = [*STATIC.rglob("*.js"), APP / "render.py"]
    offenders = [str(f) for f in files if "vendor" not in f.parts and pattern.search(f.read_text(encoding="utf-8"))]
    assert offenders == []


def test_center_column_can_shrink(client):
    assert 'class="min-w-0' in client.get("/section/demo").text


def test_headings_have_scroll_margin(client):
    html = client.get("/section/demo").text
    heading = re.search(r'<h2[^>]*id="part-1"[^>]*>', html)
    assert heading and "scroll-mt-20" in heading.group(0)


def test_no_external_urls(client):
    for path in ("/", "/section/demo"):
        assert not re.search(r'(src|href)="(https?:)?//', client.get(path).text)


def test_old_stylesheet_is_gone(client):
    assert "style.css" not in client.get("/section/demo").text
    assert "app.css" in client.get("/section/demo").text


def test_theme_toggle_and_early_theme_script(client):
    html = client.get("/section/demo").text
    assert "data-theme-toggle" in html
    head = html[: html.index("</head>")]
    # Тема выставляется до первой отрисовки, иначе тёмная страница мигает светлой.
    assert "course.theme" in head and "dataset.theme" in head


def test_app_css_supports_manual_theme(client):
    css = client.get(f"{main.ASSET_PREFIX}/app.css").text
    assert '[data-theme="dark"]' in css or "[data-theme=dark]" in css
    assert ':not([data-theme="light"])' in css or ":not([data-theme=light])" in css


def test_light_theme_defines_chart_series(client):
    # Tailwind v4 пишет в :root только переменные @theme, которые где-то
    # используются утилитами; цвета серий читает только JS (theme.js).
    css = client.get(f"{main.ASSET_PREFIX}/app.css").text
    for light in ("--color-series-1:#4f46e5", "--color-series-2:#0d9488", "--color-series-5:#64748b"):
        assert light in css


def test_prose_overrides_skip_not_prose_blocks(client):
    css = client.get(f"{main.ASSET_PREFIX}/app.css").text
    # Последнее вхождение — наши переопределения (они после плагина); у
    # селекторов самого плагина исключение not-prose есть всегда.
    for rule in (".prose :where(table)", ".prose :where(pre)", ".prose :where(code)"):
        start = css.rindex(rule)
        assert "not-prose" in css[start : css.index("{", start)], rule
