const KEY = "course.progress";

// Обращение к localStorage обёрнуто в try/catch намеренно: в приватном окне и
// при запрете куки-хранилищ сам доступ к свойству бросает, и страница не
// должна из-за этого остаться без редактора.

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}");
  } catch {
    return {};
  }
}

export function markDone(sectionId, blockId) {
  const state = read();
  state[sectionId] = { ...(state[sectionId] || {}), [blockId]: true };
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* приватный режим: прогресс просто не сохранится */
  }
  // Навигация (nav.js) обновляет счётчики по этому событию.
  document.dispatchEvent(new CustomEvent("course:progress"));
}

export function isDone(sectionId, blockId) {
  return Boolean(read()[sectionId]?.[blockId]);
}

/** Сколько из перечисленных заданий раздела зачтено. Без localStorage — 0. */
export function doneCount(sectionId, blockIds) {
  const done = read()[sectionId] || {};
  return blockIds.filter((id) => Boolean(done[id])).length;
}
