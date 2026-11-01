import { run } from "../api.js";
import { escapeHtml as esc, formatMs, formatSpeedup, renderProblem } from "../result.js";

export function mount(element, { sectionId, blockId, params }) {
  element.classList.add("exercise", "sparse-experiment");
  element.innerHTML = `<div class="block-head">${esc(params.title)}</div><div class="editor"></div>
    <div class="controls"><button type="button">Замерить</button></div>
    <div class="result" aria-live="polite"></div><div class="experiment-history"></div>`;
  const editor = ace.edit(element.querySelector(".editor"), {
    mode: "ace/mode/c_cpp", theme: "ace/theme/github_dark", value: params.starter_code,
    minLines: 12, maxLines: 40, fontSize: 13, showPrintMargin: false, tabSize: 4,
  });
  const button = element.querySelector("button");
  const result = element.querySelector(".result");
  const history = element.querySelector(".experiment-history");
  const runs = [];
  function showStatus(message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    result.replaceChildren(paragraph);
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    editor.setReadOnly(true);
    showStatus("Замеряем…");
    try {
      const data = await run(sectionId, blockId, editor.getValue());
      const problem = renderProblem(data);
      if (problem) { result.innerHTML = problem; return; }
      showStatus(data.correct ? "Результат совпадает с ожидаемым: 4 194 304." : "Результат не совпадает с ожидаемым.");
      if (!data.correct) return;
      runs.push(data);
      const best = Math.max(...runs.map(r => r.slowdown || 0));
      history.innerHTML = `<table class="numbers"><thead><tr><th scope="col">GAP_BYTES</th><th scope="col">Без промежутков</th><th scope="col">Ваш вариант</th><th scope="col">Замедление</th></tr></thead><tbody>${runs.map(r => `<tr><td>${esc(r.gap_bytes ?? "—")}</td><td>${formatMs(r.baseline_ms)}</td><td>${formatMs(r.student_ms)}</td><td>${formatSpeedup(r.slowdown)}${r.slowdown === best ? '<span class="experiment-best">максимум</span>' : ""}</td></tr>`).join("")}</tbody></table>`;
    } catch (error) {
      showStatus(error.message || String(error));
    } finally {
      editor.setReadOnly(false);
      button.disabled = false;
    }
  });
}
