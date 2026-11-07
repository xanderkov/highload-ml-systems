// Монтирование интерактивных блоков. Разметку блоков (<div class="block"
// data-kind data-id data-lang data-params>) отдаёт render.py.

import { mountNav } from "./nav.js";
import { mountThemeToggle } from "./theme.js";

const BLOCK_MODULES = {
  exercise: "./blocks/exercise.js",
  benchmark: "./blocks/benchmark.js",
};

function moduleUrl(element) {
  const kind = element.dataset.kind;
  // viz-модуль называется по id блока — так контент связан с кодом по имени,
  // без отдельного реестра (см. спеку §5).
  if (kind === "viz") return `./viz/${element.dataset.id}.js`;
  return BLOCK_MODULES[kind] || null;
}

function showMountError(element, text) {
  element.classList.add("block-broken");
  element.textContent = `Блок «${element.dataset.id}» не запустился: ${text}`;
}

async function mountBlock(element, sectionId) {
  const url = moduleUrl(element);
  if (!url) {
    showMountError(element, `неизвестный тип «${element.dataset.kind}»`);
    return;
  }
  // Динамический импорт с обработкой ошибок: один отсутствующий или битый
  // модуль (например, viz, добавленный в текст раньше, чем написан скрипт)
  // не должен уносить с собой остальные блоки страницы.
  const module = await import(url);
  const params = JSON.parse(element.dataset.params || "{}");
  module.mount(element, {
    sectionId,
    blockId: element.dataset.id,
    lang: element.dataset.lang || "",
    params,
  });
}

/** Кнопка «копировать» у блоков кода в тексте статьи (не в заданиях). */
function addCopyButtons() {
  for (const pre of document.querySelectorAll(".section pre")) {
    if (pre.closest(".block") || pre.parentElement.classList.contains("code-wrap")) continue;
    const wrap = document.createElement("div");
    wrap.className = "code-wrap";
    pre.replaceWith(wrap);
    wrap.append(pre);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn code-copy";
    button.textContent = "Копировать";
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(pre.textContent);
        button.textContent = "Скопировано";
      } catch {
        button.textContent = "Не вышло";
      }
      setTimeout(() => { button.textContent = "Копировать"; }, 1500);
    });
    wrap.append(button);
  }
}

function typeset() {
  if (!window.renderMathInElement) return;
  window.renderMathInElement(document.querySelector("main"), {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
    ],
    throwOnError: false,
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const initialHash = location.hash;
  let navigated = false;
  const markNavigated = () => { navigated = true; };
  const navigationEvents = ['wheel', 'touchstart', 'pointerdown', 'keydown'];
  for (const name of navigationEvents) window.addEventListener(name, markNavigated, { passive: true });
  if (window.ace) {
    // Ace догружает режимы и темы отдельными файлами и вычисляет их путь из
    // src своего <script>. Задаём явно, чтобы это не зависело от того, как
    // именно браузер нормализовал адрес.
    window.ace.config.set("basePath", "/static/vendor/ace");
  }

  const sectionId = document.querySelector(".section")?.dataset.section;
  mountThemeToggle();
  mountNav(sectionId);
  if (sectionId) {
    for (const element of document.querySelectorAll(".block")) {
      try {
        await mountBlock(element, sectionId);
      } catch (error) {
        showMountError(element, error.message || error);
      }
    }
  }

  addCopyButtons();
  typeset();
  // Interactive blocks also create headings after Markdown has been rendered.
  for (const heading of document.querySelectorAll('.section :is(h1, h2, h3, h4, h5, h6):not([id])')) {
    const slug = heading.textContent.trim().toLowerCase().replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-|-$/g, '') || 'heading';
    const base = `heading-${slug}`;
    let id = base, suffix = 2;
    while (document.getElementById(id)) id = `${base}-${suffix++}`;
    heading.id = id;
    const link = document.createElement('a');
    link.className = 'heading-link';
    link.href = `#${id}`;
    link.append(...heading.childNodes);
    heading.append(link);
  }
  // Restore the requested anchor once the interactive blocks have their size.
  // Never pull the reader back after they have started navigating themselves.
  await document.fonts.ready;
  if (document.readyState !== 'complete') {
    await new Promise(resolve => window.addEventListener('load', resolve, { once: true }));
  }
  if (initialHash && location.hash === initialHash && !navigated) {
    try {
      document.getElementById(decodeURIComponent(initialHash.slice(1)))?.scrollIntoView();
    } catch { /* Ignore malformed fragments in external links. */ }
  }
  for (const name of navigationEvents) window.removeEventListener(name, markNavigated);
});
