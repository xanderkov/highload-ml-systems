// Copy-on-write после fork: воркер только читает, но каждое чтение
// Python-объекта увеличивает его ob_refcnt — это запись в страницу, и ядро
// копирует страницу целиком. Второй режим — те же числа в одном массиве:
// счётчик ссылок есть только у заголовка массива, буфер с данными не трогается.
const PAGES = 6;
const PAGE_BYTES = 4096;

const MODES = {
  objects: {
    label: "dict из объектов",
    code: ["for key in keys:", "    token_id, score = vocab[key]", "    # Py_INCREF(record): ob_refcnt += 1"],
  },
  array: {
    label: "numpy-массив",
    code: ["for key in keys:", "    pos = np.searchsorted(hashes, h(key))", "    token_id = ids[pos]  # +1 только у ids"],
  },
};

function plural(n) {
  if (n === 1) return "объект";
  return n < 5 ? "объекта" : "объектов";
}

export function mount(element, { params = {}, blockId = "cow-pages" } = {}) {
  const requested = Number(params.objects_per_page);
  const perPage = Number.isInteger(requested) && requested >= 1 && requested <= 8 ? requested : 4;
  const helpId = `${blockId}-help`;
  element.classList.add("viz", "cow-pages");
  element.innerHTML = `
    <div class="block-head"><span>Copy-on-write после fork</span><span>${PAGES} страниц · ${perPage} ${plural(perPage)} на страницу</span></div>
    <div class="cow-modes controls" role="radiogroup" aria-label="Как хранятся данные">
      ${Object.entries(MODES).map(([key, mode]) =>
        `<button type="button" role="radio" data-mode="${key}" aria-checked="false">${mode.label}</button>`).join("")}
    </div>
    <div class="cow-stage" tabindex="0" aria-label="Страницы памяти родителя и воркера" aria-describedby="${helpId}">
      <pre class="cow-code" aria-hidden="true"></pre>
      <section class="cow-space" data-owner="parent">
        <div class="cow-title">Родитель · виртуальные страницы</div>
        <div class="cow-pages-row"></div>
      </section>
      <section class="cow-space" data-owner="child">
        <div class="cow-title">Воркер после fork · виртуальные страницы</div>
        <div class="cow-pages-row"></div>
      </section>
      <div class="cow-stats">
        <span>Прочитано объектов <strong class="cow-reads">0</strong></span>
        <span>Скопировано страниц <strong class="cow-copies">0</strong></span>
        <span>Физическая память <strong class="cow-physical">0</strong></span>
      </div>
    </div>
    <p class="cow-note" role="status">Ожидание</p>
    <div class="controls">
      <button class="tick" type="button" aria-describedby="${helpId}">Такт</button>
      <button class="restart" type="button">Сначала</button>
    </div>
    <p class="cow-help" id="${helpId}">«Такт» или Enter: воркер читает следующий объект. Клик по объекту в строке воркера читает именно его.</p>`;

  const stage = element.querySelector(".cow-stage");
  const tick = element.querySelector(".tick");
  const note = element.querySelector(".cow-note");
  const code = element.querySelector(".cow-code");
  const rows = {
    parent: element.querySelector('[data-owner="parent"] .cow-pages-row'),
    child: element.querySelector('[data-owner="child"] .cow-pages-row'),
  };
  let mode = "objects";
  let state;

  // Раскладка: в режиме объектов на каждой странице perPage записей со своим
  // ob_refcnt. В режиме массива на странице 0 живёт заголовок ndarray (у него
  // и refcount, и указатель на буфер), а остальные страницы — сырой буфер.
  function layout() {
    const pages = [];
    let next = 0;
    for (let p = 0; p < PAGES; p++) {
      const objects = [];
      if (mode === "objects") {
        for (let k = 0; k < perPage; k++) objects.push({ id: next++, label: `tok${next - 1}`, refcnt: 1 });
      } else if (p === 0) {
        objects.push({ id: "header", label: "ndarray", refcnt: 1 });
      } else {
        for (let k = 0; k < perPage; k++) objects.push({ id: next++, label: `ids[${next - 1}]`, refcnt: null });
      }
      pages.push({ objects, copied: false });
    }
    return pages;
  }

  function readable() {
    return state.pages.flatMap(page => page.objects).filter(object => object.id !== "header");
  }

  function render() {
    code.textContent = MODES[mode].code.join("\n");
    for (const [owner, row] of Object.entries(rows)) {
      row.replaceChildren();
      state.pages.forEach((page, p) => {
        const node = document.createElement("div");
        const shared = !page.copied;
        node.className = `cow-page${owner === "child" ? (shared ? " is-shared" : " is-copied") : ""}${page.copied && owner === "parent" ? " is-split" : ""}`;
        if (state.flash === p && owner === "child") node.classList.add("is-flash");
        const caption = owner === "child"
          ? (shared ? "общая с родителем" : "своя копия · 4 КиБ")
          : (page.copied ? "только у родителя" : "общая");
        node.innerHTML = `<div class="cow-page-head"><span>стр. ${p}</span><span>${caption}</span></div>`;
        const list = document.createElement("div");
        list.className = "cow-objects";
        for (const object of page.objects) {
          const cell = document.createElement(owner === "child" && object.id !== "header" ? "button" : "span");
          cell.className = "cow-object";
          if (object.id === "header") cell.classList.add("is-header");
          if (state.current === object.id) cell.classList.add("is-current");
          if (state.read.has(object.id)) cell.classList.add("is-read");
          // Пока объект в работе, у воркера на нём +1; после — снова как было.
          // Значение возвращается, а копия страницы остаётся.
          const inUse = owner === "child" && (state.current === object.id || (object.id === "header" && state.current !== null));
          const count = object.refcnt === null ? "" : `<small>refcnt ${object.refcnt + (inUse ? 1 : 0)}</small>`;
          cell.innerHTML = `<span>${object.label}</span>${count}`;
          if (cell.tagName === "BUTTON") {
            cell.type = "button";
            cell.setAttribute("aria-label", `Прочитать ${object.label}`);
            cell.addEventListener("click", () => read(object.id));
          }
          list.append(cell);
        }
        node.append(list);
        row.append(node);
      });
    }
    const copies = state.pages.filter(page => page.copied).length;
    element.querySelector(".cow-reads").textContent = state.read.size;
    element.querySelector(".cow-copies").textContent = `${copies} из ${PAGES}`;
    element.querySelector(".cow-physical").textContent = `${(PAGES + copies) * 4} КиБ`;
    for (const button of element.querySelectorAll(".cow-modes button")) {
      button.setAttribute("aria-checked", String(button.dataset.mode === mode));
      button.classList.toggle("is-active", button.dataset.mode === mode);
    }
    tick.disabled = state.read.size === readable().length;
  }

  function touch(pageIndex, what) {
    const page = state.pages[pageIndex];
    if (page.copied) return `${what}: страница ${pageIndex} уже своя, запись идёт в копию.`;
    page.copied = true;
    state.flash = pageIndex;
    return `${what}: запись ob_refcnt в общую страницу ${pageIndex}. Ядро копирует все ${PAGE_BYTES} байт ради 8 байт счётчика.`;
  }

  function read(id) {
    if (state.read.has(id)) {
      note.textContent = "Этот объект уже прочитан. Счётчик вернулся к прежнему значению, но копия страницы осталась.";
      return;
    }
    state.flash = null;
    state.current = id;
    state.read.add(id);
    const pageIndex = state.pages.findIndex(page => page.objects.some(object => object.id === id));
    const object = state.pages[pageIndex].objects.find(o => o.id === id);
    if (mode === "objects") {
      note.textContent = touch(pageIndex, `Чтение ${object.label}`);
    } else {
      const first = !state.pages[0].copied;
      const message = touch(0, `Чтение ${object.label}`);
      note.textContent = first
        ? `${message} Страница ${pageIndex} с данными только читается и остаётся общей.`
        : `Чтение ${object.label}: refcount меняется лишь у заголовка, страница ${pageIndex} с данными остаётся общей.`;
    }
    render();
  }

  function step() {
    const next = readable().find(object => !state.read.has(object.id));
    if (next) read(next.id);
  }

  function reset() {
    state = { pages: layout(), read: new Set(), current: null, flash: null };
    note.textContent = mode === "objects"
      ? "После fork все страницы общие: физически каждая лежит в памяти один раз."
      : "Те же данные в массиве: refcount есть только у заголовка ndarray на странице 0.";
    render();
  }

  tick.addEventListener("click", () => { step(); tick.focus({ preventScroll: true }); });
  stage.addEventListener("keydown", event => {
    if (event.target !== stage || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    step();
  });
  element.querySelector(".restart").addEventListener("click", () => { reset(); stage.focus({ preventScroll: true }); });
  for (const button of element.querySelectorAll(".cow-modes button")) {
    button.addEventListener("click", () => {
      mode = button.dataset.mode;
      reset();
    });
  }
  reset();
}
