// pymalloc: арена (1 МиБ) делится на пулы (16 КиБ), пул — на блоки одного
// размерного класса. ОС получает арену обратно, только когда в ней нет ни
// одного живого блока. В схеме пулов и блоков меньше, чем в жизни
// (64 пула на арену и сотни блоков на пул), но устройство то же.
const ARENA_KIB = 1024;
const POOL_KIB = 16;
const REAL_POOLS = ARENA_KIB / POOL_KIB;
const POOLS = 8;
const BLOCKS = 8;

function plural(n, one, few, many) {
  const m = n % 100;
  if (m >= 11 && m <= 14) return many;
  const d = n % 10;
  if (d === 1) return one;
  return d >= 2 && d <= 4 ? few : many;
}

export function mount(element, { params = {}, blockId = "pymalloc-arenas" } = {}) {
  const requested = Number(params.arenas);
  const arenaCount = Number.isInteger(requested) && requested >= 2 && requested <= 6 ? requested : 4;
  const helpId = `${blockId}-help`;
  element.classList.add("viz", "pymalloc-arenas");
  element.innerHTML = `
    <div class="block-head"><span>Арены pymalloc</span><span>${arenaCount} арены · схема: ${POOLS} пулов по ${BLOCKS} блоков</span></div>
    <div class="pm-stage" aria-describedby="${helpId}">
      <div class="pm-arenas"></div>
      <div class="pm-stats">
        <span>Живых блоков <strong class="pm-live">0</strong></span>
        <span>Арен у процесса <strong class="pm-held">0</strong></span>
        <span>Возвращено ОС <strong class="pm-returned">0</strong></span>
      </div>
    </div>
    <p class="pm-note" role="status">Арен нет: процесс ещё не выделял память.</p>
    <div class="controls">
      <button class="pm-create" type="button">Создать</button>
      <button class="pm-thin" type="button">Удалить через один</button>
      <button class="pm-clear" type="button">Удалить все</button>
      <button class="pm-reset" type="button">Сначала</button>
    </div>
    <p class="pm-help" id="${helpId}">Арена целиком (${ARENA_KIB} КиБ, ${REAL_POOLS} пулов по ${POOL_KIB} КиБ) возвращается ОС, только когда пуста. Клик по живому блоку удаляет его.</p>`;

  const arenasEl = element.querySelector(".pm-arenas");
  const note = element.querySelector(".pm-note");
  const buttons = {
    create: element.querySelector(".pm-create"),
    thin: element.querySelector(".pm-thin"),
    clear: element.querySelector(".pm-clear"),
  };
  let arenas;
  let created;

  // blocks[a][p][b]: true, если блок жив. До «Создать» арен у процесса нет.
  function fresh() {
    return Array.from({ length: arenaCount }, () => ({
      returned: false,
      pools: Array.from({ length: POOLS }, () => Array.from({ length: BLOCKS }, () => true)),
    }));
  }

  const liveIn = arena => arena.pools.reduce((n, pool) => n + pool.filter(Boolean).length, 0);

  function sync() {
    for (const arena of arenas) if (created && !arena.returned && liveIn(arena) === 0) arena.returned = true;
  }

  function render() {
    arenasEl.replaceChildren();
    arenas.forEach((arena, a) => {
      const box = document.createElement("section");
      box.className = `pm-arena${arena.returned ? " is-returned" : ""}${created ? "" : " is-absent"}`;
      const live = liveIn(arena);
      const caption = !created ? "не выделена" : arena.returned ? "возвращена ОС" : `занято блоков: ${live} из ${POOLS * BLOCKS}`;
      box.innerHTML = `<div class="pm-arena-head"><span>арена ${a}</span><span>${caption}</span></div>`;
      const grid = document.createElement("div");
      grid.className = "pm-pools";
      arena.pools.forEach((pool, p) => {
        const poolEl = document.createElement("div");
        const empty = created && !arena.returned && pool.every(b => !b);
        poolEl.className = `pm-pool${empty ? " is-empty" : ""}`;
        poolEl.setAttribute("aria-label", `пул ${p} арены ${a}`);
        pool.forEach((alive, b) => {
          const cell = document.createElement(alive && created && !arena.returned ? "button" : "span");
          cell.className = `pm-block${alive && created && !arena.returned ? " is-live" : ""}`;
          if (cell.tagName === "BUTTON") {
            cell.type = "button";
            cell.setAttribute("aria-label", `Удалить блок ${b} пула ${p} арены ${a}`);
            cell.addEventListener("click", () => { pool[b] = false; after("Блок удалён."); });
          }
          poolEl.append(cell);
        });
        grid.append(poolEl);
      });
      box.append(grid);
      arenasEl.append(box);
    });
    const live = arenas.reduce((n, arena) => n + liveIn(arena), 0);
    const returned = arenas.filter(arena => arena.returned).length;
    element.querySelector(".pm-live").textContent = created ? live : 0;
    element.querySelector(".pm-held").textContent = created ? arenaCount - returned : 0;
    element.querySelector(".pm-returned").textContent = returned;
    buttons.create.disabled = created;
    buttons.thin.disabled = !created || live === 0;
    buttons.clear.disabled = !created || live === 0;
  }

  function after(prefix) {
    sync();
    const live = arenas.reduce((n, arena) => n + liveIn(arena), 0);
    const returned = arenas.filter(arena => arena.returned).length;
    if (live === 0) {
      note.textContent = `${prefix} Живых блоков нет, все ${arenaCount} ${plural(arenaCount, "арена пуста", "арены пусты", "арен пусты")}: ОС получила их обратно.`;
    } else if (returned > 0) {
      note.textContent = `${prefix} Пустых арен: ${returned}, их ОС получила обратно. В остальных ещё есть живые блоки, они остаются у процесса.`;
    } else {
      note.textContent = `${prefix} Пул хранит освободившиеся блоки для новых объектов, но арена цела: в каждой остались живые блоки, и ОС ничего не вернулось.`;
    }
    render();
  }

  buttons.create.addEventListener("click", () => {
    created = true;
    arenas = fresh();
    note.textContent = `Python выделил ${arenaCount} ${plural(arenaCount, "арену", "арены", "арен")} и заполнил блоки подряд: объекты лежат вплотную.`;
    render();
  });
  buttons.thin.addEventListener("click", () => {
    let i = 0;
    for (const arena of arenas) {
      if (arena.returned) continue;
      for (const pool of arena.pools) pool.forEach((alive, b) => { if (alive && i++ % 2 === 1) pool[b] = false; });
    }
    after("Удалён каждый второй живой блок.");
  });
  buttons.clear.addEventListener("click", () => {
    for (const arena of arenas) for (const pool of arena.pools) pool.fill(false);
    after("Удалены все блоки.");
  });
  element.querySelector(".pm-reset").addEventListener("click", () => {
    created = false;
    arenas = fresh();
    note.textContent = "Арен нет: процесс ещё не выделял память.";
    render();
  });

  created = false;
  arenas = fresh();
  render();
}
