import { mount as mountComparison } from "./comparison.js";
import { run } from "../api.js";
import {
  escapeHtml,
  formatMs,
  formatSpeedup,
  renderCompileCommand,
  renderProblem,
  statusLabel,
} from "../result.js";

// Параметры графика приходят из блока в section.md, а не зашиты в код:
// один и тот же sweep рисует и лестницу кэша (по оси X — размер рабочего
// множества), и кривую префетчера (по оси X — шаг обхода). Числа `size` в
// обоих случаях считаются в элементах double, а x_factor переводит их в те
// единицы, в которых подписана ось.
const CHART_DEFAULTS = {
  x_label: "размер",
  y_label: "нс на элемент",
  x_factor: 1,
};

export function mount(element, { sectionId, blockId, params, lang }) {
  if (params.parallel_editors) return mountComparison(element, { sectionId, blockId, params });
  element.classList.add("benchmark");
  element.innerHTML = `
    <div class="block-head">
      <span>${escapeHtml(params.title || "Замер")}</span>
      <span class="status">не запускалось</span>
    </div>
    <div class="controls"><button class="run" type="button">Замерить</button>${params.starter_code !== undefined ? '<button class="reset" type="button">Вернуть исходный код</button>' : ""}</div>
    ${params.starter_code !== undefined ? '<div class="editor"></div>' : ""}
    <div class="result" aria-live="polite"></div>
    <div class="benchmark-history"></div>
    <div class="chart"></div>
    <p class="caption"></p>`;

  const editor = params.starter_code === undefined ? null : ace.edit(element.querySelector(".editor"), {
    mode: lang === "python" ? "ace/mode/python" : "ace/mode/c_cpp", theme: "ace/theme/github_dark", value: params.starter_code,
    minLines: 9, maxLines: 40, fontSize: 13, showPrintMargin: false, tabSize: 4,
  });
  const button = element.querySelector(".run");
  const result = element.querySelector(".result");
  const chart = element.querySelector(".chart");
  const caption = element.querySelector(".caption");
  const status = element.querySelector(".status");

  const reset = element.querySelector(".reset");
  reset?.addEventListener("click", () => editor.setValue(params.starter_code, -1));
  const history = [];
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
      status.textContent = data.series ? `${data.series.length} точек` : data.lines ? `${data.lines.length} линий` : "замер готов";
      if (params.history_parameter && editor && !data.series && !data.lines) {
        const assignment = code.split("\n").find(line => line.trim().startsWith(`${params.history_parameter} =`));
        const value = assignment?.split("=").slice(1).join("=").split("#")[0].trim() || "—";
        const correct = data.correct !== false;
        result.innerHTML = `<p class="${correct ? 'good' : 'bad'}">${correct ? 'Результат совпадает с ожидаемым' : 'Результат не совпадает с ожидаемым'}</p>`;
        history.push({value, ms: data.student_ms, correct});
        element.querySelector(".benchmark-history").innerHTML = `<table class="numbers"><thead><tr><th>${escapeHtml(params.history_parameter)}</th><th>Время</th><th>Результат</th></tr></thead><tbody>${history.map(row => `<tr><td>${escapeHtml(row.value)}</td><td>${formatMs(row.ms)}</td><td>${row.correct ? 'Совпадает' : 'Не совпадает'}</td></tr>`).join('')}</tbody></table>`;
      } else if (params.single_result && !data.series && !data.lines) {
        result.innerHTML = `<p><strong>${formatMs(data.student_ms)}</strong><br>${data.correct ? 'Результат совпадает с ожидаемым' : 'Результат не совпадает с ожидаемым'}</p>`;
      } else if (data.series) {
        result.innerHTML = renderCompileCommand(data);
        drawSweep(chart, data.series, params);
        caption.textContent = params.caption || "";
      } else if (data.lines) {
        result.innerHTML = renderCompileCommand(data);
        drawLines(chart, data.lines, params);
        caption.textContent = params.caption || "";
      } else {
        result.innerHTML = renderPair(data, params) + renderCompileCommand(data);
        caption.textContent = params.caption || "";
      }
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

function drawSweep(container, series, params) {
  const options = { ...CHART_DEFAULTS, ...params };
  const xs = series.map((point) => point.size * Number(options.x_factor));
  // ms_per_element → нс на элемент
  const ys = series.map((point) => point.ms_per_element * 1e6);

  // Логарифмическая шкала (distr: 3) не переносит нулей и отрицательных
  // значений: если хоть один замер выродился в ноль, ось молча схлопнется.
  const positive = (values) => values.every((value) => value > 0);
  const scales = {
    x: positive(xs) ? { distr: 3 } : {},
    y: positive(ys) ? { distr: 3 } : {},
  };

  // Замерить можно сколько угодно раз: старый график и его обработчик resize
  // снимаются, иначе каждый повторный клик оставлял бы за собой подписку на
  // уничтоженный график.
  disposeChart(container);
  container.innerHTML = "";
  const plot = new uPlot(
    {
      width: container.clientWidth || 640,
      height: 300,
      scales,
      axes: [
        { label: options.x_label, stroke: cssVar(container, "--color-fg", "#1a1a1a") },
        { label: options.y_label, stroke: cssVar(container, "--color-fg", "#1a1a1a") },
      ],
      legend: { show: false },
      series: [
        { label: options.x_label },
        {
          label: options.y_label,
          stroke: cssVar(container, "--color-accent", "#2f6feb"),
          width: 2,
          points: { show: true },
        },
      ],
    },
    [xs, ys],
    container
  );

  const resize = () => plot.setSize({ width: container.clientWidth || 640, height: 300 });
  window.addEventListener("resize", resize);
  container._chart = { plot, resize };
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

function renderPair(data, params) {
  const names = params.labels || params.variants || ["вариант A", "вариант B"];
  const [first, second] = names;
  const mismatch =
    data.correct === false
      ? `<p class="bad">Варианты дали разные ответы — это ошибка в материалах курса,
         сравнивать их время бессмысленно.</p>`
      : "";
  // Отношение считается как «второй к первому», а не через data.speedup:
  // speedup = baseline/student, то есть для бенчмарка он показал бы 0.45x там,
  // где студенту нужно прочитать «второй вариант в 2.2 раза дороже».
  const ratio = data.baseline_ms > 0 ? data.student_ms / data.baseline_ms : NaN;
  return `${mismatch}<table class="numbers">
    <tr><td>${escapeHtml(first)}</td><td>${formatMs(data.baseline_ms)}</td></tr>
    <tr><td>${escapeHtml(second)}</td><td>${formatMs(data.student_ms)}</td></tr>
    <tr><td>второй к первому</td><td>${formatSpeedup(ratio)}</td></tr>
    <tr><td>разброс замеров</td><td>${data.spread_pct.toFixed(1)} %</td></tr>
  </table>`;
}

function cssVar(element, name, fallback) {
  const value = getComputedStyle(element).getPropertyValue(name).trim();
  return value || fallback;
}
