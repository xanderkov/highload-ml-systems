import { formatMs } from "../result.js";

// Instructions stay beside the experiment; navigation and scrolling stay free.
export function mountIndexTutorial(element, editor, starter) {
  const button = element.querySelector(".run");
  const reset = element.querySelector(".reset");
  const expression = "a[i * n + j]";
  const replacement = "a[j * n + i]";
  const row = starter.split("\n").findIndex((line) => line.includes(expression));
  if (row < 0) return null;
  const normalize = (code) => code.replace(/\s/g, "");
  const expected = normalize(starter.replace(expression, replacement));
  let phase = "first";
  let busy = false;
  let baseline = null;
  let marker;

  const layout = document.createElement("div");
  layout.className = "exercise-with-guide is-active";
  element.before(layout);
  layout.append(element);
  element.classList.add("has-tutorial");
  reset.disabled = true;

  const panel = document.createElement("aside");
  panel.className = "exercise-guide";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Инструкция к замеру");
  panel.innerHTML = `
    <div class="guide-baseline" hidden>
      <span class="guide-label">Первый замер · исходный код</span>
      <strong class="guide-time"></strong>
      <p>Это время также отображается в таблице под редактором.</p>
    </div>
    <div class="guide-instruction" aria-live="polite"></div>`;
  layout.append(panel);
  const instruction = panel.querySelector(".guide-instruction");

  function show(error = false) {
    panel.hidden = false;
    panel.classList.toggle("is-first", phase === "first");
    instruction.hidden = false;
    if (error) {
      instruction.textContent = "Замер не получился. Подробности под редактором. Нажмите «Замерить», чтобы повторить.";
    } else if (phase === "first") {
      instruction.innerHTML = '<span class="guide-label">Первый замер</span><p>Нажмите «Замерить», чтобы получить время выполнения исходного кода.</p>';
    } else if (phase === "edit") {
      instruction.innerHTML = `<span class="guide-label">Изменение кода</span>
        <p>В строке ${row + 1} поменяйте местами <code>i</code> и <code>j</code>.</p>`;
    } else {
      instruction.textContent = "Нажмите «Замерить», чтобы измерить время после изменения индексов.";
    }
    editor.setReadOnly(phase === "first");
    button.disabled = phase === "edit";
    if (marker !== undefined) editor.session.removeMarker(marker);
    marker = undefined;
    if (phase === "edit") {
      const Range = ace.require("ace/range").Range;
      marker = editor.session.addMarker(new Range(row, 0, row, 1), "tutorial-code-line", "fullLine");
    }
    if (baseline !== null) {
      panel.querySelector(".guide-baseline").hidden = false;
      panel.querySelector(".guide-time").textContent = formatMs(baseline);
      element.querySelector(".runs .is-match")?.closest("tr").classList.add("tutorial-baseline");
    }
    editor.resize();
  }

  function changed() {
    if (busy || !["edit", "repeat"].includes(phase)) return;
    const next = normalize(editor.getValue()) === expected ? "repeat" : "edit";
    if (next === phase) return;
    phase = next;
    show();
  }
  editor.session.on("change", changed);

  show();

  return {
    blocksRun: () => busy || phase === "edit",
    running() {
      if (phase === "closed") return;
      busy = true;
      instruction.hidden = true;
      panel.hidden = baseline === null;
      editor.setReadOnly(true);
    },
    settled(data) {
      if (phase === "closed") return;
      busy = false;
      const success = data.status === "ok" && data.correct;
      if (success && phase === "repeat") {
        phase = "closed";
        panel.remove();
        layout.classList.remove("is-active");
        reset.disabled = false;
        editor.setReadOnly(false);
        editor.session.removeListener("change", changed);
        editor.resize();
        return;
      }
      if (success) {
        baseline = data.student_ms;
        phase = "edit";
      }
      show(!success);
    },
  };
}
