import pytest

from app.content import ContentError, list_sections, load_section

SECTION = """---
id: python-runtime
title: Python как рантайм сервиса
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
    directory = write_section(tmp_path, "20-python-runtime", SECTION)

    section = load_section(directory)

    assert section.id == "python-runtime"
    assert section.title == "Python как рантайм сервиса"
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


def test_load_section_with_crlf_line_endings(tmp_path):
    directory = tmp_path / "01-crlf"
    directory.mkdir(parents=True)
    # Write file with CRLF line endings
    (directory / "section.md").write_text(
        "---\r\nid: crlf-test\r\ntitle: CRLF раздел\r\norder: 5\r\n---\r\n\r\nТекст с CRLF.\r\n",
        encoding="utf-8"
    )

    section = load_section(directory)

    assert section.id == "crlf-test"
    assert section.title == "CRLF раздел"
    assert section.order == 5
    assert section.draft is False
    assert "\r" not in section.body
    assert section.body.strip() == "Текст с CRLF."


def test_load_section_with_malformed_order_fails(tmp_path):
    directory = write_section(tmp_path, "01-broken", "---\nid: x\ntitle: Т\norder: abc\n---\n\nтекст\n")

    with pytest.raises(ContentError, match="order"):
        load_section(directory)


def test_every_viz_block_has_a_module():
    """viz-модуль ищется по id блока (app.js): опечатка видна только в браузере."""
    import os
    from pathlib import Path

    from app.render import render_section

    root = Path(os.environ.get("CONTENT_ROOT", "/app/content"))
    if not root.is_dir():
        pytest.skip("контент не смонтирован")
    viz_dir = Path(__file__).resolve().parent.parent / "static" / "viz"
    missing = [
        f"{section.id}/{block.id}"
        for section in list_sections(root)
        for block in render_section(section)[1]
        if block.kind == "viz" and not (viz_dir / f"{block.id}.js").is_file()
    ]
    assert missing == []


def test_summary_is_optional(tmp_path):
    plain = write_section(tmp_path, "a", "---\nid: a\ntitle: А\norder: 10\n---\n\nтекст\n")
    described = write_section(
        tmp_path, "b", "---\nid: b\ntitle: Б\norder: 20\nsummary: Одна строка.\n---\n\nтекст\n"
    )

    assert load_section(plain).summary is None
    assert load_section(described).summary == "Одна строка."


def test_section40_lib_copies_match_section30():
    # _lib разделов независимы: раздел 40 держит копии библиотек раздела 30.
    # Любая правка вносится в оба файла, иначе замеры разделов разойдутся.
    import os
    from pathlib import Path

    root = Path(os.environ.get("CONTENT_ROOT", "/app/content"))
    lib30 = root / "30-naive-service" / "harness" / "_lib"
    copies = {name: lib30 / name for name in ("servicelib.py", "widemodel.py", "batcher_app.py")}
    # Батчеры раздела 30 — точки сравнения для Triton (стартовый и эталонный).
    for name in ("batcher_starter.py", "batcher_ref.py"):
        copies[name] = root / "30-naive-service" / "snippets" / name
    for name, original in copies.items():
        copy = root / "40-triton" / "harness" / "_lib" / name
        assert copy.read_bytes() == original.read_bytes(), name


def test_section50_static_engine_is_the_starter():
    # Точка сравнения главы 3 — стартовый код задания, копия в _lib.
    import os
    from pathlib import Path

    root = Path(os.environ.get("CONTENT_ROOT", "/app/content")) / "50-llm"
    assert (root / "harness" / "_lib" / "static_engine.py").read_bytes() == \
        (root / "snippets" / "engine_starter.py").read_bytes()
    # Глава 4 сравнивает llama.cpp с эталоном задания — тоже копия в _lib.
    assert (root / "harness" / "_lib" / "engine_ref.py").read_bytes() == \
        (root / "snippets" / "engine_ref.py").read_bytes()
