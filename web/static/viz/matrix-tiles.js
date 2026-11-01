const N=4, B=2;
const A=Array.from({length:16},(_,i)=>i%5+1),D=Array.from({length:16},(_,i)=>i%3+1);
function schedule(blocked){const ops=[];if(!blocked){for(let i=0;i<N;i++)for(let j=0;j<N;j++)for(let k=0;k<N;k++)ops.push({i,j,k});}else{for(let ii=0;ii<N;ii+=B)for(let jj=0;jj<N;jj+=B)for(let kk=0;kk<N;kk+=B)for(let i=ii;i<ii+B;i++)for(let k=kk;k<kk+B;k++)for(let j=jj;j<jj+B;j++)ops.push({i,j,k,ii,jj,kk});}return ops;}
export function mount(element){
 let step=0,timer;
 const fresh = blocked => ({ops:schedule(blocked),sum:Array(16).fill(0),done:0,cache:[],wait:0,misses:0,hits:0,prepared:false,elapsed:0});
 const lanes=[fresh(false),fresh(true)];
 element.classList.add('matrix-demo');
 element.innerHTML=`<div class="block-head">Умножение матриц 4 × 4</div><div class="matrix-lanes">${lanes.map((_,index)=>`<section data-lane="${index}"><div class="comparison-title">${index?'Блочный обход · 2 × 2':'Наивный обход · строка и столбец'}</div><div class="matrix-set">${['A','B','C'].map((name,m)=>`<div><div class="matrix-name">${name}</div><div class="matrix-grid" data-matrix="${m}">${A.map((_,i)=>`<span data-cell="${i}">${m===0?A[i]:m===1?D[i]:0}</span>`).join('')}</div></div>`).join('')}</div><div class="matrix-model-cache"><div class="ms-label">Кэш входных данных · 4 линии по 2 числа</div><div class="matrix-cache-slots"></div></div><div class="matrix-operation"></div><div class="matrix-stats"></div><div class="matrix-block-note"></div></section>`).join('')}</div><div class="controls"><button class="matrix-step">Шаг</button><button class="matrix-reset">Сначала</button><span class="matrix-count"></span></div><p class="caption">Нажмите или удерживайте «Шаг». Enter работает, когда кнопка в фокусе.</p>`;
 const button=element.querySelector('.matrix-step');
 function stop(){clearInterval(timer);timer=undefined;}
 function render(){lanes.forEach((lane,index)=>{const node=element.querySelector(`[data-lane="${index}"]`),op=step?lane.ops[Math.min(lane.done,63)]:null;
 node.querySelectorAll('[data-matrix]').forEach((grid,m)=>grid.querySelectorAll('[data-cell]').forEach((cell,pos)=>{const row=Math.floor(pos/N),col=pos%N;
 const active=op&&(m===0?row===op.i&&col===op.k:m===1?row===op.k&&col===op.j:row===op.i&&col===op.j);
 const tile=op&&index===1&&(m===0?row>=op.ii&&row<op.ii+B&&col>=op.kk&&col<op.kk+B:m===1?row>=op.kk&&row<op.kk+B&&col>=op.jj&&col<op.jj+B:row>=op.ii&&row<op.ii+B&&col>=op.jj&&col<op.jj+B);
 cell.classList.toggle('in-tile',!!tile);cell.classList.toggle('is-active',!!active);if(m===2)cell.textContent=lane.sum[pos];}));
 node.querySelector('.matrix-operation').textContent=lane.done===64?'Готово':lane.wait?`Ожидание памяти · осталось шагов: ${lane.wait}`:op?`C[${op.i}, ${op.j}] += ${A[op.i*N+op.k]} × ${D[op.k*N+op.j]} → ${lane.sum[op.i*N+op.j]}`:'C[i, j] += A[i, k] × B[k, j]';
 node.querySelector('.matrix-block-note').textContent=!op?'Результат сначала заполнен нулями':index===0?`Строка A: ${op.i}, столбец B: ${op.j}`:`Рабочие блоки A, B и C выделены серым`;
 node.querySelector('.matrix-stats').textContent=`Вычислено: ${lane.done} / 64 · загрузок: ${lane.misses} · шагов: ${lane.elapsed}`;
 node.querySelector('.matrix-cache-slots').innerHTML=Array.from({length:4},(_,i)=>`<span>${lane.cache[i] || '—'}</span>`).join('');
 node.classList.toggle('is-waiting',lane.wait>0);
 });element.querySelector('.matrix-count').textContent=`Общий шаг: ${step}`;button.disabled=lanes.every(l=>l.done===64);if(button.disabled)stop();}
 function advance(){if(lanes.every(l=>l.done===64))return;
 for(const lane of lanes){
  if(lane.done===64)continue;lane.elapsed++;
  if(lane.wait){lane.wait--;continue;}
  const {i,j,k}=lane.ops[lane.done];
  if(!lane.prepared){
   let misses=0;
   for(const [name,pos] of [['A',i*N+k],['B',k*N+j]]){
    const base=Math.floor(pos/2)*2,key=`${name}[${base}…${base+1}]`,at=lane.cache.indexOf(key);
    if(at>=0){lane.hits++;lane.cache.splice(at,1);}else{misses++;lane.misses++;if(lane.cache.length===4)lane.cache.shift();}
    lane.cache.push(key);
   }
   lane.prepared=true;
   if(misses){lane.wait=misses*3;continue;}
  }
  lane.sum[i*N+j]+=A[i*N+k]*D[k*N+j];lane.done++;lane.prepared=false;
 }step++;render();}
 function start(){stop();advance();if(!button.disabled)timer=setInterval(advance,25);}
 button.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();button.focus();start();});button.addEventListener('click',e=>{if(e.detail===0)advance();});
 button.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(!e.repeat)start();}});button.addEventListener('keyup',stop);button.addEventListener('blur',stop);
 window.addEventListener('pointerup',stop);window.addEventListener('pointercancel',stop);window.addEventListener('blur',stop);document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
 element.querySelector('.matrix-reset').addEventListener('click',()=>{stop();step=0;lanes[0]=fresh(false);lanes[1]=fresh(true);render();});render();
}
