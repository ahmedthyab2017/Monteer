const $ = s => document.querySelector(s);
const KEY = () => { try { return localStorage.getItem('mk') || ''; } catch { return ''; } };
const STAGES = { queued:'في الطابور', cut:'حذف السكتات', transcribe:'كتابة الكلام', review:'بانتظار مراجعتك',
  captions:'الكابشن', zoom:'القص والزوم', render:'الرسم', encode:'التصدير', done:'جاهز', error:'خطأ' };
let current = null, timer = null;

function toast(t){ const el=$('#toast'); el.textContent=t; el.classList.remove('hidden'); clearTimeout(el._t); el._t=setTimeout(()=>el.classList.add('hidden'),3500); }
async function api(path, opt={}){
  opt.headers = Object.assign({'X-Key':KEY()}, opt.headers||{});
  const r = await fetch(path, opt);
  if(r.status===401){ show('settings'); toast('اكتب كلمة مرور التطبيق'); throw new Error('auth'); }
  if(!r.ok){ let m='حدث خطأ'; try{ m=(await r.json()).detail||m; }catch{} toast(m); throw new Error(m); }
  return r.json();
}
function show(id){ for(const s of ['home','job','settings']) $('#'+s).classList.toggle('hidden', s!==id); clearInterval(timer);
  if(id==='home') loadJobs(); if(id==='settings') loadBrand(); }
function setProg(el,p,label){ el.querySelector('div').style.width=(p||0)+'%'; el.querySelector('span').textContent=label??((p||0)+'٪'); }
const fmt = t => { t=Math.max(0,t||0); return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0'); };

/* ---------- الرئيسية ---------- */
async function loadJobs(){
  const jobs = await api('/api/jobs').catch(()=>[]);
  const ul = $('#jobs'); ul.innerHTML='';
  if(!jobs.length){ ul.innerHTML='<li class="hint">لا يوجد ريلز بعد</li>'; return; }
  for(const j of jobs){
    const li=document.createElement('li');
    li.innerHTML=`<span></span><span class="st"></span>`;
    li.children[0].textContent=j.name||j.id; li.children[1].textContent=STAGES[j.stage]||j.stage;
    li.onclick=()=>openJob(j.id); ul.appendChild(li);
  }
}
$('#file').onchange = async e => {
  const f=e.target.files[0]; if(!f) return;
  const pr=$('#upProg'); pr.classList.remove('hidden');
  const CH=8*1024*1024, n=Math.max(1,Math.ceil(f.size/CH));
  try{
    const {uid}=await api('/api/uploads',{method:'POST'});
    for(let i=0;i<n;i++){
      const blob=f.slice(i*CH,Math.min(f.size,(i+1)*CH));
      for(let a=0;;a++){            // كل قطعة تُعاد حتى 5 مرات لو انقطع النت
        try{
          await new Promise((ok,bad)=>{ const x=new XMLHttpRequest();
            x.upload.onprogress=ev=>{ const p=Math.round(100*(i*CH+ev.loaded)/f.size); setProg(pr,p,'أرفع الفيديو… '+p+'٪'); };
            x.onload=()=>x.status===200?ok():bad(x.status); x.onerror=()=>bad(0);
            x.open('PUT','/api/uploads/'+uid+'/'+i); x.setRequestHeader('X-Key',KEY()); x.send(blob); });
          break;
        }catch(st){
          if(st===401){ throw new Error('كلمة المرور غير صحيحة'); }
          if(a>=4) throw new Error('انقطع الاتصال أثناء الرفع، حاول مرة ثانية');
          setProg(pr,Math.round(100*i*CH/f.size),'ضعف في النت… أعيد المحاولة'); await new Promise(r=>setTimeout(r,3000*(a+1)));
        }
      }
    }
    const j=await api('/api/uploads/'+uid+'/done',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parts:n,name:f.name})});
    pr.classList.add('hidden'); e.target.value=''; openJob(j.id);
  }catch(err){ pr.classList.add('hidden'); e.target.value=''; toast(err.message||'فشل الرفع'); }
};

/* ---------- المهمة ---------- */
async function openJob(id){ current=id; show('job'); await refresh(true); timer=setInterval(()=>refresh(false),3000); }
async function refresh(first){
  const j = await api('/api/jobs/'+current).catch(()=>null); if(!j) return;
  $('#jobTitle').textContent = j.name || j.id;
  setProg($('#jobProg'), j.pct); $('#jobMsg').textContent = j.msg || '';
  const isReview = j.stage==='review', isDone = j.stage==='done';
  $('#review').classList.toggle('hidden', !isReview);
  $('#done').classList.toggle('hidden', !isDone);
  $('#jobProg').classList.toggle('hidden', isDone || isReview);
  if(isReview && (first || !$('#sents').children.length)) renderSents(j.sentences||[]);
  if(isDone && $('#player').dataset.id!==j.id+j.updated){
    const u='/api/jobs/'+j.id+'/video?k='+encodeURIComponent(KEY())+'&t='+Math.round(j.updated);
    $('#player').src=u; $('#dl').href=u; $('#player').dataset.id=j.id+j.updated;
    if(j.learned) toast('تعلّم القاموس '+j.learned+' تصحيحاً جديداً');
  }
  if(isDone || isReview || j.stage==='error') clearInterval(timer);
}
function renderSents(list){
  const ol=$('#sents'); ol.innerHTML='';
  list.forEach((s,i)=>{
    const li=document.createElement('li'); li.className=s.drop?'dropped':'';
    li.innerHTML=`<div class="top"><span>${i+1} · ${fmt(s.start)}</span><button class="drop" type="button"></button></div><textarea rows="2"></textarea><div class="flag"></div>`;
    const ta=li.querySelector('textarea'); ta.value=s.text;
    const auto=()=>{ ta.style.height='auto'; ta.style.height=ta.scrollHeight+'px'; }; ta.oninput=auto; setTimeout(auto);
    li.querySelector('.flag').textContent=s.flag||'';
    const b=li.querySelector('.drop'); const lab=()=>b.textContent=li.classList.contains('dropped')?'أرجعها':'احذف'; lab();
    b.onclick=()=>{ li.classList.toggle('dropped'); lab(); };
    ol.appendChild(li);
  });
}
$('#produceBtn').onclick = async () => {
  const items=[...$('#sents').children].map(li=>({text:li.querySelector('textarea').value.trim(), drop:li.classList.contains('dropped')}));
  if(items.every(x=>x.drop||!x.text)) return toast('لا يمكن حذف كل الجمل');
  await api('/api/jobs/'+current+'/produce',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sentences:items})});
  $('#sents').innerHTML=''; await refresh(false); clearInterval(timer); timer=setInterval(()=>refresh(false),3000);
};
$('#reBtn').onclick = async () => {
  const j = await api('/api/jobs/'+current);
  $('#done').classList.add('hidden'); $('#review').classList.remove('hidden'); renderSents(j.sentences||[]);
};

/* ---------- الإعدادات ---------- */
const F=['name','address','phone','doctor','handle','cta'];
async function loadBrand(){
  $('#pw').value=KEY();
  const b = await api('/api/brand').catch(()=>null); if(!b) return;
  F.forEach(k=>$('#b_'+k).value=b[k]||'');
  $('#b_chips').value=(b.chips||[]).join('، ');
  $('#b_hot').value=(b.hot||[]).join('، ');
  $('#b_bg').value=b.bg||'#14213D'; $('#b_acc').value=b.acc||'#F2C230';
  $('#b_dict').value=Object.entries(b.dictionary||{}).map(([a,c])=>a+' = '+c).join('\n');
  $('#logoPrev').src=b.hasLogo?'/api/brand/logo.png?t='+Date.now():'';
  api('/api/ping').then(p=>$('#engineInfo').textContent='محرّك الكتابة: '+(p.engine==='groq'?'Groq · Whisper large-v3':'محلي على الخادم')).catch(()=>{});
}
const list = v => v.split(/[،,]/).map(x=>x.trim()).filter(Boolean);
$('#saveBrand').onclick = async () => {
  const dict={}; $('#b_dict').value.split('\n').forEach(l=>{ const [a,c]=l.split('='); if(a&&c&&a.trim()&&c.trim()) dict[a.trim()]=c.trim(); });
  const body={chips:list($('#b_chips').value), hot:list($('#b_hot').value), bg:$('#b_bg').value, acc:$('#b_acc').value, dictionary:dict};
  F.forEach(k=>body[k]=$('#b_'+k).value.trim());
  await api('/api/brand',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  toast('تم الحفظ');
};
$('#pw').onchange = e => { try{ localStorage.setItem('mk', e.target.value); }catch{} toast('تم حفظ كلمة المرور على هذا الجهاز'); loadBrand(); };
$('#logoFile').onchange = async e => {
  const f=e.target.files[0]; if(!f) return; const fd=new FormData(); fd.append('logo',f);
  await api('/api/brand/logo',{method:'POST',body:fd}); $('#logoPrev').src='/api/brand/logo.png?t='+Date.now(); toast('تم تحديث الشعار');
};

$('#homeBtn').onclick=()=>show('home'); $('#setBtn').onclick=()=>show('settings');
if('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(()=>{});
show('home');
