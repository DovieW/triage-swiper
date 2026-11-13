'use strict';
const $ = id => document.getElementById(id);
let videos = [], decisions = {}, view = 'pending', busy = false, history = [], shuffled = [], currentId = null;
const statusOf = id => decisions[id]?.status || 'pending';
const revisionOf = id => decisions[id]?.revision || 0;
const duration = seconds => {
  if (!Number.isFinite(seconds)) return 'Runtime unknown';
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
};
function totalDuration(items) {
  const unknown = items.filter(v => !Number.isFinite(v.duration_seconds)).length;
  const known = items.reduce((sum, v) => sum + (v.duration_seconds || 0), 0);
  return unknown ? `${known ? duration(known) + ' + ' : ''}${unknown} unknown runtime${unknown === 1 ? '' : 's'}` : duration(known);
}
function element(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) { const err = new Error(data.error || 'Request failed'); err.status = response.status; throw err; }
  return data;
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function matching() {
  const source = $('order').value === 'shuffle' ? shuffled : videos;
  return source.filter(v => (view === 'maybe' ? statusOf(v.id).startsWith('maybe') : statusOf(v.id) === view) &&
    (view !== 'maybe' || !$('maybeLevel').value || statusOf(v.id) === $('maybeLevel').value) &&
    (!$('topic').value || v.category === $('topic').value) &&
    (!$('channel').value || v.channel === $('channel').value) &&
    (!$('duration').value || ($('duration').value === 'unknown' ? !Number.isFinite(v.duration_seconds) : Number.isFinite(v.duration_seconds) && ($('duration').value === 'short' ? v.duration_seconds <= 1800 : v.duration_seconds > 1800))));
}
function render() {
  const selected = videos.filter(v => statusOf(v.id) === 'keep');
  $('keptCount').textContent = selected.length;
  $('headerKeptCount').textContent = selected.length;
  $('keptTime').textContent = `${totalDuration(selected)} selected`;
  $('pendingCount').textContent = videos.filter(v => statusOf(v.id) === 'pending').length;
  document.querySelectorAll('.tab').forEach(el => {
    const active = el.dataset.view === view;
    el.classList.toggle('active', active);
    if (active) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  });
  $('discover').hidden = view !== 'pending'; $('results').hidden = view === 'pending';
  $('maybeFilter').hidden = view !== 'maybe';
  $('undo').disabled = busy || !history.length;
  const matches = matching();
  if (view === 'pending') {
    $('remaining').textContent = `${matches.length} left`;
    $('card').hidden = !matches.length; $('empty').hidden = !!matches.length;
    $('actions').hidden = !matches.length;
    if (matches.length) showCard(matches[0]); else currentId = null;
    showNext(matches[1]);
  } else {
    currentId = null;
    $('listTitle').textContent = {keep: 'Your shortlist', maybe: 'Your maybes', pass: 'Tossed talks'}[view];
    $('listSummary').textContent = `${matches.length} talks · ${totalDuration(matches)} in this view`;
    $('exports').hidden = view !== 'keep';
    $('list').replaceChildren();
    if (!matches.length) $('list').append(element('p', 'No talks here yet. Your next pick is waiting in Discover.', 'list-empty'));
    matches.forEach(v => {
      const row = element('article', undefined, 'list-item');
      const img = element('img'); img.src = `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`; img.alt = ''; img.loading = 'lazy';
      const details = element('div', undefined, 'details');
      const link = element('a', v.title); link.href = v.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      details.append(link, element('p', `${v.channel} · ${duration(v.duration_seconds)} · ${v.category}`));
      const select = element('select'); select.setAttribute('aria-label', `Decision for ${v.title}`);
      [['keep','Keep'],['maybe1','Maybe 1 · Strongest'],['maybe2','Maybe 2 · Undecided'],['maybe3','Maybe 3 · Long shot'],['pass','Toss'],['pending','Review again']].forEach(([value, label]) => select.add(new Option(label, value)));
      select.value = statusOf(v.id); select.disabled = busy;
      select.addEventListener('change', () => decide(v.id, select.value));
      row.append(img, details, select); $('list').append(row);
    });
  }
}
function cardNote(v) {
  const description = typeof v.description === 'string' ? v.description.trim() : '';
  if (description) return {label: 'YouTube description', text: description};
  const reason = typeof v.reason === 'string' ? v.reason.trim() : '';
  if (!reason || reason === 'From your YouTube watch history.') return null;
  return {label: 'Selection note', text: reason};
}
function showNote(v, container, label, text) {
  const note = cardNote(v);
  $(container).hidden = !note;
  $(label).textContent = note?.label || '';
  $(text).textContent = note?.text || '';
}
function showCard(v) {
  if (currentId === v.id) return;
  const changing = currentId !== null;
  currentId = v.id;
  if (changing) {
    card.classList.remove('arriving');
    void card.offsetWidth;
    card.classList.add('arriving');
  }
  $('title').textContent = v.title;
  $('byline').textContent = `${v.channel} · ${duration(v.duration_seconds)}`;
  showNote(v, 'cardNote', 'noteLabel', 'reason');
  $('watch').href = v.url;
  $('chips').textContent = v.category;
  const img = element('img'); img.src = `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`; img.alt = `Thumbnail for ${v.title}`; img.draggable = false; img.decoding = 'async';
  const preview = element('button', 'Play preview', 'preview');
  preview.setAttribute('aria-label', `Play preview: ${v.title}`);
  preview.addEventListener('click', () => {
    const frame = element('iframe'); frame.src = `https://www.youtube-nocookie.com/embed/${v.id}?autoplay=1`;
    frame.title = v.title; frame.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen'; frame.allowFullscreen = true;
    $('player').replaceChildren(frame);
    $('previewDialog').showModal();
  });
  $('media').replaceChildren(img, preview, element('span', duration(v.duration_seconds), 'duration'));
}
let nextId = null;
function showNext(v) {
  $('nextCard').hidden = !v;
  if (!v) {nextId = null; return;}
  if (v.id === nextId) return;
  nextId = v.id;
  const img = element('img');
  img.src = `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`;
  img.alt = ''; img.draggable = false; img.decoding = 'async';
  $('nextMedia').replaceChildren(img);
  $('nextTitle').textContent = v.title;
  $('nextTopic').textContent = v.category;
  $('nextByline').textContent = `${v.channel} · ${duration(v.duration_seconds)}`;
  showNote(v, 'nextNote', 'nextNoteLabel', 'nextNoteText');
}
let feedbackTimer;
function feedback(status) {
  clearTimeout(feedbackTimer);
  $('gestureStatus').textContent = {keep:'Kept', pass:'Tossed', maybe1:'Maybe 1 · Strongest', maybe2:'Maybe 2 · Undecided', maybe3:'Maybe 3 · Long shot', pending:'Restored'}[status];
  feedbackTimer = setTimeout(() => {$('gestureStatus').textContent = '← Toss · Keep →';}, 1800);
}
async function decide(id, status, undo = false) {
  if (busy || !id) return;
  busy = true; error(''); $('saveStatus').textContent = 'Saving…';
  const prior = statusOf(id), revision = revisionOf(id);
  const animation = !undo && view === 'pending' && id === currentId ? exitCard(status) : Promise.resolve();
  document.querySelectorAll('.action').forEach(b => b.disabled = true);
  try {
    const saved = await api('/api/decision', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id, status, revision})});
    await animation;
    decisions[id] = saved;
    if (undo) history.pop(); else history.push({id, prior, savedRevision: decisions[id].revision});
    $('saveStatus').textContent = 'All choices saved';
    feedback(status);
  } catch (err) {
    if (err.status === 409) {
      try { decisions = await api('/api/decisions'); currentId = null; } catch (_) {}
    }
    error(err.message); $('saveStatus').textContent = 'Choice not saved';
  } finally {
    await animation;
    resetCard();
    busy = false;
    document.querySelectorAll('.action').forEach(b => b.disabled = false);
    render();
  }
}
async function undo() {
  if (busy || !history.length) return;
  const last = history.at(-1);
  try {
    decisions = await api('/api/decisions');
    if (revisionOf(last.id) !== last.savedRevision) {
      history.pop(); error('That talk changed on another device. Please edit it in the list.'); render(); return;
    }
    await decide(last.id, last.prior, true);
  } catch (err) { error(`Could not undo: ${err.message}`); }
}
async function refresh() {
  if (busy || pointer || $('tagDialog').open || !videos.length || document.hidden) return;
  try {
    const latest = await api('/api/decisions');
    if (busy || pointer || $('tagDialog').open) return;
    decisions = latest;
    $('saveStatus').textContent = 'All choices saved'; render();
  } catch (_) { $('saveStatus').textContent = 'Offline · reconnect to save'; }
}
$('closePreview').onclick = () => $('previewDialog').close();
$('previewDialog').addEventListener('close', () => $('player').replaceChildren());
for (const dialog of [$('previewDialog'), $('tagDialog')]) {
  dialog.addEventListener('click', e => {
    if (e.target !== dialog) return;
    const r = dialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close();
  });
}
let taggedId = null;
function openTag() {
  if (busy || !currentId) return;
  taggedId = currentId;
  $('tag').setAttribute('aria-expanded', 'true');
  $('tagDialog').showModal();
}
function chooseTag(level) {
  if (!taggedId || busy) return;
  const id = taggedId;
  $('tagDialog').close();
  decide(id, level);
}
$('tag').onclick = openTag;
$('closeTag').onclick = () => $('tagDialog').close();
$('tagDialog').addEventListener('close', () => {
  taggedId = null;
  $('tag').setAttribute('aria-expanded', 'false');
});
document.querySelectorAll('[data-tag]').forEach(button => {
  button.onclick = () => chooseTag(button.dataset.tag);
});
$('toss').onclick = () => decide(currentId, 'pass');
$('keep').onclick = () => decide(currentId, 'keep');
$('undo').onclick = undo;
document.querySelectorAll('.tab').forEach(tab => tab.onclick = () => {if (busy) return; view = tab.dataset.view; currentId = null; render(); if (view === 'pending') window.scrollTo({top:0, behavior:'smooth'});});
['topic','channel','duration','order','maybeLevel'].forEach(id => $(id).onchange = () => {currentId = null; render();});
$('clearFilters').onclick = () => {['topic','channel','duration'].forEach(id => $(id).value = ''); render();};
document.addEventListener('keydown', e => {
  if ($('previewDialog').open) return;
  if ($('tagDialog').open) {
    if (['1','2','3'].includes(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {e.preventDefault(); chooseTag(`maybe${e.key}`);}
    return;
  }
  if (e.target.closest('input,select,textarea,button,a,iframe') || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key.toLowerCase() === 'z') return void undo();
  if (view !== 'pending') return;
  const action = {ArrowLeft:'pass',ArrowRight:'keep','1':'maybe1','2':'maybe2','3':'maybe3',l:'maybe2',L:'maybe2'}[e.key];
  if (action) { e.preventDefault(); decide(currentId, action); }
});
let pointer = null;
const card = $('card');
function resetCard() {
  card.classList.remove('dragging', 'leaving');
  card.style.transform = '';
  card.style.opacity = '';
  card.querySelectorAll('.swipe-stamp').forEach(el => el.style.opacity = '0');
}
function moveCard(dx, dy) {
  card.style.transform = `translate3d(${dx}px,${dy * .08}px,0) rotate(${Math.max(-12, Math.min(12, dx / 22))}deg)`;
  card.querySelector('.stamp-keep').style.opacity = Math.min(1, Math.max(0, dx / 90));
  card.querySelector('.stamp-pass').style.opacity = Math.min(1, Math.max(0, -dx / 90));
}
function exitCard(status) {
  card.classList.remove('dragging', 'arriving');
  card.classList.add('leaving');
  const direction = status === 'pass' ? -1 : 1;
  if (status.startsWith('maybe')) {
    card.style.transform = 'translate3d(0,-28px,0) scale(.96)';
  } else {
    moveCard(direction * (window.innerWidth + card.clientWidth), 0);
  }
  card.style.opacity = '0';
  return new Promise(resolve => setTimeout(resolve, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 240));
}
const gesture = Swipe.attach(card, {
  canStart: e => !busy && !$('tagDialog').open && !e.target.closest('a,button,iframe'),
  onActive: active => {pointer = active;},
  onMove: (dx, dy) => {card.classList.remove('arriving'); card.classList.add('dragging'); moveCard(dx, dy);},
  onRelease: choice => decide(currentId, choice),
  onCancel: resetCard
});
window.addEventListener('blur', () => gesture.cancel());
window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh);
setInterval(refresh, 15000);
async function init() {
  try {
    const [talks, state] = await Promise.all([api('/api/talks'), api('/api/decisions')]);
    videos = talks.videos; decisions = state;
    const channelOrder = [...new Set(videos.map(v => v.channel))];
    videos.sort((a,b) => channelOrder.indexOf(a.channel) - channelOrder.indexOf(b.channel) || (b.published_date || b.watched_at || '').localeCompare(a.published_date || a.watched_at || ''));
    shuffled = [...videos];
    for (let i=shuffled.length-1;i>0;i--) {const j=Math.floor(Math.random()*(i+1));[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]];}
    [...new Set(videos.map(v => v.category))].sort().forEach(x => $('topic').add(new Option(x,x)));
    channelOrder.forEach(x => $('channel').add(new Option(x,x)));
    $('saveStatus').textContent = 'All choices saved'; render();
  } catch (err) { error(`Could not load the library. Reload to retry. ${err.message}`); $('remaining').textContent = 'Unavailable'; $('saveStatus').textContent = 'Connection failed'; }
}
init();
