from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app import main
from app.content import ContentError, load_section
from app.jobs import build_job, parse_target
from app.render import render_section

SECTION = """---
id: demo
title: Демо
order: 10
---

![Иерархия](images/hierarchy.svg)

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

```benchmark id=ladder lang=c
harness: stride
source: snippets/walk.c
```
"""


@pytest.fixture
def section(tmp_path):
    directory = tmp_path / "01-demo"
    (directory / "snippets").mkdir(parents=True)
    (directory / "images").mkdir(parents=True)
    (directory / "images" / "hierarchy.svg").write_text("<svg/>", encoding="utf-8")
    (directory / "harness" / "sum").mkdir(parents=True)
    (directory / "harness" / "sum" / "meta.yml").write_text("kind: ab\nfunction: f\n")
    (directory / "harness" / "stride").mkdir(parents=True)
    (directory / "harness" / "stride" / "meta.yml").write_text("kind: sweep\nfunction: walk\n")
    for name, text in [
        ("sum_starter.c", "// starter\n"),
        ("sum_ref.c", "// ref\n"),
        ("sum_rows.c", "// rows\n"),
        ("sum_cols.c", "// cols\n"),
        ("walk.c", "// walk\n"),
    ]:
        (directory / "snippets" / name).write_text(text, encoding="utf-8")
    (directory / "section.md").write_text(SECTION, encoding="utf-8")
    return load_section(directory)


@pytest.fixture
def client(section, monkeypatch):
    monkeypatch.setenv("CONTENT_ROOT", str(section.dir.parent))
    return TestClient(main.app)


def blocks_of(section):
    _, blocks = render_section(section)
    return {block.id: block for block in blocks}


def test_parse_target():
    assert parse_target("speedup >= 3") == {"metric": "speedup", "op": ">=", "value": 3.0}


def test_parse_target_accepts_strict_greater():
    assert parse_target("speedup > 1.5")["op"] == ">"


def test_parse_target_metric_le():
    assert parse_target("pss_growth_ratio <= 0.3") == {"metric": "pss_growth_ratio", "op": "<=", "value": 0.3}


def test_parse_target_lt():
    assert parse_target("m < 2")["op"] == "<"


def test_parse_target_rejects_unknown_op():
    with pytest.raises(ContentError, match="=>"):
        parse_target("speedup => 3")


def test_parse_target_rejects_garbage():
    with pytest.raises(ContentError, match="быстрее"):
        parse_target("быстрее в три раза")


def test_exercise_job_uses_starter_as_baseline(section):
    job = build_job(section, blocks_of(section)["col-sum"], "// студент\n")

    assert job["mode"] == "exercise"
    assert job["lang"] == "c"
    assert job["harness_dir"] == "01-demo/harness/sum"
    assert job["units"]["a"] == "// starter\n"
    assert job["units"]["b"] == "// студент\n"
    assert job["target"]["value"] == 3.0


def test_exercise_job_never_carries_reference(section):
    job = build_job(section, blocks_of(section)["col-sum"], "// студент\n")

    assert "// ref" not in str(job)


def test_benchmark_job_uses_two_variants(section):
    job = build_job(section, blocks_of(section)["rows-vs-cols"], "")

    assert job["mode"] == "benchmark"
    assert job["units"] == {"a": "// rows\n", "b": "// cols\n"}
    assert job.get("target") is None


def test_sweep_benchmark_job_has_single_unit(section):
    job = build_job(section, blocks_of(section)["ladder"], "")

    assert list(job["units"]) == ["a"]
    assert job["units"]["a"] == "// walk\n"
    assert job["harness_dir"] == "01-demo/harness/stride"


def test_every_job_carries_harness_dir(section):
    # run_job падает с KeyError, если ключа нет, и с TypeError, если он None
    for block in blocks_of(section).values():
        job = build_job(section, block, "")
        assert isinstance(job["harness_dir"], str) and job["harness_dir"]


def fake_runner(monkeypatch, captured, *, status_code=200, payload=None, error=None):
    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["job"] = json
        captured["timeout"] = timeout
        if error is not None:
            raise error

        class Response:
            def __init__(self):
                self.status_code = status_code
                self.text = "boom"

            def json(self):
                return payload

        return Response()

    monkeypatch.setattr(main.httpx, "post", fake_post)


def test_api_run_proxies_to_runner(client, monkeypatch):
    captured = {}
    fake_runner(monkeypatch, captured, payload={"status": "ok", "speedup": 3.4, "passed": True})

    response = client.post(
        "/api/run", json={"section": "demo", "block": "col-sum", "code": "// студент\n"}
    )

    assert response.status_code == 200
    assert response.json()["passed"] is True
    assert captured["job"]["units"]["b"] == "// студент\n"
    assert captured["timeout"] == main.RUN_TIMEOUT_S


def test_run_timeout_exceeds_every_harness_timeout():
    # Инвариант из main.RUN_TIMEOUT_S: прокси не должен обрывать прогон раньше,
    # чем runner вернёт собственный статус timeout. Проверяется по настоящему
    # контенту курса, а не по фикстуре, — иначе инвариант некому нарушить.
    root = Path(main.__file__).resolve().parent.parent / "content"
    limits = {
        str(meta): float((yaml.safe_load(meta.read_text(encoding="utf-8")) or {}).get("timeout_s", 30))
        for meta in root.glob("*/harness/*/meta.yml")
    }
    assert all(main.RUN_TIMEOUT_S > limit for limit in limits.values()), limits


def test_api_run_unknown_block_returns_404(client):
    response = client.post("/api/run", json={"section": "demo", "block": "nope", "code": ""})

    assert response.status_code == 404


def test_api_run_unknown_section_returns_404(client):
    response = client.post("/api/run", json={"section": "nope", "block": "col-sum", "code": ""})

    assert response.status_code == 404


def test_api_run_passes_runner_failure_statuses_through(client, monkeypatch):
    fake_runner(
        monkeypatch,
        {},
        payload={"status": "compile_error", "message": "Код не скомпилировался", "line": 4},
    )

    response = client.post("/api/run", json={"section": "demo", "block": "col-sum", "code": "x"})

    assert response.status_code == 200
    assert response.json()["status"] == "compile_error"


def test_api_run_reports_runner_crash_as_service_error(client, monkeypatch):
    fake_runner(monkeypatch, {}, status_code=500, payload=None)

    response = client.post("/api/run", json={"section": "demo", "block": "col-sum", "code": "x"})

    assert response.status_code == 200
    assert response.json()["status"] == "service_error"


def test_api_run_transport_failure_is_502(client, monkeypatch):
    fake_runner(monkeypatch, {}, error=httpx.ConnectError("нет соединения"))

    response = client.post("/api/run", json={"section": "demo", "block": "col-sum", "code": "x"})

    assert response.status_code == 502


def test_markdown_image_points_at_asset_route(section):
    html, _ = render_section(section)

    assert 'src="/assets/demo/images/hierarchy.svg"' in html


def test_asset_route_serves_section_image(client):
    response = client.get("/assets/demo/images/hierarchy.svg")

    assert response.status_code == 200
    assert response.text == "<svg/>"


def test_asset_route_refuses_snippets(client):
    assert client.get("/assets/demo/snippets/sum_ref.c").status_code == 404


def test_asset_route_refuses_traversal(client):
    response = client.get("/assets/demo/images/..%2fsnippets%2fsum_ref.c")

    assert response.status_code == 404
    assert "// ref" not in response.text

@pytest.mark.parametrize('variant', [0, 1])
def test_parallel_editors_replace_only_selected_unit(section, variant):
    from dataclasses import replace
    section = replace(section, body=section.body.replace('variants: [rows, cols]', 'variants: [rows, cols]\nparallel_editors: true'))
    _, blocks = render_section(section)
    block = next(b for b in blocks if b.id == 'rows-vs-cols')
    assert block.params['variant_codes'] == ['// rows\n', '// cols\n']
    job = build_job(section, block, '// edited', variant=variant)
    assert job['units']['ab'[variant]] == '// edited'
    assert job['units']['ab'[1 - variant]] == block.params['variant_codes'][1 - variant]


def test_three_parallel_editors_route_third_code(section):
    from dataclasses import replace
    section = replace(section, body=section.body.replace('variants: [rows, cols]', 'variants: [rows, cols, rows]\nparallel_editors: true'))
    _, blocks = render_section(section)
    block = next(b for b in blocks if b.id == 'rows-vs-cols')
    assert len(block.params['variant_codes']) == 3
    job = build_job(section, block, '// third edit', variant=2)
    assert job['units'] == {'a': '// rows\n', 'b': '// cols\n', 'c': '// third edit'}
    assert job['edited_unit'] == 'c'
