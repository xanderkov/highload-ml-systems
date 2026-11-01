import json

import pytest

from app.content import ContentError, load_section
from app.render import render_section, section_outline

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

    assert '<h1 id="heading-заголовок"><a class="heading-link" href="#heading-заголовок">Заголовок</a></h1>' in html
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


def test_exercise_over_non_ab_harness_fails(tmp_path):
    # exercise.js рисует A/B-результат (ускорение, разброс); у sweep/series
    # таких полей нет, и блок упал бы в браузере.
    section = make_section(
        tmp_path,
        "```exercise id=x lang=c\ntitle: Т\ntarget: speedup >= 3\n"
        "starter: snippets/sum_starter.c\nreference: snippets/sum_ref.c\nharness: stride\n```\n",
    )

    with pytest.raises(ContentError, match="x.*stride.*sweep.*ab"):
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


def test_titled_code_fence_is_not_a_block(tmp_path):
    section = make_section(tmp_path, "```python title=foo\nprint('hi')\n```\n")

    html, blocks = render_section(section)

    assert blocks == []
    assert "print" in html


def test_annotated_code_fence_without_equals_is_not_a_block(tmp_path):
    section = make_section(tmp_path, "```bash {highlight}\necho hi\n```\n")

    html, blocks = render_section(section)

    assert blocks == []
    assert "echo hi" in html


def test_github_callout_becomes_marked_blockquote(tmp_path):
    section = make_section(tmp_path, "> [!NOTE]\n> Врезка с пояснением.\n")

    html, _ = render_section(section)

    assert 'class="callout callout-note"' in html
    assert 'data-title="Заметка"' in html
    assert "[!NOTE]" not in html
    assert "Врезка с пояснением." in html


def test_plain_blockquote_is_untouched(tmp_path):
    section = make_section(tmp_path, "> Просто цитата.\n")

    html, _ = render_section(section)

    assert "<blockquote>" in html
    assert "callout" not in html


def test_unknown_callout_kind_stays_literal(tmp_path):
    section = make_section(tmp_path, "> [!SPOILER]\n> Текст.\n")

    html, _ = render_section(section)

    assert "callout" not in html
    assert "[!SPOILER]" in html


def test_h2_headings_get_sequential_anchors(tmp_path):
    section = make_section(tmp_path, "## Первая\n\nтекст\n\n## Вторая\n\nтекст\n")

    html, _ = render_section(section)

    assert '<h2 id="part-1"><a class="heading-link" href="#part-1">Первая</a></h2>' in html
    assert '<h2 id="part-2"><a class="heading-link" href="#part-2">Вторая</a></h2>' in html


def test_h3_headings_have_permalink(tmp_path):
    section = make_section(tmp_path, "### Подзаголовок\n")

    html, _ = render_section(section)

    assert '<h3 id="heading-подзаголовок"><a class="heading-link" href="#heading-подзаголовок">Подзаголовок</a></h3>' in html


def test_outline_lists_parts_in_order(tmp_path):
    section = make_section(tmp_path, "## Первая\n\nтекст\n\n## Вторая\n\nтекст\n")

    outline = section_outline(section)

    assert [(p["id"], p["title"]) for p in outline] == [
        ("part-1", "Первая"),
        ("part-2", "Вторая"),
    ]


def test_outline_anchors_match_rendered_headings(tmp_path):
    section = make_section(tmp_path, "## Первая\n\nтекст\n\n## Вторая\n\nтекст\n")

    html, _ = render_section(section)
    outline = section_outline(section)

    for part in outline:
        assert f'id="{part["id"]}"' in html


def test_outline_attributes_exercise_to_its_part(tmp_path):
    section = make_section(
        tmp_path,
        "## Первая\n\nтекст\n\n"
        "## Вторая\n\n"
        "```exercise id=col-sum lang=c\n"
        "title: Т\ntarget: speedup >= 3\n"
        "starter: snippets/sum_starter.c\nreference: snippets/sum_ref.c\nharness: sum\n```\n",
    )

    outline = section_outline(section)

    assert outline[0]["exercises"] == []
    assert outline[1]["exercises"] == ["col-sum"]


def test_outline_ignores_plain_code_fences(tmp_path):
    section = make_section(tmp_path, "## Первая\n\n```c\nint main(void){return 0;}\n```\n")

    outline = section_outline(section)

    assert outline[0]["exercises"] == []


def test_outline_survives_fence_before_any_heading(tmp_path):
    section = make_section(tmp_path, "```c\nint x;\n```\n\n## Первая\n")

    outline = section_outline(section)

    assert [p["id"] for p in outline] == ["part-1"]


def test_outline_strips_manual_part_number_from_title(tmp_path):
    section = make_section(tmp_path, "## 1. Вы это уже знаете\n\n## 10) Итоги\n")

    outline = section_outline(section)

    assert [p["title"] for p in outline] == ["Вы это уже знаете", "Итоги"]


def test_rendered_heading_keeps_its_original_text(tmp_path):
    # Номер срезается только в панели: в самом тексте заголовок остаётся таким,
    # каким его написал автор.
    section = make_section(tmp_path, "## 1. Вы это уже знаете\n")

    html, _ = render_section(section)

    assert "1. Вы это уже знаете" in html


def test_duplicate_heading_ids_are_unique(tmp_path):
    section = make_section(tmp_path, "### Пример\n\n### Пример\n\n#### Пример\n")
    html, _ = render_section(section)
    for anchor in ("heading-пример", "heading-пример-2", "heading-пример-3"):
        assert html.count(f'id="{anchor}"') == 1
        assert f'href="#{anchor}"' in html
