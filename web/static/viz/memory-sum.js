// Small instruction-by-instruction loop; memory latency is animated.
const VALUES = [7, 2, 5, 6];
const REPEAT_MS = 240;
const MEMORY_MS = 600;
const ADD_LEG_MS = 90;

export function mount(element) {
  element.classList.add("viz", "memory-sum");
  element.innerHTML = `
    <div class="block-head"><span>Память → регистр → сложение</span><span class="status"></span></div>
    <div class="memory-sum-stage" tabindex="0" aria-label="Суммирование матрицы" aria-describedby="memory-sum-help">
      <section class="ms-memory" aria-label="Оперативная память">
        <div class="ms-label">RAM · память · матрица 2 × 2</div>
        <div class="ms-matrix">${VALUES.map((value, index) => `<div class="ms-cell"><span class="ms-address">0x${(0x1000 + index * 4).toString(16)}</span><strong>${value}</strong></div>`).join("")}</div>
      </section>
      <div class="ms-path" aria-hidden="true">↓ загрузка в регистр</div>
      <section class="ms-cpu" aria-label="CPU — процессор">
      <div class="ms-label ms-cpu-label">CPU · процессор</div>
      <section class="ms-register-bank" aria-label="Регистры процессора">
        <div class="ms-label">Регистры процессора</div>
        <div class="ms-registers">
          <div class="ms-register ms-value-register"><span class="ms-address">EBX · элемент</span><strong class="ms-value">—</strong></div>
          <div class="ms-register ms-sum-register"><span class="ms-address">EAX · сумма</span><strong class="ms-sum">0</strong></div>
          <div class="ms-register ms-counter-register"><span class="ms-address">RCX · счётчик</span><strong class="ms-counter">0</strong></div>
          <div class="ms-register ms-limit-register"><span class="ms-address">RDX · количество</span><strong>4</strong></div>
        </div>
      </section>
      <div class="ms-path" aria-hidden="true">↓ операнды · ↑ результат</div>
      <section class="ms-execution" aria-label="Выполнение инструкции">
        <div class="ms-label">Выполнение</div>
        <div class="ms-loop-label">loop:</div>
        <div class="ms-program">
          <code class="ms-operation" data-pc="0">MOV EBX, [0x1000 + RCX*4]</code>
          <code class="ms-operation" data-pc="1">ADD EAX, EBX</code>
          <code class="ms-operation" data-pc="2">INC RCX</code>
          <code class="ms-operation" data-pc="3">CMP RCX, RDX</code>
          <code class="ms-operation" data-pc="4">JL loop</code>
        </div>
      </section>
      </section>
      <svg class="ms-clock-wire" aria-hidden="true"><path class="ms-clock-line" fill="none"/><path class="ms-clock-arrow" fill="none"/></svg>
      <div class="controls ms-clock-controls">
        <button class="tick" type="button" aria-describedby="memory-sum-help">Такт</button>
        <button class="restart" type="button">Сначала</button>
        <span class="ms-clock-count">Тактов: 0</span>
      </div>
      <span class="ms-flying-number" aria-hidden="true" hidden></span>
    </div>
    <p class="ms-help" id="memory-sum-help">Нажмите «Такт» или Enter. Удерживайте кнопку или клавишу для непрерывной подачи тактов.</p>
    <p class="ms-step" aria-live="polite"></p>`;

  const stage = element.querySelector(".memory-sum-stage");
  const tick = element.querySelector(".tick");
  const cells = [...element.querySelectorAll(".ms-cell")];
  const packet = element.querySelector(".ms-flying-number");
  const valueNode = element.querySelector(".ms-value");
  const sumNode = element.querySelector(".ms-sum");
  const instructions = [...element.querySelectorAll(".ms-operation")];
  const counterNode = element.querySelector(".ms-counter");
  const note = element.querySelector(".ms-step");
  let next = 0, sum = 0, value = null;
  let pc = 0, busy = false, less = false;
  let animation, repeatTimer, pulseTimer;
  let clocks = 0;
  const wire = element.querySelector(".ms-clock-wire");

  function layoutWire() {
    const origin = stage.getBoundingClientRect();
    const button = tick.getBoundingClientRect();
    const execution = element.querySelector(".ms-execution").getBoundingClientRect();
    const x1 = button.left + button.width / 2 - origin.left;
    const y1 = button.top - origin.top;
    const x2 = execution.left + execution.width / 2 - origin.left;
    const y2 = execution.bottom - origin.top;
    const bend = y1 - 22;
    wire.setAttribute("viewBox", `0 0 ${origin.width} ${origin.height}`);
    wire.querySelector(".ms-clock-line").setAttribute("d", `M ${x1} ${y1} V ${bend} H ${x2} V ${y2 + 2}`);
    wire.querySelector(".ms-clock-arrow").setAttribute("d", `M ${x2 - 4} ${y2 + 8} L ${x2} ${y2 + 2} L ${x2 + 4} ${y2 + 8}`);
  }
  new ResizeObserver(layoutWire).observe(stage);

  function issueClock() {
    if (tick.disabled) return;
    clocks += 1;
    element.querySelector(".ms-clock-count").textContent = `Тактов: ${clocks}`;
    clearTimeout(pulseTimer);
    wire.classList.add("is-pulsing");
    pulseTimer = setTimeout(() => wire.classList.remove("is-pulsing"), 120);
    if (busy && pc === 0) note.textContent = "CPU ждёт данные из RAM. Такты поступают, сложение ещё не выполняется.";
    advance();
  }

  function stopHolding() {
    clearInterval(repeatTimer);
    repeatTimer = undefined;
    tick.classList.remove("is-held");
  }

  function highlight(operation) {
    cells.forEach((cell, i) => {
      cell.classList.toggle("is-current", operation === "load" && i === next);
      cell.classList.toggle("is-added", i < next);
    });
    for (const [selector, active] of [
      [".ms-execution", operation !== null],
      [".ms-value-register", operation === "load"], [".ms-sum-register", operation === "add"],
      [".ms-counter-register", operation === "increment" || operation === "compare"],
    ]) element.querySelector(selector).classList.toggle("is-current", active);
  }

  function fly(from, to, number, arrived, duration = MEMORY_MS) {
    busy = true;
    const finish = () => {
      packet.hidden = true;
      busy = false;
      arrived();
    };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      finish();
      return;
    }
    const origin = stage.getBoundingClientRect();
    const start = from.getBoundingClientRect();
    const end = to.getBoundingClientRect();
    const x = start.left + start.width / 2, y = start.top + start.height / 2;
    packet.textContent = number;
    packet.hidden = false;
    packet.style.left = `${x - origin.left}px`;
    packet.style.top = `${y - origin.top}px`;
    animation = packet.animate([
      { transform: "translate(-50%, -50%)" },
      { transform: `translate(calc(-50% + ${end.left + end.width / 2 - x}px), calc(-50% + ${end.top + end.height / 2 - y}px))` },
    ], { duration, easing: "ease-in-out" });
    animation.onfinish = finish;
  }

  function advance() {
    if (busy || tick.disabled) return;
    instructions.forEach((line, index) => {
      line.classList.toggle("is-current", index === pc);
      if (index === pc) line.setAttribute("aria-current", "step");
      else line.removeAttribute("aria-current");
    });
    if (pc === 0) {
      value = VALUES[next];
      highlight("load");
      note.textContent = `MOV: загружаем число по адресу 0x${(0x1000 + next * 4).toString(16)} в EBX.`;
      fly(cells[next].querySelector("strong"), valueNode, value, () => {
        valueNode.textContent = value;
        pc = 1;
        note.textContent = "Число загружено в EBX.";
      });
    } else if (pc === 1) {
      highlight("add");
      note.textContent = "ADD: прибавляем EBX к сумме в EAX.";
      fly(valueNode, instructions[1], value, () => {
        fly(instructions[1], sumNode, sum + value, () => {
          sum += value;
          sumNode.textContent = sum;
          pc = 2;
          element.querySelector(".status").textContent = `${next + 1} / ${VALUES.length} элементов`;
        }, ADD_LEG_MS);
      }, ADD_LEG_MS);
    } else if (pc === 2) {
      next += 1;
      counterNode.textContent = next;
      highlight("increment");
      note.textContent = "INC: увеличиваем счётчик RCX на единицу.";
      pc = 3;
    } else if (pc === 3) {
      highlight("compare");
      less = next < VALUES.length;
      note.textContent = `CMP: сравниваем счётчик RCX (${next}) с количеством элементов в RDX (4).`;
      pc = 4;
    } else {
      highlight("jump");
      if (!less) {
        note.textContent = "JL: счётчик достиг 4, переход не выполняется. Цикл завершён.";
        stopHolding();
        tick.disabled = true;
      } else {
        note.textContent = "JL: счётчик меньше 4. Возвращаемся к loop — загрузке следующего числа.";
        pc = 0;
      }
    }
  }

  function beginHolding() {
    if (repeatTimer !== undefined || tick.disabled) return;
    tick.classList.add("is-held");
    repeatTimer = setInterval(issueClock, REPEAT_MS);
    issueClock();
  }

  function reset() {
    stopHolding();
    clearTimeout(pulseTimer);
    wire.classList.remove("is-pulsing");
    clocks = 0;
    element.querySelector(".ms-clock-count").textContent = "Тактов: 0";
    if (animation) { animation.onfinish = null; animation.cancel(); }
    packet.hidden = true;
    busy = false;
    next = 0; sum = 0; value = null; pc = 0; less = false;
    tick.disabled = false;
    valueNode.textContent = "—";
    sumNode.textContent = "0";
    counterNode.textContent = "0";
    instructions.forEach(line => {
      line.classList.remove("is-current");
      line.removeAttribute("aria-current");
    });
    element.querySelector(".status").textContent = "0 / 4 элементов";
    note.textContent = "Первый шаг: число 7 из памяти попадёт в EBX.";
    highlight(null);
  }

  tick.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    tick.focus({ preventScroll: true });
    tick.setPointerCapture(event.pointerId);
    beginHolding();
  });
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) tick.addEventListener(name, stopHolding);
  // Keyboard/assistive clicks have detail=0. Pointer clicks already ran on down.
  tick.addEventListener("click", (event) => { if (event.detail === 0) issueClock(); });
  for (const control of [tick, stage]) {
    control.addEventListener("keydown", (event) => {
      if (control === stage && event.target !== stage) return;
      if (event.key !== "Enter" && !(control === tick && event.key === " ")) return;
      event.preventDefault();
      if (!event.repeat) beginHolding();
    });
    control.addEventListener("keyup", (event) => {
      if (control === stage && event.target !== stage) return;
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); stopHolding(); }
    });
    control.addEventListener("blur", stopHolding);
  }
  window.addEventListener("blur", stopHolding);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopHolding(); });
  element.querySelector(".restart").addEventListener("click", () => { reset(); stage.focus({ preventScroll: true }); });
  reset();
}
