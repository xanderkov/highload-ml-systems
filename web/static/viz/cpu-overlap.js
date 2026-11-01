const OPS = [
 {name:'x = data[i]',out:'x',deps:[],unit:'load',run:()=>7},
 {name:'y = x + 1',out:'y',deps:['x'],unit:'alu',run:v=>v.x+1},
 {name:'p = a + b',out:'p',deps:[],unit:'alu',run:()=>12},
 {name:'q = c + d',out:'q',deps:[],unit:'alu',run:()=>18},
 {name:'t = p + q',out:'t',deps:['p','q'],unit:'alu',run:v=>v.p+v.q},
 {name:'result = y + t',out:'result',deps:['y','t'],unit:'alu',run:v=>v.y+v.t},
];
export function mount(element) {
 let tick=0,timer,playing=false,states,values,nextRetire,lastCompleted,events=[],animations=[];
 element.classList.add('pipeline-demo');
 element.innerHTML=`<div class="block-head">Одно ядро · независимое выполнение операций</div>
 <div class="pipe-memory">RAM · data[i] = 7 <span>Исходные регистры: a = 5, b = 7, c = 8, d = 10</span></div>
 <div class="pipe-scroll"><div class="pipe-core"><div class="ms-label">CPU · процессор</div><div class="pipe-flow">
 <section class="pipe-stage"><h4>Подготовка</h4><p>До двух операций за шаг</p><div data-zone="decode"></div></section>
 <section class="pipe-stage"><h4>Очередь</h4><p>Ждём операнды и свободный блок</p><div data-zone="queue"></div></section>
 <section class="pipe-stage pipe-execution"><h4>Выполнение</h4><div class="pipe-unit" data-unit="load"><div class="ms-label">Загрузка из памяти</div><div class="pipe-unit-status"></div><div data-zone="load"></div><progress max="8" value="0" aria-label="Загрузка из памяти"></progress><div class="pipe-unit-last"></div></div>${[0,1].map(i=>`<div class="pipe-unit" data-unit="alu${i}"><div class="ms-label">Блок сложения ${i+1}</div><div class="pipe-unit-status"></div><div data-zone="alu${i}"></div><progress max="2" value="0" aria-label="Выполнение сложения"></progress><div class="pipe-unit-last"></div></div>`).join('')}</section>
 <section class="pipe-stage"><h4>Результат готов</h4><p>Уже доступен зависимым операциям</p><div data-zone="complete"></div></section>
 <section class="pipe-stage"><h4>Фиксация</h4><p>В исходном порядке программы</p><div data-zone="retired"></div></section>
 </div></div></div><div class="pipe-registers"></div><p class="pipe-note" aria-live="polite"></p>
 <div class="controls"><button class="pipe-step">Шаг</button><button class="pipe-play">Запустить</button><button class="pipe-reset">Сначала</button><span class="pipe-count"></span></div>
 <p class="caption">Можно выполнять по шагам, удерживать «Шаг» или включить автоматическое выполнение.</p>`;
 const cards=OPS.map((op,i)=>{const card=document.createElement('div');card.className='pipe-card';card.dataset.op=i;card.innerHTML=`<span class="pipe-order">${i+1}</span><code>${op.name}</code><small></small>`;return card;});
 const stepButton=element.querySelector('.pipe-step'),playButton=element.querySelector('.pipe-play');
 function halt(){clearInterval(timer);timer=undefined;playing=false;playButton.textContent='Запустить';}
 function draw(animate=true){
  animations.forEach(a=>a.cancel());animations=[];
  const before=cards.map(c=>c.isConnected?c.getBoundingClientRect():null);
  states.forEach((s,i)=>{
   const card=cards[i],op=OPS[i];card.dataset.state=s.state;
   const zone=s.state==='execute'?s.unit:s.state==='waiting'?'decode':s.state;
   element.querySelector(`[data-zone="${zone}"]`).append(card);
   const missing=op.deps.filter(d=>!(d in values));
   card.querySelector('small').textContent=s.state==='waiting'?'Ожидает подготовки':s.state==='decode'?'Декодирование':s.state==='queue'?(missing.length?`Ждёт ${missing.join(', ')}`:'Операнды готовы'):s.state==='execute'?`Осталось шагов: ${s.remaining}`:`${op.out} = ${values[op.out]}`;
   card.classList.toggle('is-waiting',s.state==='queue'&&missing.length>0);
  });
  if(animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches)cards.forEach((c,i)=>{const from=before[i],to=c.getBoundingClientRect();if(from&&(from.x!==to.x||from.y!==to.y))animations.push(c.animate([{transform:`translate(${from.x-to.x}px, ${from.y-to.y}px)`},{transform:'translate(0,0)'}],{duration:280,easing:'ease-out'}));});
  for(const unit of ['load','alu0','alu1']){
   const box=element.querySelector(`[data-unit="${unit}"]`);
   const current=states.findIndex(s=>s.state==='execute'&&s.unit===unit);
   const busy=current>=0, duration=unit==='load'?8:2, last=lastCompleted[unit];
   box.classList.toggle('is-busy',busy);
   box.classList.toggle('is-free',!busy);
   box.querySelector('.pipe-unit-status').textContent=busy?`Занят · осталось ${states[current].remaining} шагов`:'Свободен';
   box.querySelector('progress').value=busy?duration-states[current].remaining:0;
   box.querySelector('.pipe-unit-last').textContent=last?`Завершено на шаге ${last.tick}: ${OPS[last.op].name} → ${values[OPS[last.op].out]}`:'Ещё не выполнял операции';
  }
  element.querySelector('.pipe-registers').textContent=nextRetire?`Зафиксировано: ${OPS.slice(0,nextRetire).map(op=>`${op.out} = ${values[op.out]}`).join(' · ')}`:'Результаты ещё не зафиксированы';
  element.querySelector('.pipe-count').textContent=`Шаг ${tick}`;
  const busy=states.filter(s=>s.state==='execute').length;
  element.querySelector('.pipe-note').textContent=nextRetire===OPS.length?'Все результаты зафиксированы. result = 38.':events.length?events.join(' '):states[0].state==='execute'&&busy>1?'Загрузка памяти продолжается, а независимые сложения уже выполняются на других блоках.':states.some((s,i)=>s.state==='complete'&&i>nextRetire)?'Поздние операции уже завершены. Их результаты доступны, но фиксация ждёт более ранних операций.':tick===0?'Операции стоят в исходном порядке. Следите, как p и q обгонят ожидающее загрузки вычисление y.':'Готовые операции занимают подходящие свободные блоки. Зависимые ждут свои операнды.';
  stepButton.disabled=playButton.disabled=nextRetire===OPS.length;if(stepButton.disabled)halt();
 }
 function advance(){if(nextRetire===OPS.length)return;tick++;events=[];
  // Retire only completed operations, in program order.
  for(let n=0;n<2&&nextRetire<OPS.length&&states[nextRetire].state==='complete';n++)states[nextRetire++].state='retired';
  states.forEach((s,i)=>{if(s.state==='execute'&&--s.remaining===0){s.state='complete';values[OPS[i].out]=OPS[i].run(values);lastCompleted[s.unit]={op:i,tick};}});
  // Ready instructions may bypass older instructions waiting for data.
  for(const unit of ['load','alu0','alu1']){
   if(states.some(s=>s.state==='execute'&&s.unit===unit))continue;
   const i=states.findIndex((s,i)=>s.state==='queue'&&OPS[i].unit===(unit==='load'?'load':'alu')&&OPS[i].deps.every(d=>d in values));
   if(i>=0){
    Object.assign(states[i],{state:'execute',unit,remaining:unit==='load'?8:2});
    if(lastCompleted[unit]?.tick===tick){
     events.push(`Блок сложения ${unit==='alu0'?1:2} завершил «${OPS[lastCompleted[unit].op].name}» и взял из очереди «${OPS[i].name}».${states[0].state==='execute'?' Загрузка памяти всё ещё продолжается.':''}`);
    }
   }
  }
  states.forEach(s=>{if(s.state==='decode')s.state='queue';});
  let fetched=0;states.forEach(s=>{if(s.state==='waiting'&&fetched<2){s.state='decode';fetched++;}});
  draw();
 }
 function hold(){halt();advance();if(!stepButton.disabled)timer=setInterval(advance,550);}
 stepButton.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();stepButton.focus();hold();});
 stepButton.addEventListener('click',e=>{if(e.detail===0)advance();});
 stepButton.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(!e.repeat)hold();}});
 const release=()=>{if(!playing)halt();};stepButton.addEventListener('keyup',release);stepButton.addEventListener('blur',release);window.addEventListener('pointerup',release);window.addEventListener('pointercancel',release);
 playButton.addEventListener('click',()=>{if(playing){halt();return;}halt();playing=true;playButton.textContent='Пауза';advance();if(!stepButton.disabled)timer=setInterval(advance,550);});
 window.addEventListener('blur',halt);document.addEventListener('visibilitychange',()=>{if(document.hidden)halt();});
 function reset(){halt();tick=0;values={};nextRetire=0;lastCompleted={};events=[];states=OPS.map(()=>({state:'waiting'}));draw(false);}
 element.querySelector('.pipe-reset').addEventListener('click',reset);reset();
}
