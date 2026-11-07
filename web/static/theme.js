// Тема страницы: «как в системе» (по умолчанию), светлая или тёмная.
// Выбор хранится в localStorage под course.theme; до первой отрисовки его
// применяет скрипт в <head> base.html, здесь — кнопка и чтение темы для
// компонентов, которые красятся из JS (Ace, графики).

const KEY = "course.theme";
const ORDER = ["system", "light", "dark"];
const LABEL = { system: "как в системе", light: "светлая", dark: "тёмная" };
const ICON = { system: "◐", light: "☀", dark: "☾" };

function stored() {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function apply(choice) {
  if (choice === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    /* приватный режим: выбор действует до перезагрузки */
  }
}

/** Тема, которая видна сейчас: ручной выбор или системная настройка. */
export function isDark() {
  const forced = document.documentElement.dataset.theme;
  if (forced === "dark") return true;
  if (forced === "light") return false;
  return Boolean(window.matchMedia?.("(prefers-color-scheme: dark)").matches);
}

export function mountThemeToggle() {
  const button = document.querySelector("[data-theme-toggle]");
  if (!button) return;
  let choice = document.documentElement.dataset.theme || stored();
  const render = () => {
    button.textContent = ICON[choice];
    button.setAttribute("aria-label", `Тема: ${LABEL[choice]}`);
    button.title = `Тема: ${LABEL[choice]}`;
  };
  render();
  button.addEventListener("click", () => {
    choice = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
    apply(choice);
    render();
    document.dispatchEvent(new CustomEvent("course:theme"));
  });
  // Смена системной темы при выборе «как в системе» тоже меняет вид.
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
    if (choice === "system") document.dispatchEvent(new CustomEvent("course:theme"));
  });
}

/** Тема Ace под текущую тему страницы. */
export function aceTheme() {
  return isDark() ? "ace/theme/github_dark" : "ace/theme/github";
}

/** Значение CSS-переменной страницы (токена из app.css). */
export function cssVar(name, fallback = "") {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Цвета графиков из токенов: серии по порядку, сетка, подписи осей. */
export function chartColors() {
  return {
    series: [1, 2, 3, 4, 5].map((n) => cssVar(`--color-series-${n}`, "#4f46e5")),
    grid: cssVar("--color-line", "#e2e8f0"),
    axis: cssVar("--color-muted", "#64748b"),
  };
}
