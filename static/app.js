const cards = new Map();
const $ = id => document.getElementById(id);
function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Permintaan gagal (${response.status}). Periksa koneksi / login.`);
  return response.json();
}
function renderCameras(cameras) {
  for (const camera of cameras) {
    let card = cards.get(camera.id);
    if (!card) {
      const root = element('article', undefined, 'camera');
      const title = element('h3', camera.name);
      const image = element('img'); image.alt = `Video ${camera.name}`; image.hidden = true;
      const placeholder = element('div', 'Menunggu video…', 'placeholder');
      const status = element('p'); root.append(title, image, placeholder, status);
      $('cameras').append(root);
      card = {image, status, placeholder, streaming:false}; cards.set(camera.id, card);
    }
    const running = camera.status === 'running';
    if (running && !card.streaming) {
      card.image.src = `/api/cameras/${encodeURIComponent(camera.id)}/stream`;
      card.streaming = true;
    } else if (!running && card.streaming) {
      card.image.removeAttribute('src'); card.streaming = false;
    }
    card.image.hidden = !running; card.placeholder.hidden = running;
    card.placeholder.textContent = camera.error || `Status: ${camera.status}. Untuk video selesai, restart server untuk mengulang.`;
    card.status.textContent = `${camera.status} · Orang: ${camera.people} · Kandidat: ${camera.candidates} · Terkonfirmasi temporal: ${camera.confirmed} · Detik: ${camera.media_seconds}`;
  }
}
const reviews = [['pending','Belum ditinjau'],['confirmed_visual','HP terlihat dekat orang'],['false_positive','Deteksi salah'],['uncertain','Tidak jelas']];
function renderEvents(events) {
  // Keep a focused review dropdown intact while the periodic refresh runs.
  if ($('events').contains(document.activeElement)) return;
  $('events').replaceChildren(); $('count').textContent = `(${events.length})`;
  if (!events.length) {
    const row = element('tr'); const cell = element('td', 'Belum ada kejadian. Kandidat harus melewati ambang durasi.'); cell.colSpan = 8;
    row.append(cell); $('events').append(row);
  }
  for (const event of events) {
    const row = element('tr');
    for (const value of [event.recorded_at, `${event.camera} / ${event.zone}`, event.track,
      `${event.start_seconds.toFixed(1)}–${event.end_seconds.toFixed(1)}`, `${event.duration.toFixed(1)} dtk`, event.status]) {
      row.append(element('td', String(value)));
    }
    const select = element('select'); select.setAttribute('aria-label', `Review kejadian ${event.id}`);
    for (const [value,label] of reviews) { const option = element('option', label); option.value = value; select.append(option); }
    select.value = event.review;
    select.addEventListener('change', async () => {
      select.disabled = true;
      try { await request(`/api/events/${event.id}/review`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:select.value})}); }
      catch (error) { $('error').textContent = error.message; }
      finally { select.disabled = false; }
    });
    const reviewCell = element('td'); reviewCell.append(select); row.append(reviewCell);
    const imageCell = element('td');
    if (event.snapshot) { const link = element('a','Lihat'); link.href = `/api/snapshots/${encodeURIComponent(event.snapshot)}`; link.target = '_blank'; link.rel = 'noopener'; imageCell.append(link); }
    else imageCell.textContent = 'Tidak disimpan';
    row.append(imageCell); $('events').append(row);
  }
}
async function refresh() {
  try {
    const [cameras, events] = await Promise.all([request('/api/cameras'),request('/api/events')]);
    renderCameras(cameras); renderEvents(events); $('error').textContent = '';
  } catch (error) { $('error').textContent = error.message; }
  finally { window.setTimeout(refresh,2000); }
}
refresh();
