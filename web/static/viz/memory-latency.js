// Illustrative latency values, not measurements of the visitor's machine.
const levels = [
  ["Регистры", "Операция ADD над регистрами", 0.3, "≈ 0,3 нс"],
  ["L1 · данные", "48 КиБ на ядро", 1.5, "≈ 1,5 нс"],
  ["L2", "2 МиБ на ядро", 5, "≈ 5 нс"],
  ["L3", "105 МиБ на процессор", 33, "≈ 33 нс"],
  ["Оперативная память", "DDR5-4800 · объём зависит от сервера", 107, "≈ 107 нс"],
];

export function mount(element) {
  element.classList.add("memory-latency");
  element.innerHTML = `<figure aria-label="Задержка доступа: от оперативной памяти до регистров">
    <figcaption>Задержка, нс · меньше — быстрее</figcaption>
    <div class="ml-axis" aria-hidden="true"><span>0</span><span>30</span><span>60</span><span>90</span><span>120</span></div>
    ${[...levels].reverse().map(([name, size, latency, label]) => `<div class="ml-row">
      <div class="ml-label"><strong>${name}</strong><span>${size}</span></div>
      <div class="ml-track" aria-hidden="true"><span style="width:${latency / 120 * 100}%"></span></div>
      <div class="ml-value">${label}</div>
    </div>`).join("")}
  </figure>`;
}
