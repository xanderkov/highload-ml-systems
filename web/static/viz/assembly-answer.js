// Fixed, small integer exercises; no overflow or general-purpose emulation.
const EXERCISES = [
  {
    title: "Арифметика и память",
    code: ["ADD RAX, RBX", "SUB RAX, [RCX]", "ADD RBX, 2", "SUB RAX, RBX"],
    initial: [["RAX", "10"], ["RBX", "3"], ["RCX", "0x1000"], ["Память [RCX]", "7"]],
    note: "По адресу 0x1000 хранится 64-битное целое число.",
    answer: 1,
    hint: "Проверьте порядок вычитания и учтите изменение RBX в третьей строке.",
    trace: ["RAX: 10 + 3 = 13", "RAX: 13 − 7 = 6", "RBX: 3 + 2 = 5", "RAX: 6 − 5 = 1"],
  },
  {
    title: "Цикл со счётчиком",
    code: ["loop:", "ADD RAX, RCX", "INC RCX", "CMP RCX, 4", "JL loop"],
    initial: [["RAX", "0"], ["RCX", "1"]],
    note: "JL возвращает выполнение к loop, если после CMP значение RCX меньше 4.",
    answer: 6,
    hint: "Сложение выполняется до увеличения RCX. Проверьте, при каком значении счётчика прекращается переход.",
    trace: ["RCX = 1: RAX = 0 + 1 = 1", "RCX = 2: RAX = 1 + 2 = 3", "RCX = 3: RAX = 3 + 3 = 6", "RCX = 4: переход не выполняется"],
  },
  {
    title: "Изменение шага в цикле",
    code: ["loop:", "SUB RAX, RBX", "ADD RBX, 2", "INC RCX", "CMP RCX, 3", "JL loop"],
    initial: [["RAX", "20"], ["RBX", "2"], ["RCX", "0"]],
    note: "RBX меняется на каждом проходе. RCX считает выполненные проходы.",
    answer: 8,
    hint: "На каждом проходе из RAX вычитается текущее значение RBX, после чего RBX увеличивается на 2.",
    trace: ["Проход 1: RAX = 20 − 2 = 18; RBX = 4", "Проход 2: RAX = 18 − 4 = 14; RBX = 6", "Проход 3: RAX = 14 − 6 = 8; RBX = 8", "RCX = 3: переход не выполняется"],
  },
];

export function mount(element, { blockId = "assembly-answer" } = {}) {
  element.classList.add("assembly-answer");
  const states = EXERCISES.map(() => ({ value: "", solved: false, feedback: "", invalid: false }));
  const labels = ["Задание 1", "Задание 2", "Задание 3"];
  let active = 0;
  element.innerHTML = `
    <div class="asm-tabs" role="tablist" aria-label="Задания на ассемблер">
      ${labels.map((label, i) => `<button type="button" role="tab" id="${blockId}-tab-${i}" aria-controls="${blockId}-panel" data-index="${i}">${label}</button>`).join("")}
    </div>
    <div id="${blockId}-panel" role="tabpanel">
      <div class="block-head"><span class="asm-title"></span><span>Вычислите RAX</span></div>
      <div class="asm-question">
        <pre class="asm-program" aria-label="Код на ассемблере"><code></code></pre>
        <div class="asm-initial">
          <span class="guide-label">Начальные значения</span>
          <dl></dl><p></p>
        </div>
      </div>
      <form class="controls asm-answer-form" novalidate>
        <label>RAX после выполнения <input class="asm-answer-input" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" aria-describedby="${blockId}-feedback"></label>
        <button type="submit">Проверить</button>
      </form>
      <div id="${blockId}-feedback" class="asm-feedback" role="status" aria-live="polite"></div>
    </div>`;
  const tabs = [...element.querySelectorAll('[role="tab"]')];
  const input = element.querySelector("input");
  const feedback = element.querySelector(".asm-feedback");

  function updateTabs() {
    tabs.forEach((tab, i) => {
      tab.textContent = labels[i] + (states[i].solved ? " ✓" : "");
      tab.setAttribute("aria-label", labels[i] + (states[i].solved ? ", решено" : ""));
      tab.setAttribute("aria-selected", String(i === active));
      tab.tabIndex = i === active ? 0 : -1;
    });
  }

  function showFeedback() {
    const state = states[active], exercise = EXERCISES[active];
    feedback.replaceChildren();
    input.toggleAttribute("aria-invalid", state.invalid);
    if (state.invalid) input.setAttribute("aria-invalid", "true");
    if (state.feedback === "correct") {
      const message = document.createElement("p");
      message.textContent = `Верно. RAX = ${exercise.answer}.`;
      const list = document.createElement("ol");
      for (const line of exercise.trace) {
        const item = document.createElement("li");
        item.textContent = line;
        list.append(item);
      }
      feedback.append(message, list);
    } else feedback.textContent = state.feedback;
  }

  function render() {
    const exercise = EXERCISES[active];
    updateTabs();
    element.querySelector('[role="tabpanel"]').setAttribute("aria-labelledby", tabs[active].id);
    element.querySelector(".asm-title").textContent = exercise.title;
    const code = element.querySelector(".asm-program code");
    code.replaceChildren();
    exercise.code.forEach((line, i) => {
      const row = document.createElement("span");
      row.className = "asm-code-line";
      const number = document.createElement("span");
      number.className = "asm-line-number";
      number.setAttribute("aria-hidden", "true");
      number.textContent = i + 1;
      const opcode = document.createElement("span");
      opcode.className = line.endsWith(":") ? "asm-label" : "asm-op";
      const [op, ...args] = line.split(" ");
      opcode.textContent = op;
      row.append(number, opcode, document.createTextNode(args.length ? " " + args.join(" ") : ""));
      code.append(row, document.createTextNode("\n"));
    });
    const initial = element.querySelector(".asm-initial dl");
    initial.replaceChildren();
    for (const [name, value] of exercise.initial) {
      const dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = name; dd.textContent = value;
      initial.append(dt, dd);
    }
    element.querySelector(".asm-initial p").textContent = exercise.note;
    input.value = states[active].value;
    showFeedback();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => { active = index; render(); });
    tab.addEventListener("keydown", event => {
      let target;
      if (event.key === "ArrowRight") target = (active + 1) % tabs.length;
      if (event.key === "ArrowLeft") target = (active + tabs.length - 1) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      if (target === undefined) return;
      event.preventDefault();
      active = target; render(); tabs[target].focus();
    });
  });
  element.querySelector("form").addEventListener("submit", event => {
    event.preventDefault();
    const state = states[active], exercise = EXERCISES[active];
    const raw = input.value.trim(), answer = Number(raw);
    state.invalid = !/^[+-]?\d+$/.test(raw) || !Number.isSafeInteger(answer);
    if (state.invalid) state.feedback = "Введите целое число.";
    else if (answer !== exercise.answer) state.feedback = "Ответ не совпадает. " + exercise.hint;
    else { state.solved = true; state.feedback = "correct"; }
    updateTabs();
    showFeedback();
  });
  input.addEventListener("input", () => {
    Object.assign(states[active], { value: input.value, feedback: "", invalid: false });
    showFeedback();
  });
  render();
}
