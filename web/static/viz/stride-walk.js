// Identical machines driven by one clock; each keeps its own cache and progress.
const LINE = 16;
const HOLD_MS = 60;
const FETCH_MS = 200;

export function mount(element, { params = {}, blockId = "stride-walk" } = {}) {
  const cacheEnabled = params.cache !== false;
  const clockMs = cacheEnabled ? HOLD_MS : 25;
  const helpId = `${blockId}-help`;
  const requested = Number(params.size);
  const size = Number.isInteger(requested) && requested >= (cacheEnabled ? 8 : 4) && requested <= 16 ? requested : 8;
  const values = Array.from({ length: size * size }, (_, i) => i % 9 + 1);
  element.classList.add("viz", "cache-walk", "cache-dual");
  element.innerHTML = `
    <div class="block-head"><span>Два порядка обхода</span><span>${size} × ${size} · int</span></div>
    <div class="cs-dual-stage" tabindex="0" aria-label="Параллельное сравнение обходов" aria-describedby="${helpId}">
      <div class="cs-dual-scroll"><div class="cs-lanes">
        <section class="cs-lane" data-order="cols" aria-label="Обход по столбцам"></section>
        <section class="cs-lane" data-order="rows" aria-label="Обход по строкам"></section>
      </div></div>
      <svg class="ms-clock-wire" aria-hidden="true">
        <path class="ms-clock-line" fill="none"/><path class="ms-clock-arrow" fill="none"/>
      </svg>
      <div class="controls ms-clock-controls">
        <button class="tick" type="button" aria-describedby="${helpId}">Такт</button>
        <button class="restart" type="button">Сначала</button>
        <span class="ms-clock-count">Тактов подано: 0</span>
      </div>
    </div>
    <p class="cs-help" id="${helpId}">Каждый такт поступает в обе колонки. Удерживайте «Такт» или Enter для непрерывного выполнения.</p>`;
  const stage = element.querySelector(".cs-dual-stage");
  const tick = element.querySelector(".tick");
  const wire = element.querySelector(".ms-clock-wire");
  let holdTimer, pulseTimer, clocks = 0;
  const lanes = [...element.querySelectorAll(".cs-lane")].map(node =>
    createLane(node, node.dataset.order, size, values, cacheEnabled, () => {
      if (lanes.every(lane => lane.finished())) {
        tick.disabled = true;
        stopHolding();
      }
    })
  );

  function layoutWire() {
    const origin = stage.getBoundingClientRect(), from = tick.getBoundingClientRect();
    const x1 = from.left + from.width / 2 - origin.left, y1 = from.top - origin.top;
    const paths = [], arrows = [];
    for (const target of element.querySelectorAll(".ms-execution")) {
      const to = target.getBoundingClientRect();
      const x2 = to.left + to.width / 2 - origin.left, y2 = to.bottom - origin.top;
      paths.push(`M ${x1} ${y1} V ${y1 - 20} H ${x2} V ${y2 + 2}`);
      arrows.push(`M ${x2 - 4} ${y2 + 8} L ${x2} ${y2 + 2} L ${x2 + 4} ${y2 + 8}`);
    }
    wire.setAttribute("viewBox", `0 0 ${origin.width} ${origin.height}`);
    wire.querySelector(".ms-clock-line").setAttribute("d", paths.join(" "));
    wire.querySelector(".ms-clock-arrow").setAttribute("d", arrows.join(" "));
  }
  new ResizeObserver(layoutWire).observe(stage);
  element.querySelector(".cs-dual-scroll").addEventListener("scroll", layoutWire, { passive: true });

  function issueClock() {
    if (tick.disabled) return;
    clocks++;
    element.querySelector(".ms-clock-count").textContent = `Тактов подано: ${clocks}`;
    clearTimeout(pulseTimer);
    wire.classList.add("is-pulsing");
    pulseTimer = setTimeout(() => wire.classList.remove("is-pulsing"), 25);
    for (const lane of lanes) lane.press();
  }
  function stopHolding() {
    clearInterval(holdTimer);
    holdTimer = undefined;
    tick.classList.remove("is-held");
  }
  function beginHolding() {
    if (holdTimer !== undefined || tick.disabled) return;
    holdTimer = setInterval(issueClock, clockMs);
    tick.classList.add("is-held");
    issueClock();
  }
  function reset() {
    stopHolding();
    clearTimeout(pulseTimer);
    clocks = 0;
    tick.disabled = false;
    wire.classList.remove("is-pulsing");
    element.querySelector(".ms-clock-count").textContent = "Тактов подано: 0";
    for (const lane of lanes) lane.reset();
  }
  tick.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    event.preventDefault();
    tick.focus({ preventScroll: true });
    tick.setPointerCapture(event.pointerId);
    beginHolding();
  });
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) tick.addEventListener(name, stopHolding);
  tick.addEventListener("click", event => { if (event.detail === 0) issueClock(); });
  for (const control of [tick, stage]) {
    control.addEventListener("keydown", event => {
      if (control === stage && event.target !== stage) return;
      if (event.key !== "Enter" && !(control === tick && event.key === " ")) return;
      event.preventDefault();
      if (!event.repeat) beginHolding();
    });
    control.addEventListener("keyup", event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); stopHolding(); }
    });
    control.addEventListener("blur", stopHolding);
  }
  element.querySelector(".restart").addEventListener("click", () => { reset(); stage.focus({ preventScroll: true }); });
  window.addEventListener("blur", stopHolding);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopHolding(); });
  reset();
}

function createLane(element, order, size, values, cacheEnabled, onComplete) {
  element.innerHTML = `
    <div class="cs-lane-title">${order === "cols" ? "По столбцам" : "По строкам"}${cacheEnabled ? (order === "cols" ? " · медленный" : " · быстрый") : ""}</div>
    <div class="cs-lane-stats">${cacheEnabled
      ? '<span>Попадания <strong class="cs-hits">0</strong></span><span>Промахи <strong class="cs-misses">0</strong></span>'
      : '<span>Чтения <strong class="cs-reads">0</strong></span><span>Сложения <strong class="cs-adds">0</strong></span>'}</div>
    <div class="cs-progress"><span>Просуммировано <strong>0 / ${values.length}</strong></span><progress max="${values.length}" value="0"></progress></div>
    <p class="cs-note" role="status">Ожидание</p>
    <div class="memory-sum-stage cache-stage">
      <section class="ms-memory">
        <div class="ms-label">RAM · память</div>
        <div class="cs-memory-grid" style="--matrix-size:${size}">${values.map((v, i) =>
          `<span class="cs-memory-cell" data-index="${i}" title="a[${Math.floor(i / size)}][${i % size}]">${v}</span>`).join("")}</div>
      </section>
      <div class="ms-path" aria-hidden="true">${cacheEnabled ? "↓ кэш-линия · 64 байта" : "↓ элемент"}</div>
      <section class="ms-cpu">
        <div class="ms-label ms-cpu-label">CPU · процессор</div>
        ${cacheEnabled ? `<section class="cs-cache">
          <div class="ms-label">Кэш · одна линия</div>
          <div class="cs-cache-grid">${Array.from({ length: LINE }, () => '<span class="cs-cache-cell">—</span>').join("")}</div>
          <div class="cs-cache-status">Кэш пуст</div>
        </section>
        <div class="ms-path" aria-hidden="true">↓ элемент</div>` : ""}
        <section class="ms-register-bank">
          <div class="ms-label">Регистры</div>
          <div class="ms-registers">
            <div class="ms-register cs-value-register"><span class="ms-address">Элемент</span><strong class="cs-value">—</strong></div>
            <div class="ms-register cs-sum-register"><span class="ms-address">Сумма</span><strong class="cs-sum">0</strong></div>
          </div>
        </section>
        <div class="ms-path" aria-hidden="true">↓ операнды · ↑ результат</div>
        <section class="ms-execution">
          <div class="ms-label">Выполнение</div>
          <code class="ms-operation">Ожидание</code>
          ${cacheEnabled ? "" : '<div class="cs-wait-state">Готов к чтению</div><div class="cs-wait-count">Такты ожидания: <strong>0</strong></div>'}
        </section>
      </section>
      <span class="ms-flying-number cs-packet" aria-hidden="true" hidden></span>
    </div>`;
  const stage = element.querySelector(".cache-stage");
  const packet = element.querySelector(".cs-packet");
  const memoryCells = [...element.querySelectorAll(".cs-memory-cell")];
  const cacheCells = [...element.querySelectorAll(".cs-cache-cell")];
  const cacheGrid = element.querySelector(".cs-cache-grid");
  const cacheStatus = element.querySelector(".cs-cache-status");
  const valueNode = element.querySelector(".cs-value");
  const sumNode = element.querySelector(".cs-sum");
  const operation = element.querySelector(".ms-operation");
  const note = element.querySelector(".cs-note");
  const execution = element.querySelector(".ms-execution");
  const waitState = element.querySelector(".cs-wait-state");
  const waitCount = element.querySelector(".cs-wait-count strong");
  let state, animation, flightTimer, waitPulseTimer;

  function drawStats() {
    element.querySelector(".cs-progress strong").textContent = `${state.done} / ${values.length}`;
    element.querySelector("progress").value = state.done;
    if (cacheEnabled) {
      element.querySelector(".cs-hits").textContent = state.hits;
      element.querySelector(".cs-misses").textContent = state.misses;
    } else {
      element.querySelector(".cs-reads").textContent = state.reads;
      element.querySelector(".cs-adds").textContent = state.done;
    }
  }
  function fly(from, to, content, duration, arrived, isLine = false) {
    state.busy = true;
    packet.replaceChildren();
    packet.classList.toggle("is-line", isLine);
    if (isLine) {
      for (const v of content) {
        const cell = document.createElement("span");
        cell.textContent = v;
        packet.append(cell);
      }
    } else packet.textContent = content;
    const finish = () => {
      packet.hidden = true;
      state.busy = false;
      arrived();
    };
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      flightTimer = setTimeout(finish, duration);
      return;
    }
    const origin = stage.getBoundingClientRect(), start = from.getBoundingClientRect(), end = to.getBoundingClientRect();
    const x = start.left + start.width / 2, y = start.top + start.height / 2;
    packet.style.left = `${x - origin.left}px`;
    packet.style.top = `${y - origin.top}px`;
    packet.hidden = false;
    animation = packet.animate([
      { transform: "translate(-50%, -50%)" },
      { transform: `translate(calc(-50% + ${end.left + end.width / 2 - x}px), calc(-50% + ${end.top + end.height / 2 - y}px))` },
    ], { duration, easing: "ease-in-out" });
    animation.onfinish = finish;
  }

  function target() {
    return order === "rows" ? state.done : (state.done % size) * size + Math.floor(state.done / size);
  }

  function loadRegister(index) {
    const slot = index % LINE;
    cacheCells.forEach((cell, i) => cell.classList.toggle("is-current", i === slot));
    fly(cacheCells[slot], valueNode, values[index], 35, () => {
      state.value = values[index];
      valueNode.textContent = state.value;
      state.phase = "add";
      note.textContent = "Элемент загружен. Следующий шаг — сложение.";
    });
  }

  function advance() {
    if (state.busy || state.done === values.length) return;
    element.querySelector(".ms-execution").classList.add("is-current");
    element.querySelector(".cs-value-register").classList.toggle("is-current", state.phase === "load");
    element.querySelector(".cs-sum-register").classList.toggle("is-current", state.phase === "add");
    const index = target();
    if (state.phase === "load") {
      const block = Math.floor(index / LINE);
      operation.textContent = `value = a[${Math.floor(index / size)} * ${size} + ${index % size}];`;
      memoryCells.forEach(cell => cell.classList.remove("is-fetching"));
      if (!cacheEnabled) {
        memoryCells.forEach((cell, i) => cell.classList.toggle("is-current", i === index));
        state.fetching = true;
        execution.classList.add("is-waiting-memory");
        waitState.textContent = "Ожидаем RAM · сложение недоступно";
        note.textContent = "Память загружает элемент. Новые такты не меняют сумму.";
        fly(memoryCells[index], valueNode, values[index], 650, () => {
          state.fetching = false;
          execution.classList.remove("is-waiting-memory");
          waitState.textContent = "Данные готовы · можно складывать";
          state.value = values[index];
          state.reads++;
          valueNode.textContent = state.value;
          state.phase = "add";
          note.textContent = "Элемент загружен. Следующий шаг — сложение.";
          drawStats();
        });
      } else if (state.cached === block) {
        state.hits++;
        cacheStatus.textContent = "Попадание · элемент уже в кэше";
        note.textContent = "Загружаем элемент из кэша в регистр.";
        loadRegister(index);
      } else {
        state.misses++;
        state.fetching = true;
        cacheStatus.textContent = "Промах · ожидаем линию из RAM";
        note.textContent = "CPU ждёт данные из памяти.";
        const start = block * LINE;
        const line = values.slice(start, start + LINE);
        memoryCells.forEach((cell, i) => cell.classList.toggle("is-fetching", i >= start && i < start + LINE));
        const first = memoryCells[start], last = memoryCells[Math.min(start + LINE - 1, values.length - 1)];
        const source = { getBoundingClientRect() {
          const a = first.getBoundingClientRect(), b = last.getBoundingClientRect();
          return { left: Math.min(a.left, b.left), top: a.top, width: Math.max(a.right, b.right) - Math.min(a.left, b.left), height: b.bottom - a.top };
        }};
        fly(source, cacheGrid, line, FETCH_MS, () => {
          state.cached = block;
          state.fetching = false;
          cacheCells.forEach((cell, i) => { cell.textContent = line[i] ?? "—"; });
          memoryCells.forEach((cell, i) => {
            cell.classList.remove("is-fetching");
            cell.classList.toggle("in-cache", Math.floor(i / LINE) === block);
          });
          cacheStatus.textContent = "Линия загружена · 16 чисел";
          loadRegister(index);
        }, true);
      }
      drawStats();
    } else {
      operation.textContent = "total += value;";
      note.textContent = "Прибавляем элемент к сумме.";
      if (waitState) waitState.textContent = "Сложение · один такт";
      fly(valueNode, operation, state.value, cacheEnabled ? 15 : 5, () => {
        fly(operation, sumNode, state.sum + state.value, cacheEnabled ? 15 : 5, () => {
          state.sum += state.value;
          state.done++;
          state.phase = "load";
          sumNode.textContent = state.sum;
          memoryCells[index].classList.add("is-visited");
          drawStats();
          if (state.done === values.length) {
            element.classList.add("is-complete");
            note.textContent = "Готово";
            if (waitState) waitState.textContent = "Выполнение завершено";
            onComplete();
          }
        });
      });
    }
  }

  function reset() {
    clearTimeout(flightTimer);
    clearTimeout(waitPulseTimer);
    execution.classList.remove("is-waiting-memory", "is-wait-tick");
    if (waitState) waitState.textContent = "Готов к чтению";
    if (waitCount) waitCount.textContent = "0";
    if (animation) { animation.onfinish = null; animation.cancel(); }
    state = { done: 0, sum: 0, value: null, cached: null, phase: "load", busy: false, fetching: false, hits: 0, misses: 0, reads: 0, waitingClocks: 0 };
    packet.hidden = true;
    element.classList.remove("is-complete");
    sumNode.textContent = "0";
    valueNode.textContent = "—";
    operation.textContent = "Ожидание";
    if (cacheStatus) cacheStatus.textContent = "Кэш пуст";
    note.textContent = "Ожидание";
    memoryCells.forEach(cell => { cell.className = "cs-memory-cell"; });
    cacheCells.forEach(cell => { cell.className = "cs-cache-cell"; cell.textContent = "—"; });
    element.querySelectorAll(".ms-register, .ms-execution").forEach(node => node.classList.remove("is-current"));
    drawStats();
  }
  return {
    reset,
    finished: () => state.done === values.length,
    press() {
      if (state.fetching && !cacheEnabled) {
        state.waitingClocks++;
        waitCount.textContent = state.waitingClocks;
        execution.classList.add("is-wait-tick");
        clearTimeout(waitPulseTimer);
        waitPulseTimer = setTimeout(() => execution.classList.remove("is-wait-tick"), 12);
        return;
      }
      if (state.fetching) note.textContent = "CPU ждёт линию из RAM.";
      advance();
    },
  };
}
