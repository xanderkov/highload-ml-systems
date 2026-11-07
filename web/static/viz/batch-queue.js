// Dynamic batching на временной шкале: запросы приходят, батчер собирает их
// в окно (до max_batch_size штук или max_queue_delay после первого), батч
// уходит в модель. Модель занята, пока считает, — запросы за это время ждут
// в очереди и попадают в следующий батч.
//
// Поток запросов детерминированный (фиксированное зерно), чтобы картинка не
// менялась от перезагрузки. Время модели условное: 2 мс на вызов плюс 0,5 мс
// на элемент — порядок величин widemodel из замера подглавы 2.

const SPAN_MS = 60;
const MODEL_FIXED_MS = 2;
const MODEL_PER_ITEM_MS = 0.5;
const LOADS = {
  rare: { label: "редкие запросы", meanGapMs: 5 },
  busy: { label: "частые запросы", meanGapMs: 0.8 },
};
const WIDTH = 720;
const LEFT = 70;
const RIGHT = 12;
const LANES = { arrivals: 26, window: 64, model: 102 };
const AXIS_Y = 132;

function plural(n, one, few, many) {
  const m = n % 100;
  if (m >= 11 && m <= 14) return many;
  const d = n % 10;
  if (d === 1) return one;
  return d >= 2 && d <= 4 ? few : many;
}

/** mulberry32: маленький детерминированный генератор, [0, 1). */
function random(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Моменты прихода запросов: экспоненциальные промежутки со средним meanGapMs. */
export function arrivals(meanGapMs, spanMs = SPAN_MS, seed = 7) {
  const next = random(seed);
  const times = [];
  let t = 0;
  for (;;) {
    t += -Math.log(1 - next()) * meanGapMs;
    if (t > spanMs) return times;
    times.push(t);
  }
}

/** Батчер и модель. Возвращает батчи: окно сбора, вызов модели, индексы запросов. */
export function simulate(times, maxDelayMs, maxBatch) {
  const batches = [];
  let modelFree = 0;
  let i = 0;
  while (i < times.length) {
    // Батчер берёт первый запрос, как только модель свободна и запрос есть.
    const start = Math.max(modelFree, times[i]);
    const deadline = start + maxDelayMs;
    const members = [i++];
    // Всё, что уже ждёт в очереди или придёт до дедлайна, — в этот батч.
    while (members.length < maxBatch && i < times.length && times[i] <= deadline) members.push(i++);
    const full = members.length === maxBatch;
    // Полный батч уходит сразу; неполный ждёт дедлайна (при 0 — не ждёт).
    const close = full ? Math.max(start, times[members[members.length - 1]]) : deadline;
    const done = close + MODEL_FIXED_MS + MODEL_PER_ITEM_MS * members.length;
    batches.push({ start, close, done, members });
    modelFree = done;
  }
  return batches;
}

function stats(times, batches) {
  const latency = [];
  for (const batch of batches) for (const i of batch.members) latency.push(batch.done - times[i]);
  const mean = latency.reduce((a, b) => a + b, 0) / Math.max(latency.length, 1);
  return {
    batches: batches.length,
    meanSize: times.length / Math.max(batches.length, 1),
    meanLatency: mean,
    maxLatency: Math.max(0, ...latency),
  };
}

const fmt = (x, digits = 1) => x.toFixed(digits).replace(".", ",");

export function mount(element, { params = {} } = {}) {
  const delays = Array.isArray(params.delays) && params.delays.length ? params.delays.map(Number) : [0, 2, 10];
  const maxBatch = Number(params.max_batch_size) || 8;
  let delay = delays[Math.min(1, delays.length - 1)];
  let load = "busy";

  element.classList.add("viz", "batch-queue", "block-card");
  element.innerHTML = `
    <div class="block-head"><span>Сбор батча на временной шкале</span><span>max_batch_size = ${maxBatch}</span></div>
    <div class="controls bq-controls">
      <span class="bq-group" role="radiogroup" aria-label="max_queue_delay">
        <span class="bq-group-label">max_queue_delay</span>
        ${delays.map((d) => `<button class="btn" type="button" role="radio" data-delay="${d}" aria-checked="false">${fmt(d, 0)} мс</button>`).join("")}
      </span>
      <span class="bq-group" role="radiogroup" aria-label="Нагрузка">
        ${Object.entries(LOADS).map(([key, l]) => `<button class="btn" type="button" role="radio" data-load="${key}" aria-checked="false">${l.label}</button>`).join("")}
      </span>
    </div>
    <div class="bq-stage"><svg class="bq-svg" viewBox="0 0 ${WIDTH} 150" role="img" aria-label="Временная шкала запросов, окон сбора и вызовов модели"></svg></div>
    <p class="bq-stats" role="status"></p>
    <p class="bq-help">Точки — запросы; цвет точки — номер батча, в который она попала. Полоса «сбор» — окно, пока батчер добирает запросы; «модель» — вызов модели с размером батча. Модель условная: ${MODEL_FIXED_MS} мс на вызов плюс ${fmt(MODEL_PER_ITEM_MS)} мс на элемент.</p>`;

  const svg = element.querySelector(".bq-svg");
  const status = element.querySelector(".bq-stats");
  const x = (t) => LEFT + (t / SPAN_MS) * (WIDTH - LEFT - RIGHT);

  function render() {
    for (const button of element.querySelectorAll("[data-delay]")) {
      button.setAttribute("aria-checked", String(Number(button.dataset.delay) === delay));
    }
    for (const button of element.querySelectorAll("[data-load]")) {
      button.setAttribute("aria-checked", String(button.dataset.load === load));
    }

    const times = arrivals(LOADS[load].meanGapMs);
    const batches = simulate(times, delay, maxBatch);
    const owner = new Map();
    batches.forEach((batch, k) => batch.members.forEach((i) => owner.set(i, k)));

    const parts = [];
    for (const [lane, y] of Object.entries(LANES)) {
      const label = { arrivals: "запросы", window: "сбор", model: "модель" }[lane];
      parts.push(`<text class="bq-lane-label" x="0" y="${y + 4}">${label}</text>`);
      parts.push(`<line class="bq-lane" x1="${LEFT}" x2="${WIDTH - RIGHT}" y1="${y}" y2="${y}"></line>`);
    }
    for (let t = 0; t <= SPAN_MS; t += 10) {
      parts.push(`<line class="bq-tick" x1="${x(t)}" x2="${x(t)}" y1="${AXIS_Y - 4}" y2="${AXIS_Y}"></line>`);
      parts.push(`<text class="bq-axis-label" x="${x(t)}" y="${AXIS_Y + 13}" text-anchor="middle">${t} мс</text>`);
    }
    batches.forEach((batch, k) => {
      if (batch.start > SPAN_MS) return;
      const odd = k % 2 === 1;
      const end = Math.min(batch.close, SPAN_MS);
      if (end > batch.start) {
        parts.push(`<rect class="${odd ? "bq-window bq-odd" : "bq-window"}" x="${x(batch.start)}" y="${LANES.window - 7}" width="${Math.max(x(end) - x(batch.start), 1.5)}" height="14" rx="3"></rect>`);
      } else {
        parts.push(`<line class="bq-instant" x1="${x(batch.start)}" x2="${x(batch.start)}" y1="${LANES.window - 7}" y2="${LANES.window + 7}"></line>`);
      }
      if (batch.close <= SPAN_MS) {
        const runEnd = Math.min(batch.done, SPAN_MS);
        parts.push(`<rect class="${odd ? "bq-run bq-odd" : "bq-run"}" x="${x(batch.close)}" y="${LANES.model - 9}" width="${Math.max(x(runEnd) - x(batch.close), 1.5)}" height="18" rx="3"></rect>`);
        if (x(runEnd) - x(batch.close) > 12) {
          parts.push(`<text class="bq-run-label" x="${(x(batch.close) + x(runEnd)) / 2}" y="${LANES.model + 4}" text-anchor="middle">${batch.members.length}</text>`);
        }
      }
    });
    times.forEach((t, i) => {
      const odd = (owner.get(i) ?? 0) % 2 === 1;
      parts.push(`<circle class="${odd ? "bq-dot bq-odd" : "bq-dot"}" cx="${x(t)}" cy="${LANES.arrivals}" r="3.5"></circle>`);
    });
    svg.innerHTML = parts.join("");

    const s = stats(times, batches);
    status.textContent =
      `${times.length} ${plural(times.length, "запрос", "запроса", "запросов")} за ${SPAN_MS} мс → ` +
      `${s.batches} ${plural(s.batches, "батч", "батча", "батчей")}, в среднем по ${fmt(s.meanSize)}; ` +
      `задержка запроса в среднем ${fmt(s.meanLatency)} мс, максимум ${fmt(s.maxLatency)} мс.`;
  }

  element.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.delay !== undefined) delay = Number(button.dataset.delay);
    if (button.dataset.load !== undefined) load = button.dataset.load;
    render();
  });
  render();
}
