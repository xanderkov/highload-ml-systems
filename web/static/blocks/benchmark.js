import { run } from "../api.js";
import { escapeHtml, renderFault, renderProblem, statusLabel } from "../result.js";
import { aceTheme, chartColors } from "../theme.js";

// Замер: series-харнесс возвращает линии, блок рисует их графиком uPlot.
// Если у блока есть starter, над графиком — редактор, и замер идёт по коду
// студента. Состояние карточки — data-state, как у задания (см. app.css).

// Подписи осей приходят из блока в section.md (x_label, y_label); это
// запасные значения на случай, если блок их не задал.
const CHART_DEFAULTS = {
  x_label: "x",
  y_label: "y",
};
const CHART_HEIGHT = 300;
const RUN_LABEL = "Замерить";

/** Русское склонение после числа: 1 линия, 2 линии, 5 линий. */
function plural(n, one, few, many) {
  const m = n % 100;
  if (m >= 11 && m <= 14) return many;
  const d = n % 10;
  if (d === 1) return one;
  return d >= 2 && d <= 4 ? few : many;
}

export function mount(element, { sectionId, blockId, params }) {
  const editable = params.starter_code !== undefined;
  element.classList.add("benchmark", "block-card");
  element.dataset.state = "idle";
  element.innerHTML = `
    <div class="block-head">
      <span class="font-semibold text-ink">Замер</span>
      <span class="status status-badge">не запускалось</span>
    </div>
    ${params.title ? `<h3 class="px-5 pt-4 text-lg leading-snug font-semibold text-ink">${escapeHtml(params.title)}</h3>` : ""}
    ${editable ? '<div class="editor mx-5 mt-4 rounded-md border border-line"></div>' : ""}
    <div class="flex flex-wrap items-center gap-2 px-5 py-4">
      <button class="run btn btn-primary" type="button">${RUN_LABEL}</button>
      ${editable ? '<button class="reset btn" type="button">Вернуть исходный код</button>' : ""}
    </div>
    <div class="result px-5 pb-4 empty:hidden" aria-live="polite"></div>
    <div class="chart px-3 pb-2 empty:hidden"></div>
    <p class="caption px-5 pb-4 text-sm text-muted empty:hidden"></p>`;

  const editor = editable
    ? ace.edit(element.querySelector(".editor"), {
        mode: "ace/mode/python",
        theme: aceTheme(),
        value: params.starter_code,
        minLines: 9,
        maxLines: 40,
        fontSize: 13,
        showPrintMargin: false,
        tabSize: 4,
      })
    : null;
  const button = element.querySelector(".run");
  const result = element.querySelector(".result");
  const chart = element.querySelector(".chart");
  const caption = element.querySelector(".caption");
  const status = element.querySelector(".status");
  const reset = element.querySelector(".reset");
  reset?.addEventListener("click", () => editor.setValue(params.starter_code, -1));

  // Цвета графика берутся из токенов в момент рисования, поэтому при смене
  // темы последний результат перерисовывается.
  let lastLines = null;
  document.addEventListener("course:theme", () => {
    editor?.setTheme(aceTheme());
    if (lastLines) drawLines(chart, lastLines, params);
  });

  const setState = (state, label) => {
    element.dataset.state = state;
    status.textContent = label;
  };

  button.addEventListener("click", async () => {
    const code = editor?.getValue() ?? "";
    if (reset) reset.disabled = true;
    button.disabled = true;
    button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Выполняется…';
    editor?.setReadOnly(true);
    setState("running", "идёт замер");
    result.innerHTML = "";
    caption.textContent = "";
    disposeChart(chart);
    lastLines = null;
    try {
      const data = await run(sectionId, blockId, code);
      const problem = renderProblem(data);
      if (problem) {
        result.innerHTML = problem;
        setState("error", statusLabel(data));
        return;
      }
      lastLines = data.lines || [];
      const count = lastLines.length;
      setState("idle", `${count} ${plural(count, "линия", "линии", "линий")}`);
      drawLines(chart, lastLines, params);
      caption.textContent = params.caption || "";
    } catch (error) {
      result.innerHTML = renderFault(error);
      setState("error", "сбой сервиса");
    } finally {
      button.disabled = false;
      button.textContent = RUN_LABEL;
      if (reset) reset.disabled = false;
      editor?.setReadOnly(false);
    }
  });
}

// Несколько линий на одном графике: каждая линия — отдельная серия uPlot.
// uPlot требует общую ось X, поэтому x-значения всех линий объединяются, а
// там, где у линии нет точки, стоит null (с spanGaps линия идёт через пропуск).
function drawLines(container, lines, params) {
  const options = { ...CHART_DEFAULTS, ...params };
  const xs = [...new Set(lines.flatMap((line) => line.points.map((point) => point.x)))].sort((a, b) => a - b);
  const columns = lines.map((line) => {
    const byX = new Map(line.points.map((point) => [point.x, point.y]));
    return xs.map((x) => (byX.has(x) ? byX.get(x) : null));
  });

  const positive = (values) => values.every((value) => value === null || value > 0);
  const logY = options.log_y === true && columns.every(positive);
  const colors = chartColors();
  const axis = (label) => ({
    label,
    stroke: colors.axis,
    grid: { stroke: colors.grid, width: 1 },
    ticks: { stroke: colors.grid, width: 1 },
    font: "12px Inter Variable, system-ui, sans-serif",
    labelFont: "12px Inter Variable, system-ui, sans-serif",
  });

  // Замерить можно сколько угодно раз: старый график и его обработчик resize
  // снимаются, иначе каждый повторный клик оставлял бы подписку на
  // уничтоженный график.
  disposeChart(container);
  const plot = new uPlot(
    {
      width: container.clientWidth || 640,
      height: CHART_HEIGHT,
      scales: { x: { time: false }, y: logY ? { distr: 3 } : {} },
      axes: [axis(options.x_label), axis(options.y_label)],
      legend: { show: true },
      series: [
        { label: options.x_label },
        ...lines.map((line, index) => ({
          label: line.name,
          stroke: colors.series[index % colors.series.length],
          width: 2,
          spanGaps: true,
          points: { show: true, size: 5 },
        })),
      ],
    },
    [xs, ...columns],
    container
  );

  const resize = () => plot.setSize({ width: container.clientWidth || 640, height: CHART_HEIGHT });
  window.addEventListener("resize", resize);
  container._chart = { plot, resize };
}

function disposeChart(container) {
  const previous = container._chart;
  if (previous) {
    window.removeEventListener("resize", previous.resize);
    previous.plot.destroy();
    container._chart = null;
  }
  container.innerHTML = "";
}
