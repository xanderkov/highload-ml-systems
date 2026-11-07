import { run } from "../api.js";
import { isDone, markDone } from "../progress.js";
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
    <p class="block-goal${params.hide_target ? " is-veiled" : ""}"><code>${escapeHtml(
      params.target
    )}</code></p>
    <div class="editor"></div>
    <div class="controls">
      <button class="run" type="button">Проверить</button>
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
  });

  // Порог задания можно спрятать до первого запуска (hide_target). Нужен он
  // там, где смысл упражнения — дать студенту самому увидеть разницу: строка
  // «нужно ускорить втрое» выдала бы развязку раньше, чем он успел замерить.
  const goal = element.querySelector(".block-goal");

  const result = element.querySelector(".result");
  const button = element.querySelector(".run");
  const status = element.querySelector(".status");

  function setDone() {
    element.classList.add("is-done");
    element.classList.remove("is-failed");
    status.textContent = "готово";
  }

  if (isDone(sectionId, blockId)) setDone();

  element.querySelector(".reset").addEventListener("click", () => {
    editor.setValue(starter, -1);
    editor.focus();
  });

  button.addEventListener("click", async () => {
    button.disabled = true;
    result.className = "result is-running";
    result.textContent = "Замеряем…";
    status.textContent = "замеряем";
    try {
      const data = await run(sectionId, blockId, editor.getValue());
      goal.classList.remove("is-veiled");
      result.className = "result";
      result.innerHTML = render(data, params);
      highlightCompileError(editor, data);
      if (data.passed) {
        markDone(sectionId, blockId);
        setDone();
      } else {
        element.classList.toggle("is-failed", data.status !== "ok" || !data.correct);
        status.textContent = statusLabel(data);
      }
    } catch (error) {
      result.className = "result";
      result.innerHTML = `<p class="fault">Не получилось запустить: ${escapeHtml(
        error.message || error
      )}</p>`;
      status.textContent = "сбой сервиса";
    } finally {
      button.disabled = false;
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

/** Метрика, операция и порог из строки цели; тот же разбор, что web/app/jobs.py. */
function parseTarget(target) {
  const match = /^\s*(\w+)\s*([<>]=?)\s*([\d.]+)\s*$/.exec(String(target || ""));
  return match ? { metric: match[1], op: match[2], value: Number(match[3]) } : null;
}

function isCustomMetric(params) {
  const parsed = parseTarget(params.target);
  return Boolean(parsed && parsed.metric !== "speedup");
}

function formatMetric(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? String(Number(value.toPrecision(4)))
    : "—";
}

function metricRows(data) {
  const cell = (metrics) =>
    Object.entries(metrics || {})
      .map(([name, value]) => `${escapeHtml(name)} = ${formatMetric(value)}`)
      .join(", ");
  return `<tr><td>стартовый код</td><td>${cell(data.baseline_metrics)}</td></tr>
      <tr><td>ваш код</td><td>${cell(data.metrics)}</td><td>${correctness(data.correct)}</td></tr>`;
}

function render(data, params) {
  const problem = renderProblem(data);
  if (problem) return problem;

  if (isCustomMetric(params)) {
    return `${verdict(data, params)}
    <table class="numbers">
      ${metricRows(data)}
      <tr><td>время, стартовый код</td><td>${formatMs(data.baseline_ms)}</td></tr>
      <tr><td>время, ваш код</td><td>${formatMs(data.student_ms)}</td></tr>
      <tr><td>разброс замеров</td><td>${data.spread_pct.toFixed(1)} %</td></tr>
    </table>
    ${renderCompileCommand(data)}`;
  }

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

/** Плашка зачёта: единственная сплошная заливка и единственная смена
    полярности на странице. Полоса сравнивает результат с порогом. */
function passBand(data, params) {
  if (isCustomMetric(params)) return metricBand(data, params);
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

/** Плашка зачёта для метрики, отличной от ускорения: значение и порог. */
function metricBand(data, params) {
  const { metric, op, value } = parseTarget(params.target);
  const actual = (data.metrics || {})[metric];
  return `<div class="verdict">
      <div class="verdict-row">
        <div class="verdict-num">${formatMetric(actual)}</div>
        <div>
          <div class="verdict-word">${escapeHtml(metric)} = ${formatMetric(actual)}</div>
          <div class="verdict-meta">порог ${escapeHtml(op)} ${value}</div>
        </div>
      </div>
    </div>`;
}

/** Харнесс объясняет расхождение в stderr (dtype, форма, max diff, checksum):
    без этого студент видит только «не совпадает» и не знает, что чинить. */
function diagnostics(data) {
  const text = typeof data.stderr === "string" ? data.stderr.trim() : "";
  if (!text) return "";
  return `<details class="compile-command harness-log" open>
    <summary>Что сообщила проверка</summary>
    <pre>${escapeHtml(text)}</pre>
  </details>`;
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
    return `<p class="bad">Результат разошёлся со стартовым кодом — оптимизация что-то сломала.</p>${hint}${diagnostics(data)}`;
  }

  // Код верен, но порог не взят. Это не ошибка, а недобор, и выглядеть он
  // должен иначе, чем сломанный код: студенту нужно продолжать, а не чинить.
  const got = isCustomMetric(params)
    ? formatMetric((data.metrics || {})[parseTarget(params.target).metric])
    : formatSpeedup(data.speedup);
  return `<p class="warn">Не хватило: нужно <code>${escapeHtml(
    params.target
  )}</code>, получилось ${got}.</p>`;
}
