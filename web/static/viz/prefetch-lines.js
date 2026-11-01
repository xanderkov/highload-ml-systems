const LINE=16, values=Array.from({length:64},(_,i)=>i%9+1);
export function mount(element){
 let done=0,sum=0,phase='load',timer,generation=0,cached=new Set([0]),pending=new Set(),flights=new Set();
 element.classList.add('viz','cache-walk','cache-dual','prefetch-cache');
 element.innerHTML=`<div class="block-head">Последовательный обход · предвыборка</div><div class="cs-progress"><span>Просуммировано <strong>0 / 64</strong></span><progress max="64" value="0"></progress></div><p class="cs-note" role="status"></p>
 <div class="memory-sum-stage cache-stage" tabindex="0">
 <section class="ms-memory"><div class="ms-label">RAM · память</div><div class="cs-memory-grid" style="--matrix-size:8">${values.map((v,i)=>`<span class="cs-memory-cell" data-index="${i}">${v}</span>`).join('')}</div></section>
 <div class="ms-path">↓ кэш-линии · по 64 байта</div>
 <section class="ms-cpu"><div class="ms-label ms-cpu-label">CPU · процессор</div>
 <section class="cs-cache"><div class="ms-label">Кэш · четыре линии</div>${[0,1,2,3].map(l=>`<div class="pf-cache-row" data-line="${l}"><div class="ms-label">Линия ${l} <span class="pf-line-status"></span></div><div class="cs-cache-grid">${values.slice(l*LINE,(l+1)*LINE).map(()=>'<span class="cs-cache-cell">—</span>').join('')}</div></div>`).join('')}<div class="cs-cache-status"></div></section>
 <div class="ms-path">↓ элемент</div><section class="ms-register-bank"><div class="ms-label">Регистры</div><div class="ms-registers"><div class="ms-register"><span class="ms-address">Элемент</span><strong class="cs-value">—</strong></div><div class="ms-register"><span class="ms-address">Сумма</span><strong class="cs-sum">0</strong></div></div></section>
 <div class="ms-path">↓ операнды · ↑ результат</div><section class="ms-execution"><div class="ms-label">Выполнение</div><code class="ms-operation">Ожидание</code></section></section>
 </div><div class="controls"><button class="pf-step">Такт</button><button class="pf-reset">Сначала</button></div><p class="caption">Нажимайте или удерживайте «Такт». Enter работает, когда кнопка в фокусе. Предвыборка выполняется одновременно с обработкой элементов.</p>`;
 const stage=element.querySelector('.cache-stage'),button=element.querySelector('.pf-step'),memory=[...element.querySelectorAll('.cs-memory-cell')];
 function stop(){clearInterval(timer);timer=undefined;}
 function render(){
 element.querySelector('.cs-progress strong').textContent=`${done} / 64`;element.querySelector('progress').value=done;
 element.querySelector('.cs-sum').textContent=sum;
 memory.forEach((cell,i)=>{cell.classList.toggle('is-fetching',pending.has(Math.floor(i/LINE)));});
 element.querySelectorAll('.pf-cache-row').forEach(row=>{const l=Number(row.dataset.line);row.querySelector('.pf-line-status').textContent=pending.has(l)?'· загружается заранее':cached.has(l)?'· готова':'· пусто';row.querySelectorAll('.cs-cache-cell').forEach((c,i)=>{c.textContent=cached.has(l)?values[l*LINE+i]:'—';c.classList.toggle('is-current',done<64&&l*LINE+i===done&&cached.has(l));});});
 element.querySelector('.cs-cache-status').textContent=pending.size?`Prefetcher загружает линии ${[...pending].join(', ')}`:'Следующие загруженные линии готовы к чтению';
 button.disabled=done===64;if(button.disabled)stop();
 }
 function prefetch(l){if(l>=4||cached.has(l)||pending.has(l))return;pending.add(l);const epoch=generation;
 const target=element.querySelector(`[data-line="${l}"] .cs-cache-grid`),packet=document.createElement('span');packet.className='ms-flying-number cs-packet is-line';packet.setAttribute('aria-hidden','true');
 packet.innerHTML=values.slice(l*LINE,(l+1)*LINE).map(v=>`<span>${v}</span>`).join('');stage.append(packet);
 const origin=stage.getBoundingClientRect(),a=memory[l*LINE].getBoundingClientRect(),b=target.getBoundingClientRect();packet.style.left=`${a.left-origin.left+a.width/2}px`;packet.style.top=`${a.top-origin.top}px`;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const animation=packet.animate(reduced?[{opacity:0},{opacity:0}]:[{transform:'translate(-50%, -50%)'},{transform:`translate(calc(-50% + ${b.left+b.width/2-a.left-a.width/2}px), calc(-50% + ${b.top+b.height/2-a.top}px))`}],{duration:450,easing:'ease-in-out'});
 flights.add(animation);animation.onfinish=()=>{flights.delete(animation);packet.remove();if(epoch!==generation)return;pending.delete(l);cached.add(l);render();};
 }
 function tick(){if(done===64)return;const line=Math.floor(done/LINE);prefetch(line+1);prefetch(line+2);
 const operation=element.querySelector('.ms-operation');
 if(!cached.has(line)){prefetch(line);operation.textContent='Ожидание данных';}
 else if(phase==='load'){element.querySelector('.cs-value').textContent=values[done];operation.textContent=`value = a[${done}];`;phase='add';}
 else{operation.textContent=`sum += value;  // ${sum} + ${values[done]} = ${sum+values[done]}`;sum+=values[done];done++;phase='load';}
 element.querySelector('.cs-note').textContent=done===64?'Все элементы просуммированы.':pending.size?'Ядро обрабатывает текущую линию, префетчер загружает следующие.':'Читаем элементы из заранее заполненного кэша.';render();}
 function start(){stop();tick();if(!button.disabled)timer=setInterval(tick,65);}
 button.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();button.focus();start();});button.addEventListener('click',e=>{if(e.detail===0)tick();});button.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(!e.repeat)start();}});button.addEventListener('keyup',stop);button.addEventListener('blur',stop);window.addEventListener('pointerup',stop);window.addEventListener('pointercancel',stop);window.addEventListener('blur',stop);document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
 function reset(){stop();generation++;flights.forEach(a=>a.cancel());flights.clear();stage.querySelectorAll('.cs-packet').forEach(p=>p.remove());done=0;sum=0;phase='load';cached=new Set([0]);pending=new Set();element.querySelector('.cs-value').textContent='—';element.querySelector('.ms-operation').textContent='Ожидание';element.querySelector('.cs-note').textContent='Первая линия в кэше; последовательный доступ уже обнаружен.';render();}
 element.querySelector('.pf-reset').addEventListener('click',reset);reset();
}
