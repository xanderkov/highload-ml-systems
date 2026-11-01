import { run } from "../api.js";
import { escapeHtml as esc, formatMs, renderProblem } from "../result.js";

export function mount(element, { sectionId, blockId, params }) {
  element.classList.add("code-comparison");
  element.classList.toggle("comparison-stacked", params.layout === "stacked");
  element.style.setProperty("--comparison-count", params.variant_codes.length);
  element.innerHTML = `<div class="block-head">${esc(params.title)}</div><div class="comparison-columns">
    ${params.variant_codes.map((_, index) => `<section class="comparison-column" data-variant="${index}">
      <div class="comparison-title">${esc(params.labels[index])}</div>
      <div class="controls"><button class="run" type="button">Замерить</button><button class="reset" type="button">Вернуть исходный код</button></div>
      <div class="editor"></div><div class="result" aria-live="polite"></div>
    </section>`).join("")}</div>`;
  const columns = [...element.querySelectorAll(".comparison-column")];
  columns.forEach((column, index) => {
    const editor = ace.edit(column.querySelector(".editor"), {
      mode: params.variant_sources?.[index]?.endsWith(".py") ? "ace/mode/python" : "ace/mode/c_cpp", theme: "ace/theme/github_dark", value: params.variant_codes[index],
      minLines: 12, maxLines: 40, fontSize: 12, showPrintMargin: false, tabSize: 4, wrap: true,
    });
    const result = column.querySelector(".result");
    const reset = column.querySelector(".reset");
    editor.session.on("change", () => { result.replaceChildren(); });
    reset.addEventListener("click", () => { editor.setValue(params.variant_codes[index], -1); });
    column.querySelector(".run").addEventListener("click", async () => {
      element.querySelectorAll(".run").forEach(b => { b.disabled = true; });
      editor.setReadOnly(true); reset.disabled = true;
      result.innerHTML = "<p>Замеряем…</p>";
      try {
        const data = await run(sectionId, blockId, editor.getValue(), index);
        const problem = renderProblem(data);
        result.innerHTML = problem || `<p><strong>${formatMs(data.variant_ms?.[index] ?? (index === 0 ? data.baseline_ms : data.student_ms))}</strong><br>${data.correct ? "Результат совпадает с ожидаемым" : "Результат не совпадает с ожидаемым"}</p>`;
      } catch (error) {
        result.innerHTML = `<p class="fault">${esc(error.message || error)}</p>`;
      } finally {
        element.querySelectorAll(".run").forEach(b => { b.disabled = false; });
        editor.setReadOnly(false); reset.disabled = false;
      }
    });
  });
}
