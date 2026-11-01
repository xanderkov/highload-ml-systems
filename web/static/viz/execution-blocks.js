export function mount(element, {params = {}} = {}) {
  const parallel = params.parallel === true;
  let tick = 0, holdTimer;
  element.classList.add('execution-blocks');
  element.innerHTML = `<section class="exec-memory"><div class="ms-label">RAM · данные</div><div class="exec-data"><div><span>a[0]</span><strong>5</strong></div><div><span>a[1]</span><strong>8</strong></div></div></section>
  <div class="ms-path exec-memory-path" aria-hidden="true">↓ начальные значения регистров</div>
  <section class="exec-cpu"><div class="ms-label">CPU · процессор</div><div class="exec-pair">
    <section class="exec-block" data-op="add"><div class="ms-label">Блок сложения</div><div class="exec-calculation">5 + 1</div><div class="exec-register">EAX = 5</div><div class="exec-activity">Ожидание</div><div class="exec-history" aria-label="Последние такты блока сложения"></div></section>
    <section class="exec-block" data-op="sub"><div class="ms-label">Блок вычитания</div><div class="exec-calculation">8 − 2</div><div class="exec-register">EBX = 8</div><div class="exec-activity">Ожидание</div><div class="exec-history" aria-label="Последние такты блока вычитания"></div></section>
  </div></section>
  <div class="exec-loop-label">Тело цикла · ${parallel ? 'параллельное' : 'последовательное'} выполнение</div><div class="exec-program"><code data-instruction="1">ADD EAX, 1</code><code data-instruction="2">SUB EBX, 2</code></div>
  <div class="controls"><button class="exec-tick">Такт</button><button class="exec-reset">Сначала</button><span class="exec-status" role="status"></span></div><p class="exec-help">Удерживайте «Такт» или Enter. Светлые отметки — работа, тёмные — простой. ${parallel ? 'Обе независимые операции выполняются за один такт: одна итерация за такт в этой модели.' : 'Каждый такт занят один из двух блоков.'}</p>`;
  const button = element.querySelector('.exec-tick');
  function render() {
    const active = tick === 0 ? 0 : tick % 2 ? 1 : 2;
    const adds = parallel ? tick : Math.ceil(tick / 2), subs = parallel ? tick : Math.floor(tick / 2);
    const isRunning = number => parallel ? tick > 0 : active === number;
    element.querySelectorAll('[data-instruction]').forEach(node => node.classList.toggle('is-active', isRunning(Number(node.dataset.instruction))));
    for (const [name, number, count, value] of [['add', 1, adds, 5 + adds], ['sub', 2, subs, 8 - 2 * subs]]) {
      const block = element.querySelector(`[data-op="${name}"]`), running = isRunning(number);
      block.classList.toggle('is-active', running);
      block.classList.toggle('is-idle', tick > 0 && !running);
      block.querySelector('.exec-register').textContent = `${name === 'add' ? 'EAX' : 'EBX'} = ${value}`;
      block.querySelector('.exec-calculation').textContent = count === 0 ? (name === 'add' ? '5 + 1' : '8 − 2') :
        name === 'add' ? `${value - 1} + 1 = ${value}` : `${value + 2} − 2 = ${value}`;
      block.querySelector('.exec-activity').textContent = tick === 0 ? 'Ожидание' : `${running ? 'Выполняется' : 'Простой'} · работа ${count} / ${tick} тактов`;
      const first = Math.max(1, tick - 7);
      block.querySelector('.exec-history').innerHTML = Array.from({length: 8}, (_, i) => {
        const t = first + i, filled = t <= tick, busy = filled && (parallel || (t % 2 ? 1 : 2) === number);
        return `<span class="${busy ? 'is-busy' : filled ? 'is-idle' : ''}" title="${filled ? `Такт ${t}: ${busy ? 'работа' : 'простой'}` : 'Ещё не выполнен'}">${filled ? t : '·'}</span>`;
      }).join('');
    }
    element.querySelector('.exec-status').textContent = tick === 0 ? 'Такт 0' : `Такт ${tick} · итерация ${adds} · завершено ${subs}`;
  }
  function advance() { tick++; render(); }
  function stop() { clearInterval(holdTimer); holdTimer = undefined; }
  function start() { if (holdTimer !== undefined) return; advance(); holdTimer = setInterval(advance, 450); }
  button.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    event.preventDefault(); button.focus({preventScroll:true}); button.setPointerCapture(event.pointerId); start();
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) button.addEventListener(name, stop);
  button.addEventListener('click', event => { if (event.detail === 0) advance(); });
  button.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!event.repeat) start(); }
  });
  button.addEventListener('keyup', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); stop(); } });
  button.addEventListener('blur', stop);
  window.addEventListener('blur', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  element.querySelector('.exec-reset').addEventListener('click', () => { stop(); tick = 0; render(); });
  render();
}
