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


def test_index_opens_course_directly(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Демо-раздел" in response.text
    assert response.url.path == "/section/demo"
    assert "Привет" in response.text
    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/section/demo"


def test_section_page_renders_markdown(client):
    response = client.get("/section/demo")

    assert response.status_code == 200
    # Заголовок части несёт якорь: на него ссылается боковое оглавление.
    assert '<h2 id="part-1"><a class="heading-link" href="#part-1">Привет</a></h2>' in response.text


def test_unknown_section_returns_404(client):
    assert client.get("/section/nope").status_code == 404


def test_page_loads_versioned_styles_and_nested_modules(client):
    response = client.get("/section/demo")
    for asset in ["style.css", "app.js"]:
        assert f'{main.ASSET_PREFIX}/{asset}' in response.text
    for asset in ["style.css", "app.js", "blocks/exercise.js", "blocks/index-tutorial.js"]:
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
