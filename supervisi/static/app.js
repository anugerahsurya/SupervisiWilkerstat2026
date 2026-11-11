'use strict';
const $ = id => document.getElementById(id);
const labels = {temuan:'Ada temuan', konfirmasi:'Perlu konfirmasi', sesuai:'Sesuai', tidak_dinilai:'Belum dinilai'};
const fmt = n => Number(n).toLocaleString('id-ID');
const statuses = ['temuan','konfirmasi','tidak_dinilai','sesuai'];
const svgNS = 'http://www.w3.org/2000/svg';
let result = null;
let requestNumber = 0;
const notes = new Map();

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function columnText(tag, value, className) {
  const node = element(tag, null, className);
  const pattern = new RegExp(result.column_pattern, 'g');
  let start = 0;
  for (const match of value.matchAll(pattern)) {
    node.append(value.slice(start, match.index), element('code', match[0]));
    start = match.index + match[0].length;
  }
  node.append(value.slice(start));
  return node;
}
function icon(name, className = '') {
  const node = document.createElementNS(svgNS, 'svg');
  node.setAttribute('class', 'icon ' + className);
  node.setAttribute('aria-hidden','true');
  const use = document.createElementNS(svgNS, 'use');
  use.setAttribute('href', '#i-' + name);
  node.append(use);
  return node;
}
function button(label, handler) {
  const node = element('button',label,'border');
  node.type = 'button';
  node.addEventListener('click',handler);
  return node;
}
function showMessage(id, message, error=false) {
  const target = $(id);
  target.textContent = message;
  target.classList.toggle('error',error);
}
async function checked(response) {
  if (!response.ok) {
    let message = 'Permintaan gagal (' + response.status + ').';
    try {
      const data = await response.json();
      message = data.error || data.detail || message;
    } catch {}
    throw new Error(message);
  }
  return response;
}
const runRoot = () => '/api/runs/' + encodeURIComponent(result.run_id);
const noteKey = id => 'wilkerstat.note.' + result.run_id + '.' + id;
const writes = new Map();
function readNote(id) {
  const key = noteKey(id);
  return notes.get(key) ?? result.notes?.[id] ?? '';
}
function queueNote(id, value, hint) {
  const url = runRoot() + '/notes/' + encodeURIComponent(id);
  const key = noteKey(id);
  notes.set(key,value);
  const state = writes.get(key) || {active:false, timer:null, version:0};
  writes.set(key,state);
  state.value = value;
  state.hint = hint;
  state.version++;
  try { localStorage.setItem(key,value); } catch {}
  if (hint) hint.textContent = 'Menyimpan ke Supabase…';
  clearTimeout(state.timer);
  async function flush() {
    if (state.active) return;
    state.active = true;
    const version = state.version;
    try {
      await checked(await fetch(url,{method:'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({value:state.value})}));
      if (version === state.version) {
        writes.delete(key);
        try { localStorage.removeItem(key); } catch {}
        if (state.hint) state.hint.textContent = 'Tersimpan di Supabase.';
      }
    } catch {
      if (state.hint) state.hint.textContent = 'Belum tersimpan di Supabase. Aplikasi akan mencoba kembali.';
      state.timer = setTimeout(flush,5000);
    } finally {
      state.active = false;
      if (version !== state.version) {
        clearTimeout(state.timer);
        state.timer = setTimeout(flush,0);
      }
    }
  }
  state.timer = setTimeout(flush,350);
}
function loadDrafts() {
  const prefix = noteKey('');
  try {
    for (const key of Object.keys(localStorage)) {
      if (!key.startsWith(prefix)) continue;
      const id = key.slice(prefix.length);
      const value = localStorage.getItem(key);
      if (value !== null && value !== result.notes?.[id]) queueNote(id,value,null);
      else localStorage.removeItem(key);
    }
  } catch {}
}
window.addEventListener('beforeunload',event => {
  if (writes.size) { event.preventDefault(); event.returnValue = ''; }
});
function renderNotes(rule, body) {
  const heading = element('h3');
  const label = element('label','Catatan konsultasi');
  const input = element('textarea',null,'notes');
  input.id = 'note-' + rule.id;
  label.htmlFor = input.id;
  heading.append(label);
  input.value = readNote(rule.id);
  input.placeholder = 'Contoh: bukti yang diminta atau tindak lanjut petugas';
  const hint = element('p','Catatan disimpan di Supabase dan disertakan dalam laporan.','note-status');
  input.addEventListener('input', () => queueNote(rule.id,input.value,hint));
  body.append(heading,input,hint);
}
function makeIssuePanel(rule, body) {
  const count = rule.issue_count ?? rule.issues.length;
  const heading = element('h3','Rincian objek (' + fmt(count) + ')');
  const searchLabel = element('label',null,'search issue-search');
  const input = element('input');
  input.type = 'search';
  input.placeholder = 'Cari ID objek atau keterangan';
  input.setAttribute('aria-label', 'Cari objek dalam ' + rule.title);
  searchLabel.append(icon('search'),input);
  const rows = element('div');
  const nav = element('div',null,'pager');
  const info = element('span',null,'page-info');
  info.setAttribute('role','status');
  const limit = 40;
  let offset = 0;
  let total = count;
  let query = '';
  let serial = 0;
  let timer;
  const previous = button('Sebelumnya',() => load(Math.max(0,offset-limit)));
  const next = button('Berikutnya',() => load(offset+limit));
  nav.append(info,previous,next);
  body.append(heading,searchLabel,rows,nav);
  function draw(items) {
    rows.replaceChildren();
    for (const item of items) {
      const row = element('div',null,'issue-row');
      row.append(element('b',item.object),columnText('span',item.detail));
      rows.append(row);
    }
    info.textContent = total ? fmt(offset+1) + '–' + fmt(offset+items.length) + ' dari ' + fmt(total) : 'Tidak ada objek yang cocok.';
    previous.disabled = offset === 0;
    next.disabled = offset+items.length >= total;
    previous.hidden = next.hidden = total <= limit;
  }
  async function load(target) {
    const revision = ++serial;
    info.textContent = 'Memuat objek…';
    previous.disabled = next.disabled = true;
    try {
      const params = new URLSearchParams({offset:target,limit,q:query});
      const response = await checked(await fetch(runRoot() + '/issues/' + encodeURIComponent(rule.id) + '?' + params));
      const data = await response.json();
      if (revision !== serial || !body.isConnected) return;
      offset = target;
      total = data.total;
      draw(data.issues);
    } catch (error) {
      if (revision !== serial) return;
      info.textContent = error.message;
      rows.replaceChildren(button('Coba lagi',() => load(target)));
      previous.disabled = next.disabled = true;
    }
  }
  input.addEventListener('input',() => {
    query = input.value.trim();
    serial++;
    clearTimeout(timer);
    timer = setTimeout(() => load(0),230);
  });
  draw((rule.issues || []).slice(0,limit));
  if (!rule.issues?.length && count) load(0);
}
function renderRule(rule) {
  const block = element('details',null,'rule');
  const summary = element('summary');
  const title = columnText('span',rule.title,'rule-title');
  title.append(element('span',rule.source,'rule-source'));
  summary.append(title,element('span',labels[rule.status] || rule.status,'badge ' + rule.status),icon('arrow','arrow'));
  block.append(summary);
  block.addEventListener('toggle',() => {
    if (!block.open || block.children.length !== 1) return;
    const body = element('div',null,'rule-body');
    block.append(body);
    body.append(columnText('p',rule.detail));
    if ((rule.issue_count ?? rule.issues?.length ?? 0)>0) makeIssuePanel(rule,body);
    renderNotes(rule,body);
  });
  return block;
}
function filterRules() {
  if (!result) return;
  const search = $('search').value.toLocaleLowerCase('id-ID').trim();
  const status = $('status').value;
  const rules = result.rules.filter(rule =>
    (!status || rule.status === status) &&
    [rule.title,rule.source,rule.detail,rule.id].join(' ').toLocaleLowerCase('id-ID').includes(search)
  ).sort((a,b) => statuses.indexOf(a.status)-statuses.indexOf(b.status));
  $('listed').textContent = fmt(rules.length) + ' dari ' + fmt(result.rules.length) + ' pengujian';
  $('rules').replaceChildren(...(rules.length ? rules.map(renderRule) : [element('p','Tidak ada pengujian yang cocok. Ubah kata pencarian atau filter status.','empty')]));
}
function display(data) {
  if (!Array.isArray(data?.rules)) throw new Error('Hasil pemeriksaan belum tersedia.');
  result = data;
  loadDrafts();
  $('feedback').textContent = '';
  $('results').hidden = false;
  $('search').value = $('status').value = '';
  $('dataset').textContent = [data.files.polygon,data.files.point].join(' · ');
  const metrics = [
    ['Poligon', data.counts.polygon,'poly'],['Titik bangunan',data.counts.point,'pin'],
    ['Pengujian dengan temuan',data.rules.filter(r=>r.status==='temuan').length,'bars'],
    ['Perlu konfirmasi',data.rules.filter(r=>r.status==='konfirmasi').length,'chat']
  ];
  $('metrics').replaceChildren(...metrics.map(([title,value,glyph],i) => {
    const node = element('div',null,'metric' + (i>1?' attention':''));
    node.append(element('span',title),element('b',fmt(value)),icon(glyph));
    return node;
  }));
  $('export-csv').href = runRoot() + '/findings.csv';
  filterRules();
}
function openDialog(id) {
  const dialog = $(id);
  if (dialog.open) return;
  dialog.showModal();
  if (matchMedia('(prefers-reduced-motion: no-preference)').matches && !document.activeElement?.matches(':focus-visible')) {
    dialog.animate([{transform:'scale(.97)',opacity:0},{transform:'scale(1)',opacity:1}],{duration:200,easing:'cubic-bezier(.23,1,.32,1)'});
  }
}
document.querySelectorAll('dialog .close').forEach(node => node.onclick = () => node.closest('dialog').close());
$('open-upload').onclick = () => openDialog('upload-dialog');
$('reference').onclick = () => openDialog('ref-dialog');
$('report').onclick = () => {showMessage('export-message','');renderReportFields();openDialog('report-dialog')};
$('search').oninput = filterRules;
$('status').onchange = filterRules;
$('upload-form').addEventListener('submit',async event => {
  event.preventDefault();
  if ($('run').disabled) return;
  const data = new FormData(event.target);
  const revision = ++requestNumber;
  const message = 'Pemeriksaan sedang berlangsung. Berkas besar memerlukan waktu lebih lama.';
  $('run').disabled = $('polygon').disabled = $('point').disabled = true;
  if (result) $('report').disabled = true;
  showMessage('upload-message',message);
  showMessage('feedback',message);
  try {
    const response = await checked(await fetch('/api/audit',{method:'POST',body:data}));
    const report = await response.json();
    if (revision !== requestNumber) return;
    display(report);
    const url = new URL(location.href);
    url.searchParams.set('run', report.run_id);
    history.replaceState(null, '', url);
    $('upload-dialog').close();
    $('results-heading').scrollIntoView({block:'start'});
    showMessage('upload-message','');
  } catch (error) {
    showMessage('upload-message',error.message,true);
    showMessage('feedback',error.message + (result?' Hasil sebelumnya masih ditampilkan.':''),true);
  } finally {
    $('run').disabled = $('polygon').disabled = $('point').disabled = $('report').disabled = false;
  }
});
const reportGroups = [
  {name:'A. Identitas supervisi', fields:['Satuan kerja target','Tanggal / periode supervisi','Tim supervisor BPS Provinsi','Penanggung jawab kabupaten/kota']},
  ...['Peta Digital & GS','Geotagging & Atribut','Cleaning SBR'].map(name => ({
    name:'D. '+name,
    fields: ['Kendala utama',name==='Cleaning SBR'?'Strategi dan progres':'Potensi risiko timeline','Rekomendasi / rencana tindak lanjut']
  })),
  {name:'E. Komitmen pasca-supervisi',fields:['Komitmen dan pihak yang bertanggung jawab','Target waktu penyelesaian','Pengesahan / catatan supervisor']}
];
const fieldId = (group,field) => 'form-'+group+'-'+field;
function renderReportFields() {
  const parent = $('report-fields');
  parent.replaceChildren();
  $('meta-save').textContent = 'Isian disimpan di Supabase untuk pemeriksaan ini.';
  reportGroups.forEach((group,g) => {
    const details = element('details',null,'form-group');
    details.append(element('summary',group.name));
    group.fields.forEach((name,f) => {
      const id = fieldId(g,f);
      const label = element('label',name);
      const input = element(g===0?'input':'textarea');
      input.id = 'metadata-'+id;
      label.htmlFor = input.id;
      if (g>0) input.rows = 2;
      input.value = readNote(id);
      input.oninput = () => queueNote(id,input.value,document.getElementById("meta-save"));
      details.append(label,input);
    });
    parent.append(details);
  });
}
function insertReportFields(doc) {
  const fragment = doc.createDocumentFragment();
  reportGroups.forEach((group,g) => {
    const values=group.fields.map((field,f)=>[field,readNote(fieldId(g,f)).trim()]);
    if (!values.some(([,value])=>value)) return;
    const section = element('section');
    section.append(element('h2',group.name));
    const list=element('dl');
    for(const [field,value] of values) {
      const item=element('dd',value || 'Belum diisi');
      item.style.whiteSpace='pre-wrap';
      list.append(element('dt',field),item);
    }
    section.append(list);
    if(g===0) doc.querySelector('body > dl')?.after(section);
    else fragment.append(section);
  });
  return fragment;
}
$('export-html').onclick = async () => {
  $('export-html').disabled = true;
  showMessage('export-message','Menyiapkan laporan…');
  try {
    const response = await checked(await fetch(runRoot()+'/report.html'));
    const doc = new DOMParser().parseFromString(await response.text(),'text/html');
    const commitments = insertReportFields(doc);
    const entries = result.rules.map(rule=>[rule.title,readNote(rule.id).trim()]).filter(([,note])=>note);
    if (entries.length) {
      const section = doc.createElement('section');
      section.append(element('h2','Catatan konsultasi'));
      for (const [title,note] of entries) {
        const paragraph = element('p',note);
        paragraph.style.whiteSpace='pre-wrap';
        section.append(element('h3',title),paragraph);
      }
      (doc.querySelector('main') || doc.body).append(section);
    }
    doc.body.append(commitments);
    const url = URL.createObjectURL(new Blob(['<!doctype html>\n',doc.documentElement.outerHTML],{type:'text/html;charset=utf-8'}));
    const link = element('a');
    link.href=url;
    link.download='Laporan supervisi Wilkerstat '+result.run_id+'.html';
    link.click();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    showMessage('export-message','Laporan siap diunduh.');
  } catch(error) {showMessage('export-message',error.message,true)}
  finally {$('export-html').disabled=false}
};
async function initial() {
  const revision=++requestNumber;
  try {
    const run = new URLSearchParams(location.search).get('run');
    const endpoint = run ? '/api/runs/' + encodeURIComponent(run) : '/api/current';
    const response=await checked(await fetch(endpoint));
    const report=await response.json();
    if(revision===requestNumber) display(report);
  } catch(error) {
    if(revision===requestNumber) showMessage('feedback',error.message+' Pilih Periksa GeoJSON untuk memulai pemeriksaan.',true);
  }
}
initial();
