// Монтирование интерактивных блоков. Разметку блоков (<div class="block"
// data-kind data-id data-lang data-params>) отдаёт render.py.

import { isDone } from "./progress.js";

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

/** Боковое оглавление: отметки о зачёте и подсветка текущей части. */
function mountOutline(sectionId) {
  const nav = document.querySelector(".section-toc");
  if (!nav) return;

  const items = [...nav.querySelectorAll(".toc-parts li")];
  const bars = [...nav.querySelectorAll(".toc-bar span")];

  // Часть считается пройденной, когда зачтены все задания внутри неё. Часть
  // без заданий отметки не получает: читать её можно, «сдать» — нечего.
  function refreshDone() {
    let total = 0;
    let done = 0;
    for (const item of items) {
      const ids = (item.dataset.exercises || "").split(",").filter(Boolean);
      if (!ids.length) continue;
      total += ids.length;
      const passed = ids.filter((id) => isDone(sectionId, id));
      done += passed.length;
      item.querySelector(".toc-mark").hidden = passed.length !== ids.length;
    }
    const label = nav.querySelector(".toc-progress");
    if (total) {
      label.textContent = `${done}/${total}`;
      label.hidden = false;
    }
  }

  refreshDone();
  // Прогресс пишется в localStorage при зачёте, но события об этом нет —
  // перечитываем после каждого запуска задания.
  document.addEventListener("click", (event) => {
    if (event.target.closest(".exercise .run")) setTimeout(refreshDone, 0);
  });

  const headings = items
    .map((item) => document.getElementById(item.dataset.part))
    .filter(Boolean);
  if (!headings.length || !("IntersectionObserver" in window)) return;

  const seen = new Set();
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) seen.add(entry.target.id);
      }
      // Текущая — последняя часть, чей заголовок уже проехал верх экрана.
      let current = headings[0].id;
      for (const heading of headings) {
        if (heading.getBoundingClientRect().top <= 120) current = heading.id;
      }
      items.forEach((item, index) => {
        item.classList.toggle("is-current", item.dataset.part === current);
        bars[index]?.classList.toggle("is-seen", seen.has(item.dataset.part));
      });
    },
    { rootMargin: "-100px 0px -70% 0px", threshold: 0 }
  );
  headings.forEach((heading) => observer.observe(heading));
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
  if (sectionId) {
    for (const element of document.querySelectorAll(".block")) {
      try {
        await mountBlock(element, sectionId);
      } catch (error) {
        showMountError(element, error.message || error);
      }
    }
    mountOutline(sectionId);
  }

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
