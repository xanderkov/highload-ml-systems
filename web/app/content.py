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
    # Одна строка для карточки раздела на главной; необязательна.
    summary: str | None = None


def _split_frontmatter(text: str, source: Path) -> tuple[dict, str]:
    text = text.replace("\r\n", "\n")
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

    try:
        order_value = int(meta["order"])
    except (ValueError, TypeError) as exc:
        raise ContentError(f"{source}: поле order должно быть целым числом, получено {meta['order']!r}") from exc

    return Section(
        id=str(meta["id"]),
        title=str(meta["title"]),
        order=order_value,
        draft=bool(meta.get("draft", False)),
        dir=directory,
        body=body,
        summary=str(meta["summary"]).strip() if meta.get("summary") else None,
    )


def list_sections(root: Path) -> list[Section]:
    sections = [
        load_section(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and (child / "section.md").exists()
    ]
    return sorted((s for s in sections if not s.draft), key=lambda s: s.order)
