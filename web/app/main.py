import hashlib
import os
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.content import ContentError, Section, list_sections
from app.jobs import build_job
from app.render import render_section, section_outline

BASE_DIR = Path(__file__).resolve().parent

# Прокси к runner'у обязан пережидать самый долгий харнесс: у runner'а есть
# собственный timeout_s из meta.yml, и только он умеет вернуть честный статус
# "timeout" с человеческим текстом. Инвариант: RUN_TIMEOUT_S строго больше
# любого timeout_s в любом meta.yml курса (сейчас максимум — 180 с). Если
# оборвать запрос раньше, студент увидит сетевую ошибку вместо объяснения,
# что его код не уложился в лимит.
RUN_TIMEOUT_S = 300

# Ассеты раздела отдаются только из этой подпапки: рядом, в snippets/, лежат
# эталонные решения заданий, которые не должны быть доступны из браузера.
ASSET_DIR = "images"

def asset_version(directory: Path) -> str:
    """Version the whole module graph: relative imports inherit this URL prefix."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if "vendor" in relative.parts or path.suffix not in {".js", ".css"}:
            continue
        digest.update(relative.as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


STATIC_DIR = BASE_DIR.parent / "static"
ASSET_PREFIX = f"/assets/{asset_version(STATIC_DIR)}"
app = FastAPI(title="Курс: оптимизация инференса")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount(ASSET_PREFIX, StaticFiles(directory=STATIC_DIR), name="versioned-static")
templates = Jinja2Templates(
    directory=BASE_DIR / "templates",
    context_processors=[lambda request: {"asset_prefix": ASSET_PREFIX}],
)


class RunRequest(BaseModel):
    section: str
    block: str
    code: str = ""
    variant: Literal[0, 1, 2] | None = None


def content_root() -> Path:
    return Path(os.environ.get("CONTENT_ROOT", BASE_DIR.parent / "content"))


def runner_url() -> str:
    return os.environ.get("RUNNER_URL", "http://runner:8000")


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


@app.get("/api/cache-info")
def cache_info() -> dict:
    try:
        response = httpx.get(f"{runner_url()}/cache-info", timeout=5)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Не удалось прочитать размеры кэшей") from exc


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    sections = list_sections(content_root())
    if not sections:
        raise HTTPException(status_code=404, detail="Материалы курса не найдены")
    section = next((item for item in sections if item.id == "cpu-cache"), sections[0])
    return RedirectResponse(f"/section/{section.id}", status_code=307)


@app.get("/section/{section_id}", response_class=HTMLResponse)
def section_page(request: Request, section_id: str):
    section = find_section(section_id)
    body, _blocks = render_section(section)
    return templates.TemplateResponse(
        request,
        "section.html",
        {"section": section, "body": body, "outline": section_outline(section)},
    )


@app.get("/assets/{section_id}/{asset_path:path}")
def section_asset(section_id: str, asset_path: str) -> FileResponse:
    """Отдаёт иллюстрации раздела: сюда ведут переписанные render.py пути картинок.

    Корень контента резолвится на каждый запрос (контент правится без
    пересборки образа). Итоговый путь резолвится целиком и проверяется на
    вложенность в <раздел>/images — так `../snippets/matrix_sum_ref.c` и любой
    симлинк наружу дают 404, а не выдачу файла.
    """
    section = find_section(section_id)
    root = (section.dir / ASSET_DIR).resolve()
    target = (section.dir / asset_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Файл {asset_path} не найден")
    return FileResponse(target)


@app.post("/api/run")
def api_run(payload: RunRequest) -> dict:
    section = find_section(payload.section)
    _, blocks = render_section(section)
    block = next((b for b in blocks if b.id == payload.block), None)
    if block is None:
        raise HTTPException(
            status_code=404, detail=f"Блок {payload.block} не найден в разделе {payload.section}"
        )

    if payload.variant is not None and (not block.params.get("parallel_editors") or payload.variant >= len(block.params.get("variant_sources", []))):
        raise HTTPException(status_code=400, detail="Вариант не найден")
    job = build_job(section, block, payload.code, variant=payload.variant)
    try:
        response = httpx.post(f"{runner_url()}/run", json=job, timeout=RUN_TIMEOUT_S)
    except httpx.RequestError as exc:
        # Транспортная ошибка: сервис замеров не отвечает вообще. Это не
        # результат прогона, поэтому и не 200 — фронт покажет отдельный текст.
        raise HTTPException(
            status_code=502, detail=f"Сервис замеров не отвечает: {exc}"
        ) from exc
    if response.status_code != 200:
        # Runner отвечает 200 на все восемь исходов прогона, включая ошибки
        # студента. Не-200 означает поломку самого сервиса — её нельзя
        # схлопывать в 502 «недоступен» (сервис доступен и что-то ответил) и
        # тем более нельзя показывать как ошибку в коде студента. Отдаём
        # результат со своим status, по которому фронт различит сбой сервиса.
        return {
            "status": "service_error",
            "message": (
                f"Сервис замеров ответил ошибкой {response.status_code}. "
                "Это сбой сервиса, а не ошибка в вашем коде."
            ),
            "log": response.text[:4000],
        }
    result = response.json()
    if block.kind == "experiment" and result.get("status") == "ok":
        result["gap_bytes"] = job["gap_bytes"]
        result["slowdown"] = result["student_ms"] / result["baseline_ms"] if result["baseline_ms"] > 0 else None
    return result
