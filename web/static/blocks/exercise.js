import { run } from "../api.js";
import { isDone, markDone } from "../progress.js";
import {
  escapeHtml,
  formatMs,
  formatSpeedup,
  renderFault,
  renderLog,
  renderProblem,
  statusLabel,
} from "../result.js";
import { aceTheme } from "../theme.js";

// Задание: редактор со стартовым кодом, кнопка «Проверить» и результат.
// Состояние карточки — data-state (idle | running | pass | fail | error);
// цвета состояний описаны в app.css (.block-card, .status-badge), поэтому
// здесь нет ни одного класса, собранного из кусков строки.

const RUN_LABEL = "Проверить";

export function mount(element, { sectionId, blockId, params }) {
  const number = [...document.querySelectorAll('.block[data-kind="exercise"]')].indexOf(element) + 1;
  element.classList.add("exercise", "block-card");
  element.dataset.state = "idle";
  element.innerHTML = `
    <div class="block-head">
      <span class="font-semibold text-ink">Задание${number > 0 ? ` ${number}` : ""}</span>
      <span class="status status-badge">не запускалось</span>
    </div>
    <div class="px-5 pt-4">
      <h3 class="text-lg leading-snug font-semibold text-ink">${escapeHtml(params.title)}</h3>
      <p class="mt-1 text-sm text-muted">Цель: <code class="font-mono text-ink">${escapeHtml(params.target)}</code></p>
    </div>
    <div class="editor mx-5 mt-4 rounded-md border border-line"></div>
    <div class="flex flex-wrap items-center gap-2 px-5 py-4">
      <button class="run btn btn-primary" type="button">${RUN_LABEL}</button>
      <button class="reset btn" type="button">Вернуть исходный код</button>
    </div>
    <div class="result px-5 pb-5 empty:hidden" aria-live="polite"></div>`;

  const starter = params.starter_code || "";
  const editor = ace.edit(element.querySelector(".editor"), {
    mode: "ace/mode/python",
    theme: aceTheme(),
    value: starter,
    minLines: 12,
    maxLines: 40,
    fontSize: 13,
    showPrintMargin: false,
    useSoftTabs: true,
    tabSize: 4,
  });
  document.addEventListener("course:theme", () => editor.setTheme(aceTheme()));

  const result = element.querySelector(".result");
  const button = element.querySelector(".run");
  const status = element.querySelector(".status");

  const setState = (state, label) => {
    element.dataset.state = state;
    status.textContent = label;
  };

  if (isDone(sectionId, blockId)) setState("pass", "зачтено");

  element.querySelector(".reset").addEventListener("click", () => {
    editor.setValue(starter, -1);
    editor.focus();
  });

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Выполняется…';
    setState("running", "выполняется");
    result.innerHTML = "";
    try {
      const data = await run(sectionId, blockId, editor.getValue());
      result.innerHTML = render(data, params);
      if (data.passed) {
        markDone(sectionId, blockId);
        setState("pass", "зачтено");
      } else if (data.status !== "ok") {
        setState("error", statusLabel(data));
      } else {
        setState("fail", statusLabel(data));
      }
    } catch (error) {
      result.innerHTML = renderFault(error);
      setState("error", "сбой сервиса");
    } finally {
      button.disabled = false;
      button.textContent = RUN_LABEL;
    }
  });
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

function correctness(correct) {
  return correct
    ? '<span class="text-good">✓ совпадает с ожидаемым</span>'
    : '<span class="text-bad">✕ не совпадает с ожидаемым</span>';
}

function row(label, value, extra = "") {
  return `<tr class="border-t border-line">
      <td class="py-1.5 pr-4 text-muted">${label}</td>
      <td class="py-1.5 pr-4 font-mono text-ink tabular-nums">${value}</td>
      <td class="py-1.5">${extra}</td>
    </tr>`;
}

function numbers(rows) {
  return `<div class="mt-4 overflow-x-auto"><table class="w-full text-sm">${rows.join("")}</table></div>`;
}

function metricCell(metrics) {
  return Object.entries(metrics || {})
    .map(([name, value]) => `${escapeHtml(name)} = ${formatMetric(value)}`)
    .join(", ");
}

function render(data, params) {
  const problem = renderProblem(data);
  if (problem) return problem;

  const spread = row("разброс замеров", `${data.spread_pct.toFixed(1)} %`);
  if (isCustomMetric(params)) {
    return `${verdict(data, params)}${numbers([
      row("стартовый код", metricCell(data.baseline_metrics)),
      row("ваш код", metricCell(data.metrics), correctness(data.correct)),
      row("время, стартовый код", formatMs(data.baseline_ms)),
      row("время, ваш код", formatMs(data.student_ms)),
      spread,
    ])}`;
  }
  return `${verdict(data, params)}${numbers([
    row("стартовый код", formatMs(data.baseline_ms)),
    row("ваш код", formatMs(data.student_ms), correctness(data.correct)),
    row("ускорение", formatSpeedup(data.speedup)),
    spread,
  ])}`;
}

/** Зачёт: крупное число и полоса «порог → результат». */
function passBand(data, params) {
  if (isCustomMetric(params)) return metricBand(data, params);
  const threshold = thresholdOf(params.target);
  const speedup = data.speedup;
  const margin = threshold && Number.isFinite(speedup) ? (speedup / threshold).toFixed(1) : null;

  // Запас ограничен сверху, иначе при ускорении в сотни раз полоса порога
  // схлопывается в невидимую нить и сравнивать становится не с чем.
  const over = threshold ? Math.min(Math.max(speedup - threshold, 0), threshold * 11) : 0;
  const bar = threshold
    ? `<div class="mt-4 flex h-1.5 overflow-hidden rounded-full bg-surface">
         <span class="bg-line" style="flex: ${threshold}"></span>
         <span class="bg-good" style="flex: ${over || 0.001}"></span>
       </div>
       <div class="mt-1 flex justify-between text-xs text-muted"><span>порог ${threshold}×</span><span>ваш результат</span></div>`
    : "";

  return `<div class="flex flex-wrap items-end gap-x-5 gap-y-1">
      <div class="font-mono text-4xl font-bold text-good tabular-nums">${formatSpeedup(speedup)}</div>
      <div class="pb-1 text-sm">
        <div class="font-medium text-ink">быстрее стартового кода</div>
        ${margin ? `<div class="text-muted">порог ${threshold}× · запас ${margin}×</div>` : ""}
      </div>
    </div>
    ${bar}`;
}

/** Зачёт для метрики, отличной от ускорения: значение и порог. */
function metricBand(data, params) {
  const { metric, op, value } = parseTarget(params.target);
  const actual = (data.metrics || {})[metric];
  return `<div class="flex flex-wrap items-end gap-x-5 gap-y-1">
      <div class="font-mono text-4xl font-bold text-good tabular-nums">${formatMetric(actual)}</div>
      <div class="pb-1 text-sm">
        <div class="font-medium text-ink">${escapeHtml(metric)}</div>
        <div class="text-muted">порог ${escapeHtml(op)} ${value}</div>
      </div>
    </div>`;
}

/** Харнесс объясняет расхождение в stderr (dtype, форма, max diff, checksum):
    без этого студент видит только «не совпадает» и не знает, что чинить. */
function diagnostics(data) {
  const text = typeof data.stderr === "string" ? data.stderr.trim() : "";
  if (!text) return "";
  return `<details class="harness-log mt-3" open>
    <summary class="cursor-pointer text-sm font-medium text-ink">Что сообщила проверка</summary>
    ${renderLog(text)}
  </details>`;
}

function verdict(data, params) {
  if (data.passed) return passBand(data, params);

  if (data.correct === false) {
    return `<p class="font-medium text-bad">Результат разошёлся со стартовым кодом — оптимизация что-то сломала.</p>${diagnostics(data)}`;
  }

  // Код верен, но порог не взят. Это не ошибка, а недобор, и выглядеть он
  // должен иначе, чем сломанный код: студенту нужно продолжать, а не чинить.
  const got = isCustomMetric(params)
    ? formatMetric((data.metrics || {})[parseTarget(params.target).metric])
    : formatSpeedup(data.speedup);
  return `<p class="font-medium text-warn">Не хватило: нужно <code class="font-mono">${escapeHtml(
    params.target
  )}</code>, получилось <span class="font-mono">${got}</span>.</p>`;
}
