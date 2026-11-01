import { run } from "../api.js";
import { isDone, markDone } from "../progress.js";
import { mountIndexTutorial } from "./index-tutorial.js";
import {
  escapeHtml,
  formatMs,
  formatSpeedup,
  renderCompileCommand,
  renderProblem,
  statusLabel,
} from "../result.js";

const LANG_LABEL = { c: "C", python: "Python" };

export function mount(element, { sectionId, blockId, lang, params }) {
  element.classList.add("exercise");
  element.innerHTML = `
    <div class="block-head">
      <span>${escapeHtml(LANG_LABEL[lang] || lang || "")}</span>
      <span class="status">не запускалось</span>
    </div>
    <h3 class="block-title">${escapeHtml(params.title)}</h3>
    <p class="block-goal${params.hide_target || params.guided ? " is-veiled" : ""}"><code>${escapeHtml(
      params.target
    )}</code></p>
    ${params.guided ? '<p class="step" aria-live="polite"></p>' : ""}
    <div class="editor"></div>
    <div class="controls">
      <button class="run" type="button">${params.guided ? "Замерить" : "Проверить"}</button>
      <button class="reset" type="button">Вернуть исходный код</button>
    </div>
    <div class="result" aria-live="polite"></div>`;

  const starter = params.starter_code || "";
  const editor = ace.edit(element.querySelector(".editor"), {
    mode: lang === "python" ? "ace/mode/python" : "ace/mode/c_cpp",
    // Тема страницы одна, тёмная — редактор не должен зависеть от системной
    // настройки, иначе на светлой системе он вылезал бы белым пятном.
    theme: "ace/theme/github_dark",
    value: starter,
    minLines: 12,
    maxLines: 40,
    fontSize: 13,
    showPrintMargin: false,
    useSoftTabs: true,
    tabSize: 4,
    readOnly: Boolean(params.guided),
  });

  // Порог задания можно спрятать до первого запуска (hide_target). Нужен он
  // там, где смысл упражнения — дать студенту самому увидеть разницу: строка
  // «нужно ускорить втрое» выдала бы развязку раньше, чем он успел замерить.
  const goal = element.querySelector(".block-goal");

  // Стенд (guided): редактор заперт, пока не сделан первый замер, вердикта нет
  // вовсе, а замеры копятся списком. Вывод о разнице делает студент, глядя на
  // два числа, — не плашка, которая объявляет ему результат.
  const step = element.querySelector(".step");
  const runs = [];
  if (params.guided) {
    element.classList.add("is-locked");
    if (step) step.textContent = params.hint_start || "";
  }

  const result = element.querySelector(".result");
  const button = element.querySelector(".run");
  const status = element.querySelector(".status");
  const tutorial = params.tutorial === "index-swap"
    ? mountIndexTutorial(element, editor, starter)
    : null;

  function setDone() {
    element.classList.add("is-done");
    element.classList.remove("is-failed");
    status.textContent = params.guided ? `замеров: ${runs.length}` : "готово";
  }

  if (isDone(sectionId, blockId)) setDone();

  element.querySelector(".reset").addEventListener("click", () => {
    editor.setValue(starter, -1);
    editor.focus();
  });

  button.addEventListener("click", async () => {
    tutorial?.running();
    button.disabled = true;
    result.className = "result is-running";
    result.textContent = "Замеряем…";
    status.textContent = "замеряем";
    try {
      const data = await run(sectionId, blockId, editor.getValue());
      if (!params.guided) goal.classList.remove("is-veiled");
      result.className = "result";
      if (params.guided && data.status === "ok") {
        runs.push({ ms: data.student_ms, spread: data.spread_pct, correct: data.correct });
        if (data.correct && runs.filter((entry) => entry.correct).length === 1) {
          editor.setReadOnly(false);
          element.classList.remove("is-locked");
          if (step) step.textContent = params.hint_next || "";
        }
      }
      result.innerHTML = params.guided ? renderRuns(runs, data) : render(data, params);
      highlightCompileError(editor, data);
      tutorial?.settled(data);
      if (data.passed) {
        markDone(sectionId, blockId);
        setDone();
      } else {
        element.classList.toggle("is-failed", data.status !== "ok" || !data.correct);
        status.textContent =
          params.guided && data.status === "ok"
            ? `замеров: ${runs.length}`
            : statusLabel(data);
      }
    } catch (error) {
      result.className = "result";
      result.innerHTML = `<p class="fault">Не получилось запустить: ${escapeHtml(
        error.message || error
      )}</p>`;
      status.textContent = "сбой сервиса";
      tutorial?.settled({ status: "service_error" });
    } finally {
      button.disabled = tutorial?.blocksRun() ?? false;
    }
  });
}

function highlightCompileError(editor, data) {
  // Номер строки runner отдаёт только для кода студента (юнит "b"); для
  // baseline и стадии линковки там всегда null — подсвечивать нечего.
  editor.session.clearAnnotations();
  if (data.status === "compile_error" && data.line) {
    editor.session.setAnnotations([
      { row: data.line - 1, column: 0, text: data.message || "Ошибка компиляции", type: "error" },
    ]);
  }
}

/** Порог из строки цели вида "speedup >= 3". null, если не разобрался. */
function thresholdOf(target) {
  const match = /([\d.]+)\s*$/.exec(String(target || ""));
  const value = match ? Number(match[1]) : NaN;
  return Number.isFinite(value) && value > 0 ? value : null;
}

function render(data, params) {
  const problem = renderProblem(data);
  if (problem) return problem;

  return `${verdict(data, params)}
    <table class="numbers">
      <tr><td>стартовый код</td><td>${formatMs(data.baseline_ms)}</td></tr>
      <tr><td>ваш код</td><td>${formatMs(data.student_ms)}</td><td>${correctness(data.correct)}</td></tr>
      <tr><td>ускорение</td><td>${formatSpeedup(data.speedup)}</td></tr>
      <tr><td>разброс замеров</td><td>${data.spread_pct.toFixed(1)} %</td></tr>
    </table>
    ${renderCompileCommand(data)}`;
}

function correctness(correct) {
  return correct
    ? '<span class="check-result is-match">✓ Результат совпадает с ожидаемым</span>'
    : '<span class="check-result is-mismatch">✕ Результат не совпадает с ожидаемым</span>';
}

/** Keep every completed measurement, including incorrect results. */
function renderRuns(runs, data) {
  const problem = renderProblem(data);

  const rows = runs
    .map(
      (entry, index) =>
        `<tr><td>замер ${index + 1}</td><td>${formatMs(entry.ms)}</td>` +
        `<td>разброс ${entry.spread.toFixed(1)} %</td><td>${correctness(entry.correct)}</td></tr>`
    )
    .join("");

  return `${rows ? `<table class="numbers runs">${rows}</table>` : ""}${problem || ""}${renderCompileCommand(data)}`;
}

/** Плашка зачёта: единственная сплошная заливка и единственная смена
    полярности на странице. Полоса сравнивает результат с порогом. */
function passBand(data, params) {
  const threshold = thresholdOf(params.target);
  const speedup = data.speedup;
  const margin =
    threshold && Number.isFinite(speedup) ? (speedup / threshold).toFixed(1) : null;

  // Запас ограничен сверху, иначе при ускорении в сотни раз полоса порога
  // схлопывается в невидимую нить и сравнивать становится не с чем.
  const track = threshold || 1;
  const over = threshold ? Math.min(Math.max(speedup - threshold, 0), threshold * 11) : 0;

  const bar = threshold
    ? `<div class="verdict-bar">
         <span class="track" style="flex: ${track}"></span>
         <span class="fill" style="flex: ${over || 0.001}"></span>
       </div>
       <div class="verdict-scale"><span>порог ${threshold}×</span><span>ваш результат</span></div>`
    : "";

  return `<div class="verdict">
      <div class="verdict-row">
        <div class="verdict-num">${formatSpeedup(speedup)}</div>
        <div>
          <div class="verdict-word">быстрее стартового кода</div>
          ${margin ? `<div class="verdict-meta">порог ${threshold}× · запас ${margin}×</div>` : ""}
        </div>
      </div>
      ${bar}
    </div>`;
}

function verdict(data, params) {
  if (data.passed) return passBand(data, params);

  if (data.correct === false) {
    // Быстро и неправильно — не оптимизация. Отдельный текст для случая, когда
    // компилятор просто выбросил код, потому что его результат никому не нужен.
    const hint =
      data.speedup >= 1000000
        ? `<p class="hint">Похоже, компилятор выбросил вычисление целиком: его результат
           нигде не используется.</p>`
        : "";
    return `<p class="bad">Результат разошёлся со стартовым кодом — оптимизация что-то сломала.</p>${hint}`;
  }

  // Код верен, но порог не взят. Это не ошибка, а недобор, и выглядеть он
  // должен иначе, чем сломанный код: студенту нужно продолжать, а не чинить.
  return `<p class="warn">Не хватило: нужно <code>${escapeHtml(
    params.target
  )}</code>, получилось ${formatSpeedup(data.speedup)}.</p>`;
}
