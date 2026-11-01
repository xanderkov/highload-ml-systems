export function mount(element) {
  const a = Array.from({length: 16}, (_, i) => i + 1);
  const b = Array.from({length: 16}, (_, i) => i % 4 + 2);
  let steps = 0, timer;
  element.classList.add('simd-demo', 'cache-walk', 'cache-dual');
  element.innerHTML = `<div class="block-head">Поэлементное сложение двух массивов</div>
    <div class="simd-lanes">${[1,4].map(width => `<section data-width="${width}">
      <div class="comparison-title">${width === 1 ? 'По одному элементу' : 'SIMD · по четыре элемента'}</div>
      <div class="memory-sum-stage cache-stage"><section class="ms-memory"><div class="ms-label">RAM · память</div>${['a','b','out'].map(name => `<div class="simd-row"><span>${name}</span><div class="simd-cells">${a.map((_, i) => `<span data-index="${i}">${name === 'a' ? a[i] : name === 'b' ? b[i] : '·'}</span>`).join('')}</div></div>`).join('')}
      </section><div class="ms-path">↓ операнды · ↑ результат</div>
      <section class="ms-cpu"><div class="ms-label ms-cpu-label">CPU · процессор</div>
      <section class="ms-register-bank"><div class="ms-label">${width === 1 ? 'Регистры · по одному числу' : 'Векторные регистры · по четыре числа'}</div>
      <div class="simd-registers">${['a', 'b', 'out'].map(name => `<div class="ms-register"><span class="ms-address">${name}</span><div class="simd-register-values" data-register="${name}">${Array.from({length:width},()=>'<strong>—</strong>').join('')}</div></div>`).join('')}</div></section>
      <div class="ms-path">↓ операнды · ↑ результат</div><section class="ms-execution"><div class="ms-label">Выполнение</div><code class="simd-operation"></code></section>
      </section></div><div class="simd-progress" aria-live="polite"></div>
    </section>`).join('')}</div>
    <div class="controls"><button class="simd-step">Шаг</button><button class="simd-reset">Сначала</button></div>
    <p class="caption">Нажимайте «Шаг» или удерживайте кнопку для непрерывного выполнения. Enter работает, когда кнопка в фокусе.</p>`;
  const button = element.querySelector('.simd-step');
  function render() {
    for (const lane of element.querySelectorAll('[data-width]')) {
      const width = Number(lane.dataset.width), done = Math.min(16, steps * width);
      const active = steps > 0 && steps <= 16 / width;
      lane.querySelectorAll('.simd-row').forEach((row, r) => {
        row.querySelectorAll('[data-index]').forEach((cell, i) => {
          cell.classList.toggle('is-active', active && i >= done - width && i < done);
          cell.classList.toggle('is-done', r === 2 && i < done);
          if (r === 2) cell.textContent = i < done ? a[i] + b[i] : '·';
        });
      });
      const from = Math.max(0, done - width);
      for (const name of ['a', 'b', 'out']) {
        lane.querySelectorAll(`[data-register="${name}"] strong`).forEach((cell, j) => {
          const i = from + j;
          cell.textContent = steps === 0 ? '—' : name === 'a' ? a[i] : name === 'b' ? b[i] : a[i] + b[i];
        });
      }
      lane.querySelector('.simd-operation').textContent = steps === 0 ? 'a + b → out' :
        Array.from({length: width}, (_, j) => `${a[from+j]} + ${b[from+j]} = ${a[from+j]+b[from+j]}`).join('   ·   ');
      lane.querySelector('.simd-progress').textContent = `Сложений${width > 1 ? ' группами' : ''}: ${Math.min(steps, 16 / width)} · элементов: ${done} / 16`;
    }
    button.disabled = steps === 16;
    if (button.disabled) stop();
  }
  function stop() { clearInterval(timer); timer = undefined; }
  function step() { if (steps < 16) { steps++; render(); } }
  button.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    event.preventDefault(); button.focus(); stop(); step();
    if (steps < 16) timer = setInterval(step, 220);
  });
  button.addEventListener('click', event => { if (event.detail === 0) step(); });
  button.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!event.repeat) { step(); if (steps < 16) timer = setInterval(step, 220); } }
  });
  button.addEventListener('keyup', stop);
  button.addEventListener('blur', stop);
  window.addEventListener('pointerup', stop);
  window.addEventListener('pointercancel', stop);
  window.addEventListener('blur', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  element.querySelector('.simd-reset').addEventListener('click', () => { stop(); steps = 0; render(); });
  render();
}
