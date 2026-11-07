// Навигация страницы: счётчики «N из M» у разделов, «На этой странице» с
// подсветкой текущего места и выдвижная левая панель на узком экране.
// Разметку отдают шаблоны (base.html, index.html, section.html); здесь только
// поведение — без неё страница остаётся читаемой, просто без счётчиков.

import { doneCount, isDone } from "./progress.js";

function idsOf(element) {
  return (element.dataset.exercises || "").split(",").filter(Boolean);
}

/** Счётчики у разделов в левой колонке и на карточках главной. */
export function refreshProgress(root = document) {
  for (const holder of root.querySelectorAll("[data-section-nav], [data-section-card]")) {
    const sectionId = holder.dataset.sectionNav || holder.dataset.sectionCard;
    const ids = idsOf(holder);
    const label = holder.querySelector("[data-progress]");
    // Раздел без заданий счётчика не получает: «0 из 0» ничего не сообщает.
    if (!label || !ids.length) continue;
    const done = doneCount(sectionId, ids);
    label.textContent = done === ids.length ? `✓ ${done} из ${ids.length}` : `${done} из ${ids.length}`;
    label.toggleAttribute("data-complete", done === ids.length);
    label.hidden = false;
  }
}

/** Отметки ✓ у частей, где зачтены все задания. */
function refreshPartMarks(toc, sectionId) {
  for (const item of toc.querySelectorAll("li[data-part]")) {
    const ids = idsOf(item);
    const mark = item.querySelector("[data-part-mark]");
    if (mark) mark.hidden = !ids.length || !ids.every((id) => isDone(sectionId, id));
  }
}

/** Подсветка текущего заголовка в «На этой странице». */
function watchCurrent(toc) {
  const links = [...toc.querySelectorAll("a[data-toc-link]")];
  const idOf = (link) => decodeURIComponent((link.getAttribute("href") || "").slice(1));
  const targets = links.map((link) => document.getElementById(idOf(link))).filter(Boolean);
  if (!targets.length || !("IntersectionObserver" in window)) return;

  const update = () => {
    // Текущий — последний заголовок, который уже проехал верхнюю полосу.
    let current = targets[0];
    for (const target of targets) {
      if (target.getBoundingClientRect().top <= 96) current = target;
    }
    for (const link of links) {
      if (idOf(link) === current.id) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
  };
  const observer = new IntersectionObserver(update, { rootMargin: "-80px 0px -70% 0px", threshold: 0 });
  targets.forEach((target) => observer.observe(target));
  update();
}

/** Левая панель на узком экране: кнопка ☰, Esc и переход по ссылке закрывают.
    Закрытая панель только сдвинута за край экрана, поэтому на узком экране
    она ещё и inert — иначе Tab водил бы по невидимым ссылкам. */
function mountDrawer() {
  const toggle = document.querySelector("[data-drawer-toggle]");
  const drawer = document.getElementById(toggle?.getAttribute("aria-controls") || "");
  if (!toggle || !drawer) return;
  // Граница — брейкпоинт md2 (860px) из app.css.
  const narrow = window.matchMedia?.("(max-width: 859.98px)");
  const sync = () => {
    drawer.toggleAttribute("inert", Boolean(narrow?.matches) && !drawer.hasAttribute("data-open"));
  };
  const setOpen = (open) => {
    drawer.toggleAttribute("data-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    sync();
    if (open) drawer.querySelector("a")?.focus();
  };
  sync();
  narrow?.addEventListener?.("change", sync);
  toggle.addEventListener("click", () => setOpen(!drawer.hasAttribute("data-open")));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.hasAttribute("data-open")) {
      setOpen(false);
      toggle.focus();
    }
  });
  drawer.addEventListener("click", (event) => {
    if (event.target.closest("a")) setOpen(false);
  });
}

export function mountNav(sectionId) {
  mountDrawer();
  refreshProgress();
  const toc = document.getElementById("page-toc");
  if (toc && sectionId) {
    refreshPartMarks(toc, sectionId);
    watchCurrent(toc);
  }
  // Прогресс пишется в localStorage при зачёте, но события об этом нет —
  // перечитываем после каждого запуска задания.
  document.addEventListener("course:progress", () => {
    refreshProgress();
    if (toc && sectionId) refreshPartMarks(toc, sectionId);
  });
}
