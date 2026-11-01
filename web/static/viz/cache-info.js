import { escapeHtml as esc } from "../result.js";

export async function mount(element) {
  element.classList.add("hardware-info");
  element.textContent = "Определяем процессор…";
  try {
    const response = await fetch("/api/cache-info");
    if (!response.ok) throw new Error();
    const data = await response.json();
    const arch = { arm64: "ARM64", aarch64: "ARM64", x86_64: "x86-64", amd64: "x86-64" }[data.architecture] || data.architecture;
    const groups = [...new Set(data.entries.map(e => e.group))];
    element.innerHTML = `<div class="block-head">Процессор, на котором выполняются замеры</div>
      <div class="hardware-details"><p><strong>${esc(data.model || "Модель не определена")}</strong> · ${esc(arch || "Архитектура не определена")}</p>
      ${groups.map(group => `<p>${esc(group)}: ${data.entries.filter(e => e.group === group).map(e => `L${e.level}${e.level === 1 ? "D" : ""} — ${e.bytes >= 1048576 ? e.bytes / 1048576 + " МиБ" : e.bytes / 1024 + " КиБ"}`).join(" · ")}</p>`).join("")}
      ${!data.entries.length ? "<p>Система не сообщила размеры кэшей.</p>" : !data.entries.some(e => e.level === 3) ? "<p class=hint>Размер L3 не сообщён системой.</p>" : ""}
      <p><a href="https://hw-museum.cz/cpu/cpu-interactive-table" target="_blank" rel="noopener noreferrer">Таблица процессоров и размеров кэша L1, L2, L3 ↗</a></p></div>`;
  } catch {
    element.textContent = "Не удалось получить сведения о процессоре. Обновите страницу, чтобы повторить запрос.";
  }
}
