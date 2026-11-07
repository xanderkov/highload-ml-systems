import json
import re
from html import escape
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

from app.content import Block, ContentError, Section

# Задание идёт по A/B-пути (стартовый код против кода студента), замер —
# по series-харнессу (линии графика). Других типов запуска у runner'а нет.
BLOCK_KINDS = {"viz", "benchmark", "exercise"}
EXT = {"python": "py"}
VIZ_DIR = Path(__file__).resolve().parent.parent / "static" / "viz"

# Схема (http:, data:), протокол-относительный //host и абсолютный /path
# оставляются как есть; переписывается только путь относительно section.md.
ABSOLUTE_URL = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:|//|/|#)", re.IGNORECASE)

# Ведущий номер части в заголовке: «1. », «10) », «3 — ».
LEADING_NUMBER = re.compile(r"^\s*\d+\s*[.)—–-]\s*")

# Врезки в синтаксисе GitHub: `> [!NOTE]` первой строкой цитаты. CommonMark их
# не знает и отрисовал бы «[!NOTE]» текстом внутри цитаты, поэтому маркер
# срезается, а на саму цитату вешаются класс и заголовок (его выводит CSS
# через ::before — так не приходится подмешивать в поток сырой HTML при
# отключённой опции html).
CALLOUT_TITLES = {
    "NOTE": "Заметка",
    "TIP": "Совет",
    "IMPORTANT": "Важно",
    "WARNING": "Осторожно",
    "CAUTION": "Грабли",
}
CALLOUT_MARKER = re.compile(r"^\[!([A-Z]+)\][ \t]*(?:\n|$)")


def _parse_info(info: str) -> tuple[str, dict[str, str]]:
    parts = info.strip().split()
    kind = parts[0]
    attrs = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
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
        harness_kind = _harness_kind(section, params["harness"])
        if harness_kind != "ab":
            # Упражнение показывает A/B-результат (ускорение, разброс, вердикт);
            # series этих полей не возвращает.
            raise ContentError(
                f"{section.dir / 'section.md'}: exercise {attrs['id']}: харнесс {params['harness']} "
                f"имеет kind: {harness_kind}, а упражнению нужен kind: ab"
            )
        params["starter_code"] = _require_file(section, params["starter"], "starter")
        _require_file(section, params["reference"], "reference")

    if kind == "benchmark":
        if "starter" in params:
            params["starter_code"] = _require_file(section, params["starter"], "starter")
        if "harness" not in params:
            raise ContentError(
                f"{section.dir / 'section.md'}: benchmark {attrs['id']} без поля harness"
            )
        _require_harness(section, params["harness"])
        harness_kind = _harness_kind(section, params["harness"])
        if harness_kind != "series":
            raise ContentError(
                f"{section.dir / 'section.md'}: benchmark {attrs['id']}: харнесс {params['harness']} "
                f"имеет kind: {harness_kind}, а замеру нужен kind: series"
            )
        if "source" not in params:
            raise ContentError(
                f"{section.dir / 'section.md'}: benchmark {attrs['id']} над series-харнессом "
                f"требует поле source"
            )
        _require_file(section, params["source"], "source")

    return Block(kind=kind, id=attrs["id"], lang=lang, params=params)


def _callout_rule(state) -> None:
    """Срезает маркер `[!NOTE]` и помечает цитату как врезку.

    Правило встраивается между core-шагами block и inline: на этом моменте
    inline-токены ещё не разобраны на children, поэтому правку content видно
    в итоговом HTML. После шага inline менять content уже поздно.
    """
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type != "blockquote_open" or index + 2 >= len(tokens):
            continue
        if tokens[index + 1].type != "paragraph_open" or tokens[index + 2].type != "inline":
            continue
        inline = tokens[index + 2]
        match = CALLOUT_MARKER.match(inline.content)
        if match is None or match.group(1) not in CALLOUT_TITLES:
            continue
        kind = match.group(1)
        inline.content = inline.content[match.end():]
        token.attrJoin("class", "callout")
        token.attrJoin("class", f"callout-{kind.lower()}")
        token.attrSet("data-title", CALLOUT_TITLES[kind])


def render_section(section: Section) -> tuple[str, list[Block]]:
    blocks: list[Block] = []
    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")
    md.core.ruler.after("block", "callout", _callout_rule)

    default_fence = md.renderer.rules["fence"]

    def fence(tokens, idx, options, env):
        token = tokens[idx]
        info = token.info.strip()
        kind, attrs = _parse_info(info) if info else ("", {})
        # Fence syntax alone can't tell an "unknown interactive block" apart
        # from an "annotated code fence" (e.g. ```python title=foo for a
        # titled snippet, or ```bash {highlight} for a highlight hint) —
        # both are an unrecognized word followed by extra tokens. Every
        # genuine interactive block requires an id=... attribute (validated
        # below), so we take its presence as the author's signal of intent
        # to declare a block; without it, an unrecognized kind is treated as
        # ordinary code rather than failing validation.
        if kind not in BLOCK_KINDS and "id" not in attrs:
            return default_fence(tokens, idx, options, env)
        block = _build_block(section, token.info, token.content)
        blocks.append(block)
        payload = escape(json.dumps(block.params, ensure_ascii=False), quote=True)
        return (
            f'<div class="block not-prose" data-kind="{block.kind}" data-id="{block.id}" '
            f'data-lang="{block.lang or ""}" data-params="{payload}"></div>\n'
        )

    # Заголовки частей получают якоря, чтобы на них могло ссылаться боковое
    # оглавление. Идентификатор — порядковый, а не производный от текста:
    # транслитерировать кириллицу незачем, а section_outline нумерует части в
    # том же порядке, так что ссылки и якоря сходятся по построению.
    default_heading = md.renderer.rules.get("heading_open")
    part_number = [0]
    heading_ids: set[str] = set()

    def heading_open(tokens, idx, options, env):
        token = tokens[idx]
        if token.tag == "h2":
            part_number[0] += 1
            anchor = f"part-{part_number[0]}"
        else:
            title = tokens[idx + 1].content
            slug = re.sub(r"[^\w-]+", "-", title.lower()).strip("-") or "heading"
            base = f"heading-{slug}"
            anchor = base
            suffix = 2
            while anchor in heading_ids:
                anchor = f"{base}-{suffix}"
                suffix += 1
        heading_ids.add(anchor)
        token.attrSet("id", anchor)
        # Отступ при переходе по якорю: иначе заголовок уезжает под
        # закреплённую верхнюю полосу страницы.
        token.attrJoin("class", "scroll-mt-20")
        if default_heading:
            opening = default_heading(tokens, idx, options, env)
        else:
            opening = md.renderer.renderToken(tokens, idx, options, env)
        return opening + f'<a class="heading-link" href="#{escape(anchor, quote=True)}">'

    def heading_close(tokens, idx, options, env):
        return '</a>' + md.renderer.renderToken(tokens, idx, options, env)

    md.renderer.rules["heading_open"] = heading_open
    md.renderer.rules["heading_close"] = heading_close

    default_image = md.renderer.rules["image"]

    def image(tokens, idx, options, env):
        # `![](images/hierarchy.svg)` в section.md — путь относительно папки
        # раздела, а не относительно URL страницы: браузер разрешил бы его от
        # /section/<id> в /section/images/... и получил 404. Переписываем на
        # маршрут /assets/<id>/..., который отдаёт файлы из папки раздела
        # (см. main.section_asset).
        token = tokens[idx]
        src = token.attrGet("src") or ""
        if src and not ABSOLUTE_URL.match(src):
            token.attrSet("src", f"/assets/{section.id}/{src}")
        return default_image(tokens, idx, options, env)

    md.renderer.rules["fence"] = fence
    md.renderer.rules["image"] = image
    html = md.render(section.body)
    return html, blocks


def section_outline(section: Section) -> list[dict]:
    """Части раздела для бокового оглавления: заголовки h2 по порядку и
    идентификаторы заданий, попавших под каждый из них.

    Разбор идёт по токенам, а не по готовому HTML: регулярками по разметке
    такое ломается на первом же вложенном теге. Нумерация частей совпадает с
    якорями, которые проставляет render_section, потому что обе функции идут
    по документу в одном порядке.
    """
    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")
    tokens = md.parse(section.body)

    parts: list[dict] = []
    number = 0
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2":
            number += 1
            title = tokens[index + 1].content if index + 1 < len(tokens) else ""
            # Части в тексте пронумерованы вручную («## 1. Вы это уже знаете»),
            # а панель показывает свой номер — иначе выходит «01 · 1.».
            title = LEADING_NUMBER.sub("", title, count=1)
            parts.append({"id": f"part-{number}", "title": title, "exercises": []})
        elif token.type == "fence" and parts:
            info = token.info.strip()
            if not info:
                continue
            kind, attrs = _parse_info(info)
            if kind == "exercise" and "id" in attrs:
                parts[-1]["exercises"].append(attrs["id"])
    return parts
