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


def test_index_shows_course_contents(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "Разделы курса" in response.text
    assert 'href="/section/demo"' in response.text
    assert "Демо-раздел" in response.text


def test_section_page_renders_markdown(client):
    response = client.get("/section/demo")

    assert response.status_code == 200
    # Заголовок части несёт якорь: на него ссылается боковое оглавление.
    assert '<h2 id="part-1" class="scroll-mt-20"><a class="heading-link" href="#part-1">Привет</a></h2>' in response.text


def test_unknown_section_returns_404(client):
    assert client.get("/section/nope").status_code == 404


def test_page_loads_versioned_styles_and_nested_modules(client):
    response = client.get("/section/demo")
    for asset in ["app.css", "app.js"]:
        assert f'{main.ASSET_PREFIX}/{asset}' in response.text
    for asset in ["app.css", "app.js", "blocks/exercise.js", "blocks/benchmark.js"]:
        assert client.get(f"{main.ASSET_PREFIX}/{asset}").status_code == 200


def test_nested_module_change_invalidates_asset_urls(tmp_path):
    blocks = tmp_path / "blocks"
    blocks.mkdir()
    module = blocks / "tutorial.js"
    module.write_text("old")
    before = main.asset_version(tmp_path)
    module.write_text("new")
    assert main.asset_version(tmp_path) != before


def test_broken_content_returns_500_with_reason(client, tmp_path):
    (tmp_path / "02-broken").mkdir()
    (tmp_path / "02-broken" / "section.md").write_text("нет фронтматтера\n", encoding="utf-8")

    response = client.get("/")

    assert response.status_code == 500
    assert "фронтматтер" in response.text


# ── Навигация между разделами ──────────────────────────────────────────

COURSE = [
    ("01-first", "first", "Первый раздел", 10),
    ("02-middle", "middle", "Средний раздел", 20),
    ("03-last", "last", "Последний раздел", 30),
]


@pytest.fixture
def course(tmp_path, monkeypatch):
    for folder, section_id, title, order in COURSE:
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "section.md").write_text(
            f"---\nid: {section_id}\ntitle: {title}\norder: {order}\n---\n\n## Часть\n\nТекст.\n",
            encoding="utf-8",
        )
    # Черновик не должен попадать ни в список, ни в соседи.
    draft = tmp_path / "04-draft"
    draft.mkdir()
    (draft / "section.md").write_text(
        "---\nid: draft\ntitle: Черновик\norder: 25\ndraft: true\n---\n\n## Часть\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_ROOT", str(tmp_path))
    return TestClient(main.app)


def _course_nav(html: str) -> str:
    start = html.index('<nav id="course-nav"')
    return html[start : html.index("</nav>", start)]


def _section_pager(html: str) -> str | None:
    if '<nav class="section-pager' not in html:
        return None
    start = html.index('<nav class="section-pager')
    return html[start : html.index("</nav>", start)]


@pytest.mark.parametrize("current", ["first", "middle", "last"])
def test_section_page_lists_all_sections_in_order(course, current):
    html = course.get(f"/section/{current}").text
    nav = _course_nav(html)

    positions = [nav.index(f'href="/section/{sid}"') for _, sid, _, _ in COURSE]
    assert positions == sorted(positions)
    for _, _, title, _ in COURSE:
        assert title in nav
    assert "Черновик" not in nav
    assert nav.count('aria-current="page"') == 1
    current_link = nav[: nav.index('aria-current="page"')].rsplit("<a", 1)[1]
    assert f'href="/section/{current}"' in current_link


def test_first_section_has_only_next(course):
    pager = _section_pager(course.get("/section/first").text)
    assert pager is not None
    assert "Предыдущий раздел" not in pager
    assert "Следующий раздел" in pager
    assert 'href="/section/middle"' in pager and "Средний раздел" in pager


def test_middle_section_has_prev_and_next(course):
    pager = _section_pager(course.get("/section/middle").text)
    assert pager is not None
    assert 'href="/section/first"' in pager and "Первый раздел" in pager
    assert 'href="/section/last"' in pager and "Последний раздел" in pager
    assert pager.index("Предыдущий раздел") < pager.index("Следующий раздел")
    assert "Черновик" not in pager


def test_last_section_has_only_prev(course):
    pager = _section_pager(course.get("/section/last").text)
    assert pager is not None
    assert "Следующий раздел" not in pager
    assert 'href="/section/middle"' in pager


def test_single_section_has_no_pager(client):
    assert _section_pager(client.get("/section/demo").text) is None


def test_index_is_course_contents(course):
    response = course.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "Разделы курса" in response.text
    positions = [response.text.index(f'href="/section/{sid}"') for _, sid, _, _ in COURSE]
    assert positions == sorted(positions)
    assert "Черновик" not in response.text


def test_real_course_lists_naive_service_after_python_runtime():
    root = main.content_root()
    if not root.is_dir():
        pytest.skip("контент не смонтирован")
    html = TestClient(main.app).get("/").text
    assert html.index('href="/section/python-runtime"') < html.index('href="/section/naive-service"')
    page = TestClient(main.app).get("/section/naive-service")
    assert page.status_code == 200


def test_pages_use_course_title(client):
    home = client.get("/").text
    assert "Высоконагруженные ML/DL системы" in home
    assert "Почему мы используем Triton" in home
    section = client.get("/section/demo").text
    assert "Высоконагруженные ML/DL системы" in section
    assert "Оптимизация" not in section and "Оптимизация" not in home


@pytest.fixture
def mixed(tmp_path, monkeypatch):
    with_exercise = tmp_path / "20-with"
    (with_exercise / "snippets").mkdir(parents=True)
    (with_exercise / "harness" / "sum").mkdir(parents=True)
    (with_exercise / "harness" / "sum" / "meta.yml").write_text("kind: ab\n")
    for name in ("s.py", "r.py"):
        (with_exercise / "snippets" / name).write_text("x = 1\n", encoding="utf-8")
    (with_exercise / "section.md").write_text(
        "---\nid: with\ntitle: С заданием\norder: 10\nsummary: Строка о разделе\n---\n\n## Часть\n\n"
        "```exercise id=ex1 lang=python\ntitle: Т\ntarget: speedup >= 2\nstarter: snippets/s.py\n"
        "reference: snippets/r.py\nharness: sum\n```\n",
        encoding="utf-8",
    )
    without = tmp_path / "30-without"
    without.mkdir()
    (without / "section.md").write_text(
        "---\nid: without\ntitle: Без заданий\norder: 20\n---\n\n## Часть\n\nТекст.\n", encoding="utf-8"
    )
    monkeypatch.setenv("CONTENT_ROOT", str(tmp_path))
    return TestClient(main.app)


def _nav_item(html, section_id):
    start = html.index(f'data-section-nav="{section_id}"')
    return html[html.rindex("<li", 0, start) : html.index("</li>", start)]


def test_nav_lists_all_sections_with_exercises(mixed):
    for page in ("/", "/section/with", "/section/without"):
        item = _nav_item(mixed.get(page).text, "with")
        assert 'data-exercises="ex1"' in item
        assert "data-progress" in item


def test_nav_hides_progress_without_exercises(mixed):
    html = mixed.get("/section/with").text
    item = _nav_item(html, "without")
    assert "data-exercises" not in item and "data-progress" not in item
    home = mixed.get("/").text
    card = home[home.index('data-section-card="without"') :]
    card = card[: card.index("</a>")]
    assert "data-progress" not in card


def test_home_cards_show_summary_and_progress(mixed):
    home = mixed.get("/").text
    card = home[home.index('data-section-card="with"') :]
    card = card[: card.index("</a>")]
    assert "Строка о разделе" in card and 'data-exercises="ex1"' in card and "data-progress" in card


def test_home_has_soon_cards(mixed):
    home = mixed.get("/").text
    # Раздел про Triton уже написан: «скоро» осталось только LLM.
    assert "скоро" in home and home.count("скоро") == 1
    title = "LLM-сервинг"
    assert title in home
    before = home[: home.index(title)]
    # Карточка «скоро» — не ссылка: последний открытый <a> перед ней закрыт.
    assert before.rfind("<a ") < before.rfind("</a>")


def test_page_toc_lists_subheadings(mixed, tmp_path):
    (tmp_path / "30-without" / "section.md").write_text(
        "---\nid: without\ntitle: Без заданий\norder: 20\n---\n\n## Часть\n\n### Подробность\n\nТекст.\n",
        encoding="utf-8",
    )
    html = mixed.get("/section/without").text
    toc = html[html.index('id="page-toc"') :]
    assert 'href="#heading-подробность"' in toc[: toc.index("</nav>")]
