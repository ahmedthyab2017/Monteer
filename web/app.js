/* مونتير — واجهة الجوال. دار الإبداع للحلول البرمجية */
const $ = s => document.querySelector(s);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const KEY = () => { try { return localStorage.getItem('mk') || ''; } catch { return ''; } };
const setKey = v => { try { v ? localStorage.setItem('mk', v) : localStorage.removeItem('mk'); } catch {} };
const fmt = t => { t = Math.max(0, t || 0); return Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0'); };
const ico = id => `<svg><use href="#${id}"/></svg>`;

const STAGE_LABEL = { queued: 'في الطابور', cut: 'يحذف السكتات', transcribe: 'يكتب الكلام', review: 'بانتظار مراجعتك',
  captions: 'ينتج', zoom: 'ينتج', render: 'ينتج', encode: 'ينتج', done: 'جاهز', error: 'خطأ' };
const STYLES = [
  { k: 'card', n: 'بطاقة', d: '<span class="card-s">كلام <i>مهم</i></span>' },
  { k: 'bar', n: 'شريط', d: '<span class="bar-s">كلام <i>مهم</i></span>' },
  { k: 'underline', n: 'خط سفلي', d: '<span class="under-s">كلام <i>مهم</i></span>' },
  { k: 'shadow', n: 'ظل', d: '<span class="shadow-s">كلام مهم</span>' },
  { k: 'big', n: 'كلمة كبيرة', d: '<span class="big-s">مهم</span>' },
  { k: 'chunk', n: 'مقاطع', d: '<span class="chunk-s">كلام قصير<br>على سطرين</span>' },
];
const PALETTES = [
  { n: 'سوران', bg: '#14213D', acc: '#F2C230' },
  { n: 'فيروزي', bg: '#0F3D3E', acc: '#5ED3B5' },
  { n: 'أحمر', bg: '#1B1B1F', acc: '#E5484D' },
  { n: 'وردي', bg: '#2A1E4A', acc: '#F5B7E0' },
];

let brand = {}, current = null, timer = null, jobData = null, pickedStyle = 'card', delArmed = 0;

function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.remove('hidden'); clearTimeout(e._t); e._t = setTimeout(() => e.classList.add('hidden'), 3500); }
async function api(path, opt = {}) {
  opt.headers = Object.assign({ 'X-Key': KEY() }, opt.headers || {});
  const r = await fetch(path, opt);
  if (r.status === 401) { show('login'); throw new Error('auth'); }
  if (!r.ok) { let m = 'حدث خطأ، حاول مرة ثانية'; try { m = (await r.json()).detail || m; } catch {} toast(m); throw new Error(m); }
  return r.json();
}
const fileUrl = (id, f) => `/api/jobs/${id}/${f}?k=${encodeURIComponent(KEY())}`;

/* ---------- التنقل ---------- */
function show(id) {
  for (const s of ['login', 'home', 'reels', 'job', 'brand']) $('#' + s).classList.toggle('hidden', s !== id);
  $('#tabs').classList.toggle('hidden', id === 'login' || id === 'job');
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.go === id));
  if (id !== 'job') { clearInterval(timer); current = null; const pv = $('#pv'); if (pv) pv.pause(); }
  if (id === 'home') loadHome();
  if (id === 'reels') loadReels();
  if (id === 'brand') loadBrand();
  window.scrollTo(0, 0);
}
document.addEventListener('click', e => { const b = e.target.closest('[data-go]'); if (b) show(b.dataset.go); });

/* ---------- الدخول ---------- */
$('#loginBtn').onclick = async () => {
  const v = $('#pwLogin').value.trim(); if (!v) return toast('اكتب كلمة المرور');
  setKey(v);
  try { await api('/api/ping'); show('home'); } catch { toast('كلمة المرور غير صحيحة'); }
};
$('#pwLogin').onkeydown = e => { if (e.key === 'Enter') $('#loginBtn').click(); };
$('#logout').onclick = () => { setKey(''); show('login'); };

/* ---------- الرئيسية وريلزي ---------- */
async function loadBrandHeader() {
  brand = await api('/api/brand').catch(() => brand);
  $('#brandName').textContent = brand.name || 'مونتير';
  $('#brandLogo').src = brand.hasLogo ? '/api/brand/logo.png?t=' + (brand._t || 1) : 'icon.png';
}
function reelCard(j) {
  const b = el('button', 'reel');
  if (j.stage === 'done') { const im = el('img'); im.loading = 'lazy'; im.src = fileUrl(j.id, 'thumb.jpg'); im.onerror = () => im.remove(); b.appendChild(im); }
  else { const p = el('div', 'placeholder'); p.innerHTML = ico(j.stage === 'review' ? 'i-text' : j.stage === 'error' ? 'i-warn' : 'i-film'); b.appendChild(p); }
  const bd = el('span', 'badge ' + (['review', 'done', 'error'].includes(j.stage) ? j.stage : ''), STAGE_LABEL[j.stage] || j.stage);
  b.appendChild(bd);
  const sh = el('div', 'shade');
  sh.appendChild(el('b', '', (j.name || 'فيديو').replace(/\.[^.]+$/, '')));
  const d = new Date((j.created || 0) * 1000);
  sh.appendChild(el('small', '', d.toLocaleDateString('ar-IQ', { day: 'numeric', month: 'short' }) + (j.duration ? ' · ' + fmt(j.duration) : '')));
  b.appendChild(sh);
  b.onclick = () => openJob(j.id);
  return b;
}
function fillGrid(box, jobs, emptyText) {
  box.innerHTML = '';
  if (!jobs.length) { box.appendChild(el('div', 'empty', emptyText)); return; }
  jobs.forEach(j => box.appendChild(reelCard(j)));
}
async function loadHome() {
  loadBrandHeader();
  const jobs = await api('/api/jobs').catch(() => []);
  fillGrid($('#recent'), jobs.slice(0, 4), 'لا يوجد ريلز بعد — ابدأ بأول فيديو');
}
async function loadReels() {
  const jobs = await api('/api/jobs').catch(() => []);
  fillGrid($('#allReels'), jobs, 'لا يوجد ريلز بعد');
}

/* ---------- الرفع على قطع (بوابة الاستضافة ترفض الطلب الأكبر من ~25 ميغا) ---------- */
function upProg(p, title, sub) {
  $('#upBar').style.width = p + '%'; $('#upPct').textContent = p + '٪';
  if (title) $('#upTitle').textContent = title; if (sub) $('#upSub').textContent = sub;
}
$('#file').onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  $('#upCard').classList.remove('hidden'); $('#heroUpload').classList.add('hidden');
  upProg(0, 'أرفع الفيديو…', 'خلّ الصفحة مفتوحة حتى يكمل الرفع');
  const CH = 8 * 1024 * 1024, n = Math.max(1, Math.ceil(f.size / CH));
  try {
    const { uid } = await api('/api/uploads', { method: 'POST' });
    for (let i = 0; i < n; i++) {
      const blob = f.slice(i * CH, Math.min(f.size, (i + 1) * CH));
      for (let a = 0; ; a++) {
        try {
          await new Promise((ok, bad) => {
            const x = new XMLHttpRequest();
            x.upload.onprogress = ev => upProg(Math.round(100 * (i * CH + ev.loaded) / f.size));
            x.onload = () => x.status === 200 ? ok() : bad(x.status); x.onerror = () => bad(0);
            x.open('PUT', '/api/uploads/' + uid + '/' + i); x.setRequestHeader('X-Key', KEY()); x.send(blob);
          });
          break;
        } catch (st) {
          if (st === 401) throw new Error('كلمة المرور غير صحيحة');
          if (a >= 4) throw new Error('انقطع الاتصال أثناء الرفع، حاول مرة ثانية');
          upProg(Math.round(100 * i * CH / f.size), 'ضعف في النت…', 'أعيد إرسال الجزء ' + (i + 1) + ' تلقائياً');
          await new Promise(r => setTimeout(r, 3000 * (a + 1)));
        }
      }
    }
    const j = await api('/api/uploads/' + uid + '/done', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parts: n, name: f.name }) });
    openJob(j.id);
  } catch (err) { if (err.message !== 'auth') toast(err.message || 'فشل الرفع'); }
  finally { e.target.value = ''; $('#upCard').classList.add('hidden'); $('#heroUpload').classList.remove('hidden'); }
};

/* ---------- المهمة ---------- */
function stepOf(j) {
  if (j.stage === 'done') return 5;
  if (j.stage === 'review') return 3;
  if (['captions', 'zoom', 'render', 'encode'].includes(j.stage) || (j.stage === 'queued' && j.pct >= 32)) return 4;
  return 2;
}
function paintSteps(now, err) {
  document.querySelectorAll('#stepper li').forEach(li => {
    const s = +li.dataset.s; li.className = s < now ? 'ok' : s === now ? (err ? 'on' : 'now') : '';
  });
}
async function openJob(id) {
  current = id; jobData = null; delArmed = 0;
  $('#sents').innerHTML = ''; $('#player').removeAttribute('src'); $('#pv').removeAttribute('src');
  show('job'); current = id;
  await refresh();
  clearInterval(timer); timer = setInterval(refresh, 3000);
}
async function refresh() {
  if (!current) return;
  const j = await api('/api/jobs/' + current).catch(() => null); if (!j || j.id !== current) return;
  jobData = j;
  $('#jobTitle').textContent = (j.name || 'فيديو').replace(/\.[^.]+$/, '');
  const err = j.stage === 'error', now = stepOf(j);
  paintSteps(now, err);
  const working = !err && now !== 3 && now !== 5;
  $('#working').classList.toggle('hidden', !working);
  $('#errBox').classList.toggle('hidden', !err);
  $('#review').classList.toggle('hidden', now !== 3 || err);
  $('#done').classList.toggle('hidden', now !== 5);
  if (working) {
    const p = Math.max(1, Math.min(100, j.pct || 0));
    $('#ringVal').style.strokeDashoffset = 327 * (1 - p / 100); $('#ringPct').textContent = p + '٪';
    $('#jobMsg').textContent = j.msg || '';
  }
  if (err) $('#errMsg').textContent = j.msg || '';
  if (now === 3 && !$('#sents').children.length) renderReview(j);
  if (now === 5 && $('#player').dataset.v !== j.id + j.updated) {
    const u = fileUrl(j.id, 'video') + '&t=' + Math.round(j.updated);
    $('#player').src = u; $('#dl').href = u; $('#player').dataset.v = j.id + j.updated;
    if (j.learned) toast('أضاف القاموس ' + j.learned + ' تصحيحاً جديداً');
  }
  if (now === 3 || now === 5 || err) clearInterval(timer);
}

/* المراجعة: تسمع الجملة، تصحح، تحذف */
let stopAt = null;
const pv = $('#pv');
pv.ontimeupdate = () => { if (stopAt != null && pv.currentTime >= stopAt) { pv.pause(); stopAt = null; document.querySelectorAll('.sent.playing').forEach(x => x.classList.remove('playing')); } };
function playSent(li, s) {
  document.querySelectorAll('.sent.playing').forEach(x => x.classList.remove('playing'));
  li.classList.add('playing');
  pv.currentTime = Math.max(0, s.start - 0.15); stopAt = s.end + 0.25; pv.play().catch(() => {});
}
function renderReview(j) {
  pv.src = fileUrl(j.id, 'preview');
  const ol = $('#sents'); ol.innerHTML = '';
  (j.sentences || []).forEach(s => {
    const li = el('li', 'sent' + (s.drop ? ' dropped' : ''));
    const head = el('div', 'head');
    const play = el('button', 'play'); play.innerHTML = ico('i-play'); play.setAttribute('aria-label', 'اسمع الجملة');
    head.append(play, el('span', 'time', fmt(s.start)), el('span', 'sp'));
    const del = el('button', 'del'); del.innerHTML = ico('i-trash'); del.setAttribute('aria-label', 'احذف الجملة');
    head.appendChild(del); li.appendChild(head);
    if (s.flag) { const f = el('div', 'flag'); f.innerHTML = ico('i-warn'); f.appendChild(el('span', '', s.flag)); li.appendChild(f); }
    const ta = el('textarea'); ta.rows = 1; ta.value = s.text; li.appendChild(ta);
    const fit = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
    ta.oninput = fit; setTimeout(fit);
    play.onclick = () => playSent(li, s);
    ta.onfocus = () => playSent(li, s);
    del.onclick = () => li.classList.toggle('dropped');
    ol.appendChild(li);
  });
  pickedStyle = j.capStyle || brand.capStyle || 'card';
  renderStyles($('#styles'), () => pickedStyle, k => pickedStyle = k);
}
function renderStyles(box, get, set) {
  box.innerHTML = '';
  STYLES.forEach(st => {
    const b = el('button', 'style' + (get() === st.k ? ' on' : ''));
    b.innerHTML = `<div class="demo">${st.d}</div>`; b.appendChild(el('b', '', st.n));
    b.onclick = () => { set(st.k); box.querySelectorAll('.style').forEach(x => x.classList.remove('on')); b.classList.add('on'); };
    box.appendChild(b);
  });
}
$('#produceBtn').onclick = async () => {
  const items = [...$('#sents').children].map(li => ({ text: li.querySelector('textarea').value.trim(), drop: li.classList.contains('dropped') }));
  if (items.every(x => x.drop || !x.text)) return toast('لا يمكن حذف كل الجمل');
  pv.pause();
  $('#produceBtn').disabled = true;
  try {
    await api('/api/jobs/' + current + '/produce', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sentences: items, capStyle: pickedStyle }) });
    $('#sents').innerHTML = ''; await refresh(); clearInterval(timer); timer = setInterval(refresh, 3000);
  } finally { $('#produceBtn').disabled = false; }
};
$('#reBtn').onclick = async () => {
  const j = await api('/api/jobs/' + current);
  $('#done').classList.add('hidden'); $('#review').classList.remove('hidden'); paintSteps(3);
  renderReview(j); window.scrollTo(0, 0);
};
$('#shareBtn').onclick = async () => {
  try {
    toast('أجهّز الفيديو للمشاركة…');
    const blob = await (await fetch($('#player').src)).blob();
    const file = new File([blob], 'reel.mp4', { type: 'video/mp4' });
    if (navigator.canShare && navigator.canShare({ files: [file] })) await navigator.share({ files: [file], title: jobData?.name || 'ريل' });
    else { $('#dl').click(); toast('نزّلته — شاركه من معرض الصور'); }
  } catch (e) { if (e.name !== 'AbortError') toast('تعذّرت المشاركة، استعمل «تنزيل»'); }
};
$('#copyBtn').onclick = async () => {
  const t = (jobData?.sentences || []).filter(s => !s.drop).map(s => s.text).join(' ');
  try { await navigator.clipboard.writeText(t); toast('نُسخ الكلام — الصقه وصفاً للريل'); } catch { toast('تعذّر النسخ'); }
};
$('#delJob').onclick = async () => {
  if (Date.now() - delArmed > 4000) { delArmed = Date.now(); return toast('اضغط الحذف مرة ثانية للتأكيد'); }
  await api('/api/jobs/' + current, { method: 'DELETE' }); toast('حُذف الريل'); show('home');
};

/* ---------- الهوية ---------- */
const F = ['name', 'address', 'phone', 'doctor', 'handle', 'cta'];
let svc = [], dict = {}, pal = {}, brandStyle = 'card';
function renderSvc() {
  const box = $('#chipsSvc'); box.innerHTML = '';
  svc.forEach((s, i) => { const c = el('span', 'chip', s); const x = el('button', '', '×'); x.onclick = () => { svc.splice(i, 1); renderSvc(); }; c.appendChild(x); box.appendChild(c); });
}
function renderDict() {
  const box = $('#dict'); box.innerHTML = '';
  Object.entries(dict).forEach(([a, c]) => {
    const row = el('div', 'chip'); const sp = el('span'); sp.append(el('s', '', a), el('b', 'arrow', '←'), el('em', '', c));
    const x = el('button', '', '×'); x.onclick = () => { delete dict[a]; renderDict(); };
    row.append(sp, x); box.appendChild(row);
  });
  if (!Object.keys(dict).length) box.appendChild(el('div', 'hint', 'القاموس فارغ'));
}
function renderPalettes() {
  const box = $('#palettes'); box.innerHTML = '';
  PALETTES.forEach(p => {
    const b = el('button', 'pal' + (pal.bg?.toLowerCase() === p.bg.toLowerCase() ? ' on' : ''));
    b.innerHTML = `<div class="sw"><i style="background:${p.bg}"></i><i style="background:${p.acc}"></i></div>`; b.appendChild(el('b', '', p.n));
    b.onclick = () => { pal = { bg: p.bg, acc: p.acc }; renderPalettes(); };
    box.appendChild(b);
  });
}
async function loadBrand() {
  brand = await api('/api/brand').catch(() => brand);
  F.forEach(k => $('#b_' + k).value = brand[k] || '');
  svc = [...(brand.chips || [])]; dict = { ...(brand.dictionary || {}) }; pal = { bg: brand.bg || '#14213D', acc: brand.acc || '#F2C230' };
  brandStyle = brand.capStyle || 'card';
  renderSvc(); renderDict(); renderPalettes();
  renderStyles($('#stylesBrand'), () => brandStyle, k => brandStyle = k);
  $('#logoPrev').src = brand.hasLogo ? '/api/brand/logo.png?t=' + Date.now() : 'icon.png';
  api('/api/ping').then(p => $('#engineInfo').textContent = 'الكتابة: ' + (p.engine === 'groq' ? 'Groq' : 'على الخادم')).catch(() => {});
}
$('#svcAdd').onclick = () => { const v = $('#svcNew').value.trim(); if (!v) return; if (svc.length >= 4) return toast('أقصى شيء 4 خدمات'); svc.push(v); $('#svcNew').value = ''; renderSvc(); };
$('#dAdd').onclick = () => { const a = $('#dWrong').value.trim(), c = $('#dRight').value.trim(); if (!a || !c) return toast('اكتب الكلمتين'); dict[a] = c; $('#dWrong').value = $('#dRight').value = ''; renderDict(); };
$('#saveBrand').onclick = async () => {
  const body = { chips: svc, dictionary: dict, bg: pal.bg, acc: pal.acc, capStyle: brandStyle };
  F.forEach(k => body[k] = $('#b_' + k).value.trim());
  brand = await api('/api/brand', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  toast('حُفظت الهوية');
};
$('#logoFile').onchange = async e => {
  const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append('logo', f);
  await api('/api/brand/logo', { method: 'POST', body: fd }); $('#logoPrev').src = '/api/brand/logo.png?t=' + Date.now(); brand._t = Date.now(); toast('تغيّر الشعار');
  e.target.value = '';
};

/* ---------- البدء ---------- */
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
(async () => {
  if (!KEY()) return show('login');
  try { await api('/api/ping'); show('home'); } catch { show('login'); }
})();
