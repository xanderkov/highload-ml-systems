import { run } from "../api.js";
import { escapeHtml, renderProblem, statusLabel } from "../result.js";

// Подписи осей приходят из блока в section.md (x_label, y_label); это
// запасные значения на случай, если блок их не задал.
const CHART_DEFAULTS = {
  x_label: "x",
  y_label: "y",
};

/** Русское склонение после числа: 1 линия, 2 линии, 5 линий. */
function plural(n, one, few, many) {
  const m = n % 100;
  if (m >= 11 && m <= 14) return many;
  const d = n % 10;
  if (d === 1) return one;
  return d >= 2 && d <= 4 ? few : many;
}

export function mount(element, { sectionId, blockId, params, lang }) {
  element.classList.add("benchmark");
  element.innerHTML = `
    <div class="block-head">
      <span>${escapeHtml(params.title || "Замер")}</span>
      <span class="status">не запускалось</span>
    </div>
    <div class="controls"><button class="run" type="button">Замерить</button>${params.starter_code !== undefined ? '<button class="reset" type="button">Вернуть исходный код</button>' : ""}</div>
    ${params.starter_code !== undefined ? '<div class="editor"></div>' : ""}
    <div class="result" aria-live="polite"></div>
    <div class="chart"></div>
    <p class="caption"></p>`;

  const editor = params.starter_code === undefined ? null : ace.edit(element.querySelector(".editor"), {
    mode: "ace/mode/python", theme: "ace/theme/github_dark", value: params.starter_code,
    minLines: 9, maxLines: 40, fontSize: 13, showPrintMargin: false, tabSize: 4,
  });
  const button = element.querySelector(".run");
  const result = element.querySelector(".result");
  const chart = element.querySelector(".chart");
  const caption = element.querySelector(".caption");
  const status = element.querySelector(".status");

  const reset = element.querySelector(".reset");
  reset?.addEventListener("click", () => editor.setValue(params.starter_code, -1));
  button.addEventListener("click", async () => {
    const code = editor?.getValue() ?? "";
    if (reset) reset.disabled = true;
    button.disabled = true;
    editor?.setReadOnly(true);
    result.className = "result is-running";
    result.textContent = "Замеряем…";
    caption.textContent = "";
    status.textContent = "идёт замер";
    element.classList.remove("is-failed");
    disposeChart(chart);
    chart.innerHTML = "";
    try {
      const data = await run(sectionId, blockId, code);
      result.className = "result";
      const problem = renderProblem(data);
      if (problem) {
        result.innerHTML = problem;
        element.classList.add("is-failed");
        status.textContent = statusLabel(data);
        return;
      }
      const count = data.lines?.length || 0;
      status.textContent = `${count} ${plural(count, "линия", "линии", "линий")}`;
      result.innerHTML = "";
      drawLines(chart, data.lines || [], params);
      caption.textContent = params.caption || "";
    } catch (error) {
      result.className = "result";
      result.innerHTML = `<p class="fault">Не получилось запустить: ${escapeHtml(
        error.message || error
      )}</p>`;
      element.classList.add("is-failed");
      status.textContent = "сбой сервиса";
    } finally {
      button.disabled = false;
      if (reset) reset.disabled = false;
      editor?.setReadOnly(false);
    }
  });
}

// Несколько линий на одном графике: каждая линия — отдельная серия uPlot.
// uPlot требует общую ось X, поэтому x-значения всех линий объединяются, а
// там, где у линии нет точки, стоит null (с spanGaps линия идёт через пропуск).
const LINE_FALLBACKS = ["#2f6feb", "#2da44e", "#d1242f", "#8250df", "#bf8700", "#1a7f8e"];

function drawLines(container, lines, params) {
  const options = { ...CHART_DEFAULTS, ...params };
  const xs = [...new Set(lines.flatMap((line) => line.points.map((point) => point.x)))].sort((a, b) => a - b);
  const columns = lines.map((line) => {
    const byX = new Map(line.points.map((point) => [point.x, point.y]));
    return xs.map((x) => (byX.has(x) ? byX.get(x) : null));
  });

  const positive = (values) => values.every((value) => value === null || value > 0);
  const logY = options.log_y === true && columns.every(positive);
  const fg = cssVar(container, "--color-fg", "#1a1a1a");

  disposeChart(container);
  container.innerHTML = "";
  const plot = new uPlot(
    {
      width: container.clientWidth || 640,
      height: 300,
      scales: { x: { time: false }, y: logY ? { distr: 3 } : {} },
      axes: [
        { label: options.x_label, stroke: fg },
        { label: options.y_label, stroke: fg },
      ],
      legend: { show: true },
      series: [
        { label: options.x_label },
        ...lines.map((line, index) => ({
          label: line.name,
          stroke: LINE_FALLBACKS[index % LINE_FALLBACKS.length],
          width: 2,
          spanGaps: true,
          points: { show: true },
        })),
      ],
    },
    [xs, ...columns],
    container
  );

  const resize = () => plot.setSize({ width: container.clientWidth || 640, height: 300 });
  window.addEventListener("resize", resize);
  container._chart = { plot, resize };
}

function disposeChart(container) {
  const previous = container._chart;
  if (!previous) return;
  window.removeEventListener("resize", previous.resize);
  previous.plot.destroy();
  container._chart = null;
}

function cssVar(element, name, fallback) {
  const value = getComputedStyle(element).getPropertyValue(name).trim();
  return value || fallback;
}
