/* Life Skill Manager - Aion 2 — dependency-free JavaScript SPA (Chart.js from a CDN; own icons in iconos.js,
   translations in i18n.js). Theme: the faction of the active profile's server (Asmodian → Night Forge,
   Elyos → Bright Atelier), unless one is forced in Settings. */
'use strict';

// ------------------------------------------------------------------ utilities
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
// useGrouping 'always': without it, es-ES prints 2449 with no thousands separator
let NF, NF1, NF2;
function crearFormatos() {
  NF = new Intl.NumberFormat(LOCALE(), { maximumFractionDigits: 0, useGrouping: 'always' });
  NF1 = new Intl.NumberFormat(LOCALE(), { maximumFractionDigits: 1, useGrouping: 'always' });
  NF2 = new Intl.NumberFormat(LOCALE(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
crearFormatos();
/* old-price and no-history warnings (raw Spanish from the API): the read banner and "Watch out" already sum them up */
const avisoRepetido = a => /antiguo|hist[oó]rico insuficiente/i.test(a || '');
const vale = v => v != null && isFinite(v);
const kin = v => vale(v) ? NF.format(Math.round(v)) : '—';
const num1 = v => vale(v) ? NF1.format(v) : '—';
const pct = v => vale(v) ? NF1.format(v * 100) + ' %' : '—';
const pct0 = v => vale(v) ? NF.format(v * 100) + ' %' : '—';
/* big numbers in short form: 3,79 M · 908 k · 12.857 */
function corto(v) {
  if (!vale(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e6) return NF2.format(v / 1e6) + ' M';
  if (a >= 1e5) return NF.format(Math.round(v / 1e3)) + ' k';
  return kin(v);
}
const conSigno = (v, f = kin) => !vale(v) ? '—' : (v > 0 ? '+' : '') + f(v);
const claseSigno = v => !vale(v) ? '' : v >= 0 ? 'gain' : 'loss';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function hace(h) {
  if (h == null) return t('sin datos');
  if (h < 1) return t('hace {n} min', { n: Math.max(1, Math.round(h * 60)) });
  if (h < 48) return t('hace {n} h', { n: Math.round(h) });
  return t('hace {n} d', { n: Math.round(h / 24) });
}
function haceLargo(h) {
  if (h == null) return t('sin fecha');
  if (h < 1) return t('hace {n} min', { n: Math.max(1, Math.round(h * 60)) });
  if (h < 48) return t('hace {n} h', { n: Math.round(h) });
  return t('hace {n} días', { n: Math.round(h / 24) });
}
function fecha(isoTxt) {
  if (!isoTxt) return '—';
  return new Date(isoTxt).toLocaleString(LOCALE(), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
const semaforoDe = h => h == null ? '' : h <= 6 ? 'verde' : h <= 24 ? 'ambar' : 'rojo';
const CHIP_SEMAFORO = { verde: 'chip-gain', ambar: 'chip-warn', rojo: 'chip-danger' };
const chipEdad = (s, h) => `<span class="chip ${CHIP_SEMAFORO[s] || ''}">${esc(hace(h))}</span>`;
const ESTADOS = { normal: 'normal', hundido: 'precio hundido', saturado: 'saturado', sin_datos: 'sin histórico' };
const nombreEstado = e => t(ESTADOS[e] || e || '');
const CHIP_ESTADO = { normal: 'chip-gain', hundido: 'chip-danger', saturado: 'chip-warn' };
const nombreFaccion = f => f === 'elyos' ? 'Elyos' : 'Asmodian';
/* source of a market read or an NPC price: database keys shown as words */
const FUENTES = { grabacion: 'grabación', video: 'vídeo', captura: 'captura', manual: 'manual', excel: 'excel', 'catálogo': 'catálogo' };
const nombreFuente = k => t(FUENTES[k] || k || '');

function guardarLocal(clave, valor) { try { localStorage.setItem('aion2.' + clave, JSON.stringify(valor)); } catch (_) { } }
function leerLocal(clave, defecto) { try { const v = localStorage.getItem('aion2.' + clave); return v == null ? defecto : JSON.parse(v); } catch (_) { return defecto; } }

function toast(msg, tipo = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + tipo;
  t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), tipo === 'error' ? 8000 : 4000);
}

async function api(ruta, { method = 'GET', body, cuerpoCrudo, silencioso = false } = {}) {
  const opts = { method, headers: {} };
  if (cuerpoCrudo !== undefined) { opts.body = cuerpoCrudo; opts.headers['Content-Type'] = 'application/octet-stream'; }
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  let r;
  try { r = await fetch(ruta, opts); }
  catch (e) { const err = new Error(t('No hay conexión con la app local. ¿Sigue abierta la ventana de iniciar.bat?')); if (!silencioso) toast(err.message, 'error'); throw err; }
  const tipo = r.headers.get('content-type') || '';
  const datos = tipo.includes('json') ? await r.json() : await r.blob();
  if (!r.ok) {
    let msg = (datos && datos.detail) || t('Error {n}', { n: r.status });
    if (Array.isArray(msg)) msg = msg.map(d => d.msg).join('; ');
    msg = tApi(String(msg));
    const err = new Error(msg); err.status = r.status; err.datos = datos;
    if (!silencioso) toast(msg, 'error');
    throw err;
  }
  return datos;
}
const qs = o => Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

function avisoHTML(msg, tipo = '') {
  const ic = tipo === 'error' ? iconoUI('alerta', 18) : '';
  return `<div class="aviso ${tipo}">${ic}<span>${msg}</span></div>`;
}
const vacio = (colspan, msg) => `<tr><td colspan="${colspan}" class="vacio">${msg}</td></tr>`;
async function copiar(texto, campo) {
  try { await navigator.clipboard.writeText(texto); }
  catch (_) { if (campo) { campo.select(); document.execCommand('copy'); } }
  toast(t('Lista copiada al portapapeles.'), 'ok');
}

// ------------------------------------------------------------------ icons and object names
const ICONOS = { cat: {}, of: {}, nombres: {}, porNombre: new Map(), descarga: null, usarOficiales: leerLocal('iconosOficiales', true) };
async function cargarIconos() {
  try {
    const r = await api('/api/catalogo/iconos', { silencioso: true });
    ICONOS.cat = r.categorias || {}; ICONOS.of = r.oficiales || {}; ICONOS.descarga = r.descarga || null;
    if (r.nombres) {
      ICONOS.nombres = r.nombres;
      ICONOS.porNombre = new Map(Object.entries(r.nombres).filter(([, n]) => n && n[0]).map(([id, n]) => [n[0], id]));
    }
  } catch (_) { /* no catalog: everything uses the generic icon */ }
}
/* object name in the current language: EN uses nombre_en and falls back to the Spanish name */
function nom(oid, es) {
  const n = ICONOS.nombres[oid];
  if (IDIOMA === 'en' && n && n[1]) return n[1];
  return es || (n && n[0]) || (oid != null ? `#${oid}` : '');
}
/* same, starting from the Spanish name (API messages and lists that carry no id) */
const nomTxt = es => { const id = ICONOS.porNombre.get(es); return id != null ? nom(id, es) : es; };
traducirNombre = nomTxt;
const avisoTxt = a => tApi(a);
function iconoCat(cat, tam = '') {
  const c = ICONOS_CATEGORIA[cat] ? cat : 'otro';
  return `<span class="ic ${tam}" data-cat="${c}">${svgIcono(ICONOS_CATEGORIA[c])}</span>`;
}
function icono(oid, tam = '') {
  const cat = ICONOS.cat[oid] || 'otro', of = ICONOS.usarOficiales ? ICONOS.of[oid] : null;
  if (!of) return iconoCat(cat, tam);
  return `<span class="ic ${tam}" data-cat="${cat}"><img src="/api/iconos/${encodeURIComponent(of)}" alt="" loading="lazy"></span>`;
}
/* object: icon + name (already escaped HTML) + optional detail */
function objHTML(oid, nombreHTML, detHTML = '', tam = '') {
  return `<div class="obj">${icono(oid, tam)}<div class="obj-texto"><span class="obj-nombre">${nombreHTML}</span>${detHTML ? `<span class="obj-det">${detHTML}</span>` : ''}</div></div>`;
}
function pintarIconosUI(raiz = document) {
  $$('[data-icono]', raiz).forEach(el => { if (!el.firstElementChild) el.innerHTML = iconoUI(el.dataset.icono); });
}

// catalog autocomplete
function autocompletar(input, alElegir) {
  const cont = input.closest('.ac') || input.parentElement;
  let lista = null, items = [], act = -1;
  const buscar = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) return cerrar();
    try { items = await api('/api/catalogo/buscar?' + qs({ q, limite: 12 }), { silencioso: true }); } catch (_) { items = []; }
    pintar();
  }, 180);
  function pintar() {
    cerrar();
    if (!items.length || document.activeElement !== input) return;
    lista = document.createElement('div');
    lista.className = 'ac-lista';
    lista.setAttribute('role', 'listbox');
    const otro = it => IDIOMA === 'en' ? (it.nombre_en ? it.nombre : '') : (it.nombre_en || '');
    lista.innerHTML = items.map((it, i) => `<button type="button" data-i="${i}" role="option">${icono(it.id)}<span class="obj-texto"><span class="obj-nombre">${esc(nom(it.id, it.nombre))}</span><span class="obj-det">${esc(otro(it))}${it.vinculado ? ' · ' + t('vinculado') : ''}</span></span></button>`).join('');
    lista.addEventListener('mousedown', e => { const b = e.target.closest('button[data-i]'); if (b) { e.preventDefault(); elegir(+b.dataset.i); } });
    cont.appendChild(lista);
    act = -1;
  }
  function marcar() { $$('button', lista).forEach((d, i) => d.classList.toggle('sel', i === act)); }
  function elegir(i) { const it = items[i]; if (!it) return; input.value = nom(it.id, it.nombre); input.dataset.id = it.id; cerrar(); alElegir && alElegir(it); }
  function cerrar() { if (lista) lista.remove(); lista = null; }
  input.addEventListener('input', () => { delete input.dataset.id; buscar(); });
  input.addEventListener('keydown', e => {
    if (!lista) return;
    if (e.key === 'ArrowDown') { act = Math.min(act + 1, items.length - 1); marcar(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { act = Math.max(act - 1, 0); marcar(); e.preventDefault(); }
    else if (e.key === 'Enter') { elegir(act < 0 ? 0 : act); e.preventDefault(); }
    else if (e.key === 'Escape') cerrar();
  });
  input.addEventListener('blur', () => setTimeout(cerrar, 150));
}

// side drawer (details and shopping list)
function cerrarCajon() { $('#cajon-raiz').innerHTML = ''; document.body.style.overflow = ''; }
function abrirCajon(cabHTML, cuerpoHTML) {
  const raiz = $('#cajon-raiz');
  raiz.innerHTML = `<div class="cajon-fondo" data-cerrar></div>
    <aside class="cajon" role="dialog" aria-modal="true" tabindex="-1">
      <div class="cajon-cab"><div style="min-width:0">${cabHTML}</div><button class="btn btn-s btn-icono" data-cerrar aria-label="${t('Cerrar')}">${iconoUI('cerrar', 18)}</button></div>
      <div class="cajon-cuerpo pila-grande">${cuerpoHTML}</div>
    </aside>`;
  document.body.style.overflow = 'hidden';
  $('.cajon', raiz).focus();
  return { cuerpo: $('.cajon-cuerpo', raiz), cab: $('.cajon-cab > div', raiz) };
}
$('#cajon-raiz').addEventListener('click', e => { if (e.target.closest('[data-cerrar]')) cerrarCajon(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#cajon-raiz').firstElementChild) cerrarCajon(); });

// ------------------------------------------------------------------ global state
const E = {
  perfiles: [], servidores: [], perfil: null, profesiones: {
    herreria: 'Herrería', armadura: 'Armadura', orfebreria: 'Orfebrería', alquimia: 'Alquimia', cocina: 'Cocina'
  },
  estado: null, ajustes: null, tab: 'panel', grafico: null, ultimoHist: null, objMercado: null, recetaSel: null,
  sesionSel: null, pollCaptura: null, pollIconos: null, ultimasMercado: [], rProf: leerLocal('rProf', ''),
};
const perfilActual = () => E.perfiles.find(p => p.id === E.perfil) || null;
const servidorActual = () => (perfilActual() || {}).servidor || null;
const nombreProf = k => (IDIOMA === 'en' && PROFESIONES_EN[k]) || E.profesiones[k] || k || '';

// theme by faction (or forced in Settings)
function temaDeseado() {
  const forzado = leerLocal('tema', 'auto');
  if (forzado === 'elyos' || forzado === 'asmodian') return forzado;
  const s = servidorActual();
  return s && s.faccion === 'elyos' ? 'elyos' : 'asmodian';
}
function aplicarTema() {
  const t = temaDeseado(), raiz = document.documentElement, cambio = raiz.dataset.tema !== t;
  raiz.dataset.tema = t;
  guardarLocal('temaActual', t);
  const s = servidorActual(), f = $('#faccion');
  f.hidden = !s;
  if (s) f.textContent = nombreFaccion(s.faccion);
  $$('[data-tema-boton]').forEach(b => b.classList.toggle('activo', b.dataset.temaBoton === t));
  if (cambio && E.grafico && E.ultimoHist && $('#m-grafico')) pintarGrafico(E.ultimoHist);
}

async function cargarEstado() {
  try { E.estado = await api('/api/estado', { silencioso: true }); }
  catch (_) { const el = $('#estado-bd'); el.className = 'estado-bd mal'; el.title = t('Sin conexión con la app local'); return; }
  const s = E.estado, el = $('#estado-bd');
  const bd = s.backend === 'supabase' ? 'Supabase' : s.backend === 'local' ? t('Local (SQLite)') : t('sin base de datos');
  el.className = 'estado-bd ' + (!s.backend ? 'mal' : s.en_cola ? 'cola' : 'ok');
  el.title = t('Base de datos: {bd}', { bd }) + (s.en_cola ? t(' · {n} en cola', { n: s.en_cola }) : '');
  const c = s.componentes || {}, avisos = [];
  for (const k of ['catalogo', 'repo', 'motor']) if (c[k] && !c[k].ok) avisos.push(esc(tApi(c[k].mensaje || k)));
  if (s.catalogo && s.catalogo.aviso) avisos.push(esc(tApi(s.catalogo.aviso)));
  $('#avisos-globales').innerHTML = avisos.map(a => avisoHTML(a, 'error')).join('');
  $('#avisos-globales').hidden = !avisos.length;
  if (s.catalogo) {
    try { const info = await api('/api/catalogo', { silencioso: true }); if (info.profesiones) E.profesiones = info.profesiones; } catch (_) { }
  }
}

async function cargarPerfiles() {
  try {
    [E.perfiles, E.servidores] = await Promise.all([api('/api/perfiles', { silencioso: true }), api('/api/servidores', { silencioso: true })]);
  } catch (e) { E.perfiles = []; E.servidores = []; }
  const guardado = leerLocal('perfil', null);
  if (!E.perfiles.some(p => p.id === E.perfil)) E.perfil = E.perfiles.some(p => p.id === guardado) ? guardado : (E.perfiles[0] || {}).id || null;
  const sel = $('#sel-perfil');
  sel.innerHTML = E.perfiles.length ? E.perfiles.map(p => `<option value="${esc(p.id)}">${esc(p.nombre)}${p.servidor ? ` · ${esc(p.servidor.nombre)}` : t(' · sin servidor')}</option>`).join('')
    : `<option value="">${t('Crea un perfil')}</option>`;
  sel.value = E.perfil || '';
  aplicarTema();
}

function llenarProfesiones() {
  const el = $('#f-prof'), v = el.value;
  el.innerHTML = `<option value="">${t('Todas las profesiones')}</option>` + Object.keys(E.profesiones).map(k => `<option value="${k}">${esc(nombreProf(k))}</option>`).join('');
  el.value = v;
  $('#r-profs').innerHTML = `<button class="btn btn-s btn-chip" data-prof="">${t('Todas')}</button>` + Object.keys(E.profesiones)
    .map(k => `<button class="btn btn-s btn-chip" data-prof="${k}">${iconoCat(ICONO_PROFESION[k], 'ic-s')}${esc(nombreProf(k))}</button>`).join('');
  marcarProfReceta();
}
function marcarProfReceta() { $$('#r-profs [data-prof]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.prof === E.rProf))); }

// ------------------------------------------------------------------ language
/* static HTML texts and attributes, captured once in Spanish so they can be swapped back and forth */
const ESTATICOS = { textos: [], attrs: [] };
function capturarEstaticos() {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const s = n.nodeValue.trim();
    if (s && EN[s] != null) ESTATICOS.textos.push([n, n.nodeValue, s]);
  }
  $$('[placeholder],[title],[aria-label]').forEach(el => ['placeholder', 'title', 'aria-label'].forEach(a => {
    const v = el.getAttribute(a);
    if (v && EN[v] != null) ESTATICOS.attrs.push([el, a, v]);
  }));
}
function pintarEstaticos() {
  ESTATICOS.textos.forEach(([n, original, s]) => { n.nodeValue = original.replace(s, t(s)); });
  ESTATICOS.attrs.forEach(([el, a, v]) => el.setAttribute(a, t(v)));
}
function marcarIdioma() {
  document.documentElement.lang = IDIOMA;
  $$('[data-idioma]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.idioma === IDIOMA)));
  if ($('#a-idioma')) $('#a-idioma').value = IDIOMA;
}
function cambiarIdioma(v) {
  if (!IDIOMAS.includes(v) || v === IDIOMA) return;
  IDIOMA = v;
  guardarLocal('idioma', v);
  crearFormatos();
  pintarEstaticos();
  marcarIdioma();
  llenarProfesiones();
  cargarEstado();
  cargarPerfiles().then(() => CARGADORES[E.tab]());
  if ($('#cajon-raiz').firstElementChild) cerrarCajon();
}

// ------------------------------------------------------------------ tabs
const CARGADORES = {
  panel: () => cargarPanel(), mercado: () => cargarMercado(), captura: () => cargarCaptura(),
  recetas: () => cargarRecetas(), personaje: () => cargarPersonaje(), ajustes: () => cargarAjustes(),
};
function irA(tab) {
  if (!CARGADORES[tab]) tab = 'panel';
  const cambia = E.tab !== tab;
  E.tab = tab;
  $$('#nav button').forEach(b => { if (b.dataset.tab === tab) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
  $$('main > section.pantalla').forEach(s => { s.hidden = s.id !== 'tab-' + tab; });
  if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
  if (tab !== 'captura') pararPoll();
  cerrarCajon();
  if (cambia) window.scrollTo(0, 0);
  CARGADORES[tab]();
}

// ================================================================== PANEL
let filasPanel = [], panelVer = 8, turnoPanel = 0;
function leerFiltrosPanel() {
  return {
    profesion: $('#f-prof').value || undefined,
    inversion_max: $('#f-inv').value || undefined,
    margen_min: $('#f-margen').value || undefined,
    incluir_intermedios: $('#f-inter').checked,
    usar_inventario: $('#f-usarinv').checked,
  };
}
async function cargarPanel() {
  const turno = ++turnoPanel;
  const filtros = leerFiltrosPanel();
  guardarLocal('filtros', filtros);
  $('#panel-tabla').classList.add('cargando');
  let r;
  try { r = await api('/api/oportunidades?' + qs({ perfil_id: E.perfil, ...filtros, limite: 60 }), { silencioso: true }); }
  catch (e) {
    if (turno !== turnoPanel) return;
    filasPanel = [];
    pintarPlan(null, { avisos: [e.message], traducidos: true });
    $('#panel-tabla').innerHTML = '';
    $('#panel-tabla').classList.remove('cargando');
    $('#panel-ojo').innerHTML = avisoHTML(esc(e.message), 'error');
    return;
  }
  if (turno !== turnoPanel) return;
  filasPanel = r.filas || [];
  panelVer = 8;
  $('#panel-tabla').classList.remove('cargando');
  const mejor = filasPanel.length && vale(filasPanel[0].beneficio_total) && filasPanel[0].beneficio_total > 0 ? filasPanel[0] : null;
  pintarPlan(mejor, r);
  pintarJugadas(mejor ? 1 : 0);
  pintarOjo(r, turno);
}

function pintarLectura(f, r) {
  const h = f ? f.antiguedad_precios_horas : null;
  const sem = f ? f.semaforo : null;
  const fresca = sem === 'verde';
  let titulo, det;
  if (!f && !(r && r.n_precios)) { titulo = t('Aún no hay precios'); det = t('Lee el mercado para empezar a calcular'); }
  else if (h == null) { titulo = t('Precios sin fecha'); det = t('Haz una lectura antes de comprar'); }
  else { titulo = t('Precios de {h}', { h: haceLargo(h) }); det = fresca ? t('Recién leídos: puedes comprar con confianza') : t('Haz una lectura antes de comprar'); }
  $('#panel-lectura').innerHTML = `<div class="lectura ${fresca ? 'fresca' : ''}">${iconoUI('reloj')}<div class="lectura-texto"><div class="lectura-titulo">${titulo}</div><div class="lectura-det">${det}</div></div><button class="btn" data-ir="captura">${t('Leer mercado')}</button></div>`;
}

function pintarPlan(f, r) {
  const plan = $('#panel-plan');
  pintarLectura(f, r);
  const p = perfilActual();
  if (!f) {
    const avisos = ((r && r.avisos) || []).map(a => (r.traducidos ? a : tApi(a)));
    $('#panel-eyebrow').textContent = t('Tu plan de hoy');
    $('#panel-titular').innerHTML = avisos.length ? t('Prepara tu <span class="resalte">primer plan</span>') : t('Nada rentable <span class="resalte">con estos filtros</span>');
    $('#panel-sub').textContent = avisos[0] || t('Prueba a quitar filtros, subir tus niveles en Personaje o leer más precios del mercado.');
    plan.hidden = true; plan.innerHTML = '';
    return;
  }
  const e = f.escenario_objetivo;
  const usaObjetivo = !!(e && e.precio_objetivo != null && e.estado !== 'sin_datos');
  const precio = usaObjetivo ? e.precio_objetivo : f.precio_venta;
  const ganancia = usaObjetivo && vale(e.beneficio_total) ? e.beneficio_total : f.beneficio_total;
  const n = f.intentos_recomendados || 1;
  const unidades = vale(f.items_esperados) ? f.items_esperados * n : null;

  const nombre = nom(f.producto, f.nombre);
  $('#panel-eyebrow').textContent = t('Tu plan de hoy · 3 pasos');
  $('#panel-titular').innerHTML = t('Fabrica<br><span class="resalte">{nombre}</span><br>y gana ~{g}', { nombre: esc(nombre), g: corto(ganancia) });
  $('#panel-sub').textContent = `${p ? p.nombre + (p.servidor ? ' · ' + p.servidor.nombre : '') + ' · ' : ''}` + t('{n} intentos · inviertes {inv} · margen {m}', { n, inv: corto(f.inversion), m: pct0(f.margen) });

  const notas = [];
  (f.avisos || []).filter(a => !avisoRepetido(a)).forEach(a => notas.push(`<div class="nota">${iconoUI('alerta')}<span>${esc(avisoTxt(a))}</span></div>`));
  if (e && e.estado && e.estado !== 'normal' && e.estado !== 'sin_datos') notas.push(`<div class="nota mala">${iconoUI('alerta')}<span>${t('Mercado {estado}', { estado: esc(nombreEstado(e.estado)) })}${e.aviso ? ': ' + esc(avisoTxt(e.aviso)) : ''}</span></div>`);
  else if (e && e.aviso && !avisoRepetido(e.aviso)) notas.push(`<div class="nota">${iconoUI('alerta')}<span>${esc(avisoTxt(e.aviso))}</span></div>`);

  plan.hidden = false;
  plan.innerHTML = `
    <div class="paso" id="paso-compra"><div class="paso-cab"><span class="paso-n">1</span><span class="paso-titulo">${t('Compra')}</span><span class="paso-meta num" id="paso-compra-meta">…</span></div>
      <div class="paso-lista" id="paso-compra-lista"><div class="paso-item dim">${t('Calculando la lista…')}</div></div>
      <div class="paso-pie"><button class="btn btn-s" id="paso-copiar" disabled>${iconoUI('copiar', 18)} ${t('Copiar lista')}</button><button class="btn btn-t" id="paso-lista">${t('Ver lista')}</button><span class="mas">${t('para {n} intentos', { n })}</span></div></div>
    <div class="paso"><div class="paso-cab"><span class="paso-n">2</span><span class="paso-titulo">${t('Fabrica')}</span><span class="paso-meta">${esc(nombreProf(f.profesion))} · ${t('nv. {n}', { n: f.nivel_receta ?? '—' })}</span></div>
      <div class="paso-item">${objHTML(f.producto, esc(nombre), t('{n} intentos · éxito {p}', { n, p: pct0(f.p_exito) }))}</div>
      <div class="chips"><span class="chip chip-gain num">${t('{v} / intento', { v: conSigno(f.beneficio_intento) })}</span><span class="chip num">${t('margen {m}', { m: pct0(f.margen) })}</span>${f.p_combo ? `<span class="chip num">${t('combo {p}', { p: pct0(f.p_combo) })}</span>` : ''}${f.es_intermedio ? `<span class="chip">${t('intermedio')}</span>` : ''}</div>
      <div class="paso-pie"><button class="btn btn-t" data-ver-receta="${f.receta_id}">${t('Ver receta y árbol')}</button></div></div>
    <div class="paso"><div class="paso-cab"><span class="paso-n">3</span><span class="paso-titulo">${t('Vende')}</span><span class="paso-meta num gain">${conSigno(ganancia, corto)}</span></div>
      <div class="paso-item">${objHTML(f.producto, t('a <span class="num">{p}</span> c/u', { p: kin(precio) }), `${usaObjetivo ? t('precio objetivo') : t('precio actual')}${unidades != null ? t(' · ~{u} unidades', { u: kin(unidades) }) : ''}`)}</div>
      ${notas.join('')}
      <div class="paso-pie"><button class="btn btn-t" data-detalle="0">${t('Ver detalle')}</button>${usaObjetivo && vale(e.precio_ya) ? `<span class="mas">${t('vender ya: {p} c/u', { p: kin(e.precio_ya) })}</span>` : ''}</div></div>`;
  $('#paso-lista').onclick = () => abrirListaCompra(f.receta_id, n);
  cargarPasoCompra(f, n);
}

async function cargarPasoCompra(f, n) {
  const turno = turnoPanel;
  let l;
  try { l = await api(`/api/recetas/${f.receta_id}/lista-compra?` + qs({ perfil_id: E.perfil, intentos: n }), { silencioso: true }); }
  catch (e) { if (turno === turnoPanel && $('#paso-compra-lista')) $('#paso-compra-lista').innerHTML = avisoHTML(esc(e.message), 'error'); return; }
  if (turno !== turnoPanel || !$('#paso-compra-lista')) return;
  const items = l.comprar || [];
  const origen = i => i.origen === 'npc' ? t('tienda NPC') : t('mercado');
  const precioTxt = i => i.comprar_por_debajo_de != null ? t('por debajo de <b>{p}</b> c/u · {o}', { p: kin(i.comprar_por_debajo_de), o: origen(i) }) : t('a ~<b>{p}</b> c/u · {o}', { p: kin(i.coste_unit), o: origen(i) });
  let html = items.slice(0, 4).map(i => `<div class="paso-item">${objHTML(i.id, `${esc(nom(i.id, i.nombre))} × ${kin(i.cantidad)}`, precioTxt(i))}</div>`).join('');
  if (items.length > 4) html += `<span class="mas">${t('y {n} más en la lista', { n: items.length - 4 })}</span>`;
  if (!items.length) html = `<div class="paso-item dim">${t('No hace falta comprar nada: lo tienes todo.')}</div>`;
  if ((l.fabricar || []).length) html += `<div class="nota">${iconoUI('martillo')}<span>${t('Antes fabrica: {lista}', { lista: l.fabricar.map(x => `${esc(nomTxt(x.nombre))} × ${x.intentos}`).join(', ') })}</span></div>`;
  if ((l.de_inventario || []).length) html += `<div class="nota" style="color:var(--gain)">${iconoUI('escudo')}<span>${t('De tu inventario: {lista}', { lista: l.de_inventario.map(x => `${esc(nom(x.id, x.nombre))} × ${kin(x.cantidad)}`).join(', ') })}</span></div>`;
  $('#paso-compra-lista').innerHTML = html;
  $('#paso-compra-meta').textContent = corto(l.coste_total);
  const b = $('#paso-copiar'), texto = textoLista(l);
  b.disabled = !texto;
  b.onclick = () => copiar(texto);
}
/* shopping list as plain text, built here so it follows the interface language */
function textoLista(l) {
  if (!l || !l.receta_id) return '';
  const lineas = [t('Lista de la compra — {nombre} × {n} intento(s)', { nombre: nomTxt(l.nombre), n: l.intentos })];
  (l.comprar || []).forEach(i => {
    const donde = i.origen === 'npc' ? t('tienda NPC') : t('mercado');
    lineas.push(`- ${nom(i.id, i.nombre)}: ${i.cantidad} (${donde}${i.coste_unit != null ? ' ' + t('a ~{p}', { p: kin(i.coste_unit) }) : ''})`);
  });
  (l.fabricar || []).forEach(x => lineas.push(`* ${t('Fabricar antes')}: ${nomTxt(x.nombre)} × ${t('{n} intento(s)', { n: x.intentos })}`));
  (l.de_inventario || []).forEach(x => lineas.push(`· ${t('Del inventario')}: ${nom(x.id, x.nombre)} × ${x.cantidad}`));
  return lineas.join('\n');
}

function jugadaHTML(f, i) {
  const av = (f.avisos || []).length;
  const det = `<span class="punto ${f.semaforo || ''}" title="${esc(t('Precios {h}', { h: hace(f.antiguedad_precios_horas) }))}"></span>${esc(nombreProf(f.profesion))} · ${t('invierte {inv}', { inv: corto(f.inversion) })}${f.es_intermedio ? ' · ' + t('intermedio') : ''}${av ? ' · ' + t(av > 1 ? '{n} avisos' : '{n} aviso', { n: av }) : ''}`;
  return `<button class="jugada" data-detalle="${i}"><span class="jugada-rank">${String(i + 1).padStart(2, '0')}</span>${icono(f.producto)}
    <span class="obj-texto"><span class="obj-nombre">${esc(nom(f.producto, f.nombre))}</span><span class="obj-det">${det}</span></span>
    <span class="num ${claseSigno(f.beneficio_intento)} col-intento">${conSigno(f.beneficio_intento)}</span><span class="num dim col-margen">${pct0(f.margen)}</span>
    <span class="num col-total">${conSigno(f.beneficio_total, corto)}</span><span class="col-flecha dim">${iconoUI('flecha', 18)}</span></button>`;
}
function pintarJugadas(desde) {
  const cont = $('#panel-tabla');
  const resto = filasPanel.slice(desde);
  if (!resto.length) {
    cont.innerHTML = `<div class="tarjeta vacio">${filasPanel.length ? t('No hay más recetas rentables con estos filtros.') : t('Sin oportunidades todavía. Prueba a quitar filtros o a leer más precios del mercado.')}</div>`;
    return;
  }
  cont.innerHTML = resto.slice(0, panelVer).map((f, k) => jugadaHTML(f, desde + k)).join('')
    + (resto.length > panelVer ? `<button class="btn btn-s ver-mas" id="panel-mas">${t('Ver {n} más (de {total})', { n: Math.min(10, resto.length - panelVer), total: resto.length - panelVer })}</button>` : '');
  const mas = $('#panel-mas');
  if (mas) mas.onclick = () => { panelVer += 10; pintarJugadas(desde); };
}

async function pintarOjo(r, turno) {
  const items = [];
  (r.avisos || []).forEach(a => items.push(['rojo', esc(avisoTxt(a))]));
  const s = servidorActual();
  if (s && r.n_precios) {
    try {
      const ult = await api('/api/mercado/ultimas?' + qs({ servidor_id: s.id, limite: 2000 }), { silencioso: true });
      if (turno !== turnoPanel) return;
      E.ultimasMercado = ult;
      const viejos = ult.filter(x => x.semaforo === 'rojo').length;
      if (viejos) items.push(['rojo', t('<b>{n} de {total} precios</b> tienen más de 24 h. Los cálculos pueden estar desfasados.', { n: kin(viejos), total: kin(ult.length) })]);
    } catch (_) { }
  }
  const vistos = new Set();
  filasPanel.slice(0, 6).forEach(f => {
    const nombre = esc(nom(f.producto, f.nombre));
    (f.avisos || []).filter(a => !avisoRepetido(a)).forEach(a => {
      const k = f.nombre + '|' + a;
      if (!vistos.has(k)) { vistos.add(k); items.push(['ambar', `<b>${nombre}:</b> ${esc(avisoTxt(a))}`]); }
    });
    const e = f.escenario_objetivo;
    if (e && (e.estado === 'saturado' || e.estado === 'hundido')) items.push(['ambar', `<b>${nombre}:</b> ${t('mercado {estado}.', { estado: esc(nombreEstado(e.estado)) })}`]);
    if (vale(f.margen) && f.margen < 0.1 && f.beneficio_total > 0) items.push(['ambar', t('<b>{nombre}</b> deja solo un {m} de margen.', { nombre, m: pct0(f.margen) })]);
  });
  if (filasPanel.slice(0, 15).some(f => f.escenario_objetivo && f.escenario_objetivo.estado === 'sin_datos'))
    items.push(['info', t('Sin histórico suficiente en algunos productos: el precio objetivo usa el precio actual. Cada lectura del mercado lo mejora.')]);
  if (turno !== turnoPanel) return;
  $('#panel-ojo').innerHTML = items.length
    ? items.slice(0, 8).map(([tipo, h]) => `<div class="aviso ${tipo === 'info' ? 'info' : ''}"><span class="punto ${tipo === 'info' ? '' : tipo}"></span><span>${h}</span></div>`).join('')
    : avisoHTML(t('Todo en orden: precios recientes y sin mercados saturados.'), 'ok');
}

/* warnings of a recipe: the "old price" ones are grouped into a single line */
function avisosHTML(lista) {
  const viejos = [], otros = [];
  (lista || []).forEach(a => { const m = /^Precio de (.+) antiguo \((\d+) h\)/.exec(a || ''); if (m) viejos.push(m); else otros.push(a); });
  let html = otros.map(a => `<div class="aviso"><span class="punto ambar"></span><span>${esc(avisoTxt(a))}</span></div>`).join('');
  if (viejos.length) html += `<div class="aviso"><span class="punto rojo"></span><span><b>${t(viejos.length > 1 ? '{n} precios antiguos' : '{n} precio antiguo', { n: viejos.length })}</b> (${esc(haceLargo(Math.max(...viejos.map(m => +m[2]))))}): ${viejos.map(m => esc(nomTxt(m[1]))).join(', ')}. ${t('Haz una lectura del mercado.')}</span></div>`;
  return html;
}
function cifra(et, v, clase = '') { return `<div class="cifra"><div class="cifra-et">${et}</div><div class="cifra-v ${clase}">${v}</div></div>`; }

function abrirDetallePanel(f) {
  const e = f.escenario_objetivo;
  let escenario = '';
  if (e && e.estado === 'sin_datos') {
    escenario = avisoHTML(t('Precio objetivo: hace falta más histórico de este producto (al menos 3 lecturas). Por ahora se usa el precio actual.'), 'info');
  } else if (e && e.precio_objetivo != null) {
    escenario = `<section><h3>${t('Vender ya o esperar al precio objetivo')}</h3><div class="cifras">
      ${cifra(t('Precio ya'), kin(e.precio_ya))}${cifra(t('Beneficio ya'), conSigno(f.beneficio_total, corto), claseSigno(f.beneficio_total))}
      ${cifra(t('Precio objetivo · {estado}', { estado: esc(nombreEstado(e.estado)) }), kin(e.precio_objetivo))}${cifra(t('Beneficio objetivo'), conSigno(e.beneficio_total, corto), claseSigno(e.beneficio_total))}
      ${cifra(t('Tiempo de venta'), e.dias_para_vender != null ? t('{n} d', { n: num1(e.dias_para_vender) }) : '—')}</div>
      ${e.aviso ? `<div style="margin-top:10px">${avisoHTML(esc(avisoTxt(e.aviso)))}</div>` : ''}</section>`;
  } else if (e && e.aviso) escenario = avisoHTML(esc(avisoTxt(e.aviso)), 'info');
  const cab = objHTML(f.producto, `<span class="ic-nombre" style="font-size:22px">${esc(nom(f.producto, f.nombre))}</span>`,
    `${esc(nombreProf(f.profesion))} · ${t('nivel {n}', { n: f.nivel_receta ?? '—' })}${f.es_intermedio ? ' · ' + t('intermedio') : ''} · ${esc(t('precios {h}', { h: hace(f.antiguedad_precios_horas) }))}`, 'ic-l');
  const { cuerpo } = abrirCajon(cab, `
    <div class="cifras">
      ${cifra(t('Benef. / intento'), conSigno(f.beneficio_intento), claseSigno(f.beneficio_intento))}${cifra(t('Margen'), pct(f.margen))}
      ${cifra(t('Intentos'), kin(f.intentos_recomendados))}${cifra(t('Inversión'), corto(f.inversion))}
      ${cifra(t('Benef. total'), conSigno(f.beneficio_total, corto), claseSigno(f.beneficio_total))}${cifra(t('Coste / intento'), kin(f.coste_intento))}
      ${cifra(t('Precio de venta'), kin(f.precio_venta))}${cifra(t('Equilibrio'), kin(f.precio_equilibrio))}
      ${cifra(t('Éxito'), pct(f.p_exito))}${cifra(t('Combo'), pct(f.p_combo))}${cifra(t('Objetos / intento'), num1(f.items_esperados))}
    </div>
    ${f.mensaje_inventario ? avisoHTML(esc(avisoTxt(f.mensaje_inventario)), 'info') : ''}
    ${avisosHTML(f.avisos)}
    ${escenario}
    <div class="fila"><div class="auto"><button class="btn btn-p" id="dp-lista">${iconoUI('carrito', 18)} ${t('Lista de la compra')}</button></div>
      <div class="auto"><button class="btn btn-s" data-ver-receta="${f.receta_id}">${t('Ver receta y árbol')}</button></div></div>`);
  $('#dp-lista', cuerpo).onclick = () => abrirListaCompra(f.receta_id, f.intentos_recomendados);
}

async function abrirListaCompra(recetaId, intentos) {
  const { cuerpo, cab } = abrirCajon(`<p class="eyebrow">${t('Lista de la compra')}</p><h2>${t('Calculando…')}</h2>`, `<div class="vacio">${t('Calculando…')}</div>`);
  async function pintar(n) {
    let r;
    try { r = await api(`/api/recetas/${recetaId}/lista-compra?` + qs({ perfil_id: E.perfil, intentos: n })); }
    catch (e) { cuerpo.innerHTML = avisoHTML(esc(e.message), 'error'); return; }
    const comprar = r.comprar || [], fabricar = r.fabricar || [], deInv = r.de_inventario || [];
    cab.innerHTML = `<p class="eyebrow">${t('Lista de la compra')}</p><h2>${esc(nomTxt(r.nombre))}</h2><p class="ayuda">${t('{n} intento(s) · coste estimado <b class="num">{c}</b> Kinah', { n: r.intentos, c: kin(r.coste_total) })}</p>`;
    cuerpo.innerHTML = `
      <div class="fila"><div><label for="lc-n">${t('Intentos')}</label><input type="number" min="1" id="lc-n" value="${r.intentos}"></div>
        <div class="auto"><button class="btn btn-s" id="lc-re">${t('Recalcular')}</button></div>
        <div class="auto"><button class="btn btn-p" id="lc-copiar">${iconoUI('copiar', 18)} ${t('Copiar texto')}</button></div></div>
      <section><h3>${t('Comprar')}</h3><div class="arbol">
        ${comprar.length ? comprar.map(i => `<div class="nodo-fila">${objHTML(i.id, `${esc(nom(i.id, i.nombre))} × <span class="num">${kin(i.cantidad)}</span>`,
          `${i.origen === 'npc' ? t('tienda NPC') : t('mercado')} · ${t('~<b>{p}</b> c/u', { p: kin(i.coste_unit) })}${i.comprar_por_debajo_de != null ? t(' · compra por debajo de <b>{p}</b>', { p: kin(i.comprar_por_debajo_de) }) : ''}`)}
          <span class="num" title="${t('Coste')}">${kin(i.coste)}</span></div>`).join('') : `<div class="vacio">${t('Nada que comprar: lo tienes todo.')}</div>`}
      </div></section>
      ${fabricar.length ? `<section><h3>${t('Fabricar antes')}</h3><ul class="lista-plana">${fabricar.map(f => `<li>${esc(nomTxt(f.nombre))} × ${t('{n} intento(s)', { n: f.intentos })} · ${esc(nombreProf(f.profesion))}</li>`).join('')}</ul></section>` : ''}
      ${deInv.length ? `<section><h3>${t('Usar de tu inventario')}</h3><ul class="lista-plana">${deInv.map(f => `<li>${esc(nom(f.id, f.nombre))} × ${kin(f.cantidad)}</li>`).join('')}</ul></section>` : ''}
      <div><label for="lc-texto">${t('Texto para pegar')}</label><textarea id="lc-texto" readonly>${esc(textoLista(r))}</textarea></div>`;
    $('#lc-re', cuerpo).onclick = () => pintar(+$('#lc-n', cuerpo).value || 1);
    $('#lc-copiar', cuerpo).onclick = () => copiar($('#lc-texto', cuerpo).value, $('#lc-texto', cuerpo));
  }
  pintar(intentos);
}

$('#tab-panel').addEventListener('click', e => {
  const d = e.target.closest('[data-detalle]');
  if (d) { const f = filasPanel[+d.dataset.detalle]; if (f) abrirDetallePanel(f); }
});

// ================================================================== MARKET
async function cargarMercado() {
  const s = servidorActual();
  if (!s) {
    $('#mercado-servidor').textContent = t('Elige un perfil con servidor');
    $('#m-ultimas').innerHTML = vacio(6, t('Crea un perfil con servidor en Personaje.'));
    $('#m-detalle').innerHTML = avisoHTML(t('Cada servidor tiene su propio mercado: crea un perfil con servidor en Personaje.'), 'info');
    return;
  }
  try {
    E.ultimasMercado = await api('/api/mercado/ultimas?' + qs({ servidor_id: s.id, limite: 2000 }), { silencioso: true });
    pintarUltimas();
  } catch (e) { $('#m-ultimas').innerHTML = vacio(6, esc(e.message)); }
  $('#mercado-servidor').textContent = t('{s} · {f} · {n} objetos con precio', { s: s.nombre, f: nombreFaccion(s.faccion), n: kin(E.ultimasMercado.length) });
  if (E.objMercado) cargarObjetoMercado(E.objMercado);
  else $('#m-detalle').innerHTML = `<div class="vacio pila" style="align-items:center">${iconoCat('otro', 'ic-l')}<span>${t('Busca un objeto arriba o pulsa una fila de «Últimas lecturas» para ver su histórico, las ofertas y el precio objetivo.')}</span></div>`;
}
function pintarUltimas() {
  const q = $('#m-filtro').value.trim().toLowerCase();
  const filas = E.ultimasMercado.filter(f => !q || (f.nombre || '').toLowerCase().includes(q) || nom(f.objeto_id, f.nombre).toLowerCase().includes(q));
  $('#m-ultimas').innerHTML = filas.length ? filas.slice(0, 500).map(f => `<tr class="clic ${E.objMercado === f.objeto_id ? 'sel' : ''}" data-obj="${f.objeto_id}">
      <td>${objHTML(f.objeto_id, esc(nom(f.objeto_id, f.nombre)), '', 'ic-s')}</td><td class="num">${kin(f.precio_min)}</td><td class="num">${kin(f.cantidad_total)}</td>
      <td class="num ocultar-movil">${f.num_anuncios ?? '—'}</td><td class="ocultar-movil"><span class="chip">${esc(nombreFuente(f.fuente))}</span></td>
      <td>${chipEdad(f.semaforo, f.antiguedad_horas)}</td></tr>`).join('')
    : vacio(6, E.ultimasMercado.length ? t('Ningún objeto coincide.') : t('Aún no hay lecturas en este servidor.'));
}
$('#m-filtro').addEventListener('input', debounce(pintarUltimas, 150));
$('#m-ultimas').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-obj]');
  if (tr) { cargarObjetoMercado(+tr.dataset.obj); $('#m-detalle').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
});
autocompletar($('#m-buscar'), it => cargarObjetoMercado(it.id));

async function cargarObjetoMercado(oid) {
  E.objMercado = oid;
  $$('#m-ultimas tr[data-obj]').forEach(tr => tr.classList.toggle('sel', +tr.dataset.obj === oid));
  const s = servidorActual(), cont = $('#m-detalle');
  if (!s) { cont.innerHTML = avisoHTML(tApi('Elige un perfil con servidor para ver su mercado.')); return; }
  const dias = $('#m-dias') ? $('#m-dias').value : 30;
  cont.classList.add('cargando');
  let d;
  try { d = await api(`/api/mercado/objeto/${oid}?` + qs({ servidor_id: s.id, dias }), { silencioso: true }); }
  catch (e) { cont.classList.remove('cargando'); cont.innerHTML = avisoHTML(esc(e.message), 'error'); return; }
  cont.classList.remove('cargando');
  const a = d.actual, v = d.objetivo_venta || {}, c = d.objetivo_compra || {}, o = d.objeto;
  const otroNombre = IDIOMA === 'en' ? (o.nombre_en ? o.nombre : '') : (o.nombre_en || '');
  const det = [otroNombre ? esc(otroNombre) : '', o.vinculado ? t('vinculado') : t('comerciable'), d.recetas.length ? t(d.recetas.length > 1 ? 'se fabrica ({n} recetas)' : 'se fabrica ({n} receta)', { n: d.recetas.length }) : ''].filter(Boolean).join(' · ');
  const ofertas = (a && a.ofertas) || [];
  const maxQ = Math.max(1, ...ofertas.map(([, q]) => q || 0));
  let rango = `<p class="ayuda" style="margin-top:10px">${t('Hace falta más histórico (al menos 3 lecturas) para calcular el precio objetivo.')}</p>`;
  if (v.rango_p25 != null && v.rango_p75 != null) {
    const p25 = v.rango_p25, p75 = v.rango_p75, rec = v.precio_recomendado;
    const ancho = Math.max(p75 - p25, Math.abs(p25) * 0.05, 1);
    const lo = Math.min(p25, rec ?? p25) - ancho * 0.6, hi = Math.max(p75, rec ?? p75) + ancho * 0.6;
    const pos = x => Math.max(0, Math.min(100, (x - lo) / (hi - lo) * 100));
    rango = `<div class="rango" style="margin-top:14px"><div class="rango-barra"><span class="tramo" style="left:${pos(p25).toFixed(1)}%;width:${(pos(p75) - pos(p25)).toFixed(1)}%"></span>${rec != null ? `<span class="marca-v" style="left:${pos(rec).toFixed(1)}%"></span>` : ''}</div>
      <div class="rango-et num"><span>${t('p25 {p}', { p: kin(p25) })}</span><span>${t('objetivo {p}', { p: kin(rec) })}</span><span>${t('p75 {p}', { p: kin(p75) })}</span></div></div>`;
  }
  cont.innerHTML = `
    <div class="ficha">${objHTML(oid, `<span class="ic-nombre" style="font-size:24px">${esc(nom(oid, o.nombre))}</span>`, det, 'ic-xl')}
      <div class="ficha-precio"><div class="num">${kin(a && a.precio_min)}</div><div class="ayuda">${t('precio mínimo · {edad}', { edad: a ? chipEdad(a.semaforo, a.antiguedad_horas) : t('sin lecturas') })}</div></div></div>
    <div class="cifras" style="margin-top:18px">
      ${cifra(t('En oferta'), kin(a && a.cantidad_total))}${cifra(t('Anuncios'), a && a.num_anuncios != null ? a.num_anuncios : '—')}
      ${cifra(t('Volumen / día'), d.volumen_dia != null ? num1(d.volumen_dia) : '—')}${cifra(t('Compra por debajo de'), kin(c.comprar_por_debajo_de))}
      ${cifra(t('Precio objetivo'), kin(v.precio_recomendado), 'gain')}</div>
    ${v.aviso ? `<div style="margin-top:12px">${avisoHTML(esc(avisoTxt(v.aviso)))}</div>` : ''}${c.aviso && c.estado === 'oportunidad' ? `<div style="margin-top:12px">${avisoHTML(esc(avisoTxt(c.aviso)), 'ok')}</div>` : ''}
    ${d.aviso_objetivo ? `<div style="margin-top:12px">${avisoHTML(esc(avisoTxt(d.aviso_objetivo)), 'error')}</div>` : ''}
    <div class="fila" style="margin-top:16px"><div class="auto"><label for="m-dias">${t('Histórico')}</label>
      <select id="m-dias">${[7, 30, 90, 365].map(n => `<option value="${n}" ${n == d.dias ? 'selected' : ''}>${t('{n} días', { n })}</option>`).join('')}</select></div>
      <div class="auto"><button class="btn btn-s" id="m-a-manual">${iconoUI('etiqueta', 18)} ${t('Apuntar precio')}</button></div>
      ${d.recetas.length ? `<div class="auto"><button class="btn btn-s" data-ver-receta="${d.recetas[0].id}">${t('Ver su receta')}</button></div>` : ''}</div>
    <div class="grafico" style="margin-top:14px">${d.historico.length ? `<canvas id="m-grafico" aria-label="${t('Histórico de precio y unidades en oferta')}"></canvas>` : `<div class="vacio">${t('Sin histórico en este periodo.')}</div>`}</div>
    <div class="g2" style="margin-top:18px">
      <div><h3>${t('Ofertas ahora')}</h3>${ofertas.length ? `<div class="profundidad" style="margin-top:10px">${ofertas.slice(0, 8).map(([p, q]) => `<div class="prof-fila"><span class="num">${kin(p)}</span><div class="prof-barra"><span style="width:${Math.round((q || 0) / maxQ * 100)}%"></span></div><span class="num dim" style="text-align:right">${kin(q)}</span></div>`).join('')}</div>` : `<p class="ayuda" style="margin-top:10px">${t('La última lectura no trae el libro de ofertas.')}</p>`}</div>
      <div><h3>${t('Precio objetivo de venta')} ${v.estado ? `<span class="chip ${CHIP_ESTADO[v.estado] || ''}">${esc(nombreEstado(v.estado))}</span>` : ''}</h3>${rango}</div>
    </div>`;
  $('#m-dias').onchange = () => cargarObjetoMercado(oid);
  $('#m-a-manual').onclick = () => { const i = $('#mm-obj'); i.value = nom(oid, o.nombre); i.dataset.id = oid; $('#m-manual-card').scrollIntoView({ behavior: 'smooth' }); $('#mm-precio').focus(); };
  if (d.historico.length) pintarGrafico(d.historico);
  else { if (E.grafico) E.grafico.destroy(); E.grafico = null; }
}
function colorVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function pintarGrafico(hist) {
  E.ultimoHist = hist;
  if (E.grafico) { E.grafico.destroy(); E.grafico = null; }
  const lienzo = $('#m-grafico');
  if (!lienzo) return;
  if (!window.Chart) { lienzo.replaceWith(Object.assign(document.createElement('div'), { className: 'vacio', textContent: t('No se pudo cargar Chart.js (¿sin internet?).') })); return; }
  const acento = colorVar('--accent'), suave = colorVar('--accent-soft'), linea = colorVar('--line'), apagado = colorVar('--muted'), texto = colorVar('--text'), segundo = colorVar('--gain');
  const puntos = campo => hist.filter(l => l[campo] != null).map(l => ({ x: new Date(l.fecha).getTime(), y: l[campo] }));
  const cantidades = puntos('cantidad_total');
  const series = [{ label: t('Precio mínimo'), data: puntos('precio_min'), borderColor: acento, backgroundColor: suave, fill: true, yAxisID: 'y', tension: 0.25, pointRadius: 2, borderWidth: 3 }];
  if (cantidades.length) series.push({ label: t('Unidades en oferta'), data: cantidades, borderColor: segundo, backgroundColor: segundo, yAxisID: 'y2', tension: 0.25, pointRadius: 0, borderWidth: 1.5, borderDash: [4, 4] });
  Chart.defaults.font.family = colorVar('--font-body');
  E.grafico = new Chart(lienzo, {
    type: 'line',
    data: { datasets: series },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { type: 'linear', ticks: { color: apagado, maxTicksLimit: 8, callback: v => new Date(v).toLocaleDateString(LOCALE(), { day: '2-digit', month: '2-digit' }) }, grid: { color: linea } },
        y: { position: 'left', ticks: { color: apagado, callback: v => NF.format(v) }, grid: { color: linea } },
        y2: { display: cantidades.length > 0, position: 'right', ticks: { color: apagado, callback: v => NF.format(v) }, grid: { display: false } },
      },
      plugins: {
        legend: { labels: { color: texto, boxWidth: 12 } },
        tooltip: { callbacks: { title: items => fecha(new Date(items[0].parsed.x).toISOString()), label: c => `${c.dataset.label}: ${NF.format(c.parsed.y)}` } },
      },
    },
  });
}
autocompletar($('#mm-obj'));
$('#mm-guardar').addEventListener('click', async () => {
  const s = servidorActual(), obj = $('#mm-obj');
  if (!s) return toast(t('Elige un perfil con servidor.'), 'error');
  if (!obj.dataset.id) return toast(t('Elige el objeto de la lista de sugerencias.'), 'error');
  const oid = +obj.dataset.id;
  try {
    const r = await api('/api/mercado/manual', {
      method: 'POST', body: {
        servidor_id: s.id, objeto_id: oid, precio_min: $('#mm-precio').value || null,
        cantidad_total: $('#mm-cant').value || null, num_anuncios: $('#mm-anun').value || null, ofertas_texto: $('#mm-ofertas').value,
      }
    });
    toast(r.en_cola ? t('Guardado en la cola offline (se subirá al reconectar).') : t('Lectura guardada.'), 'ok');
    ['#mm-precio', '#mm-cant', '#mm-anun', '#mm-ofertas'].forEach(id => { $(id).value = ''; });
    E.objMercado = oid;
    cargarMercado();
  } catch (_) { }
});

// ================================================================== CAPTURE
async function cargarCaptura() {
  await refrescarCaptura();
  cargarCalibracion();
}
function pararPoll() { if (E.pollCaptura) { clearInterval(E.pollCaptura); E.pollCaptura = null; } }
const CHIP_SESION = { revision: ['chip-warn', 'Por revisar'], terminada: ['chip-gain', 'Guardada'], error: ['chip-danger', 'Error'] };
const chipDe = (tabla, k) => tabla[k] ? `<span class="chip ${tabla[k][0]}">${esc(t(tabla[k][1]))}</span>` : esc(k);
async function refrescarCaptura() {
  let st;
  try { st = await api('/api/captura/estado', { silencioso: true }); } catch (e) { $('#c-sesiones').innerHTML = vacio(7, esc(e.message)); return; }
  const g = st.grabacion, terminar = $('#c-terminar');
  $('#c-empezar').disabled = st.grabando;
  terminar.disabled = !st.grabando;
  terminar.classList.toggle('btn-d', !!st.grabando); terminar.classList.toggle('btn-s', !st.grabando);
  $('#c-estado-grab').innerHTML = st.grabando
    ? `<span class="punto vivo"></span> ${t('Leyendo…')} ${g ? t('{s} s · {p} pantallas distintas · {f} filas', { s: Math.round(g.segundos || 0), p: g.fotogramas_procesados ?? 0, f: g.filas_leidas ?? 0 }) : ''}${g && g.error ? ` <span class="loss">${esc(tApi(g.error))}</span>` : ''}`
    : '';
  const ses = st.sesiones || [];
  $('#c-sesiones').innerHTML = ses.length ? ses.map(s => {
    const prog = Math.round((s.progreso || 0) * 100);
    const est = s.estado === 'procesando' ? `<div class="progreso" title="${prog} %"><span style="width:${prog}%"></span></div>` : chipDe(CHIP_SESION, s.estado);
    const origen = t({ grabacion: 'Grabación', video: 'Vídeo', imagen: 'Captura' }[s.origen] || s.origen || '');
    return `<tr class="${E.sesionSel === s.id ? 'sel' : ''}"><td>${fecha(s.creada)}</td><td>${esc(origen)}${s.nombre_archivo ? ` <span class="dim">${esc(s.nombre_archivo)}</span>` : ''}</td><td>${est}</td>
      <td class="num">${s.n_filas}</td><td class="num">${s.n_dudosas}</td><td class="dim ocultar-movil">${esc(tApi(s.error || s.mensaje || ''))}</td>
      <td>${s.estado === 'revision' ? `<button class="btn btn-p" data-revisar="${s.id}">${t('Revisar')}</button>` : s.n_filas ? `<button class="btn btn-s" data-revisar="${s.id}">${t('Ver')}</button>` : ''}</td></tr>`;
  }).join('') : vacio(7, t('Todavía no hay lecturas.'));
  const activo = st.grabando || ses.some(s => s.estado === 'procesando');
  if (activo && !E.pollCaptura) E.pollCaptura = setInterval(refrescarCaptura, 2000);
  if (!activo) pararPoll();
  if (E.sesionSel && ses.some(s => s.id === E.sesionSel && s.estado !== 'procesando') && !$('#c-revision').dataset.cargada) verSesion(E.sesionSel);
}
$('#c-empezar').addEventListener('click', async () => {
  const s = servidorActual();
  if (!s) return toast(t('Elige un perfil con servidor: las lecturas van al mercado de ese servidor.'), 'error');
  try { await api('/api/captura/grabacion/iniciar', { method: 'POST', body: { servidor_id: s.id } }); toast(t('Lectura en marcha: cambia al juego y recorre el mercado.'), 'ok'); }
  catch (_) { }
  refrescarCaptura();
});
$('#c-terminar').addEventListener('click', async () => {
  $('#c-terminar').disabled = true;
  try {
    const r = await api('/api/captura/grabacion/detener', { method: 'POST' });
    toast(r.estado === 'revision' ? t('Lectura terminada: {n} fila(s) para revisar.', { n: r.n_dudosas }) : (tApi(r.mensaje) || t('Lectura terminada.')), r.estado === 'error' ? 'error' : 'ok');
    E.sesionSel = r.id; $('#c-revision').dataset.cargada = '';
  } catch (_) { }
  refrescarCaptura();
});
const zona = $('#c-zona');
zona.addEventListener('click', e => { if (e.target !== $('#c-archivo')) $('#c-archivo').click(); });
zona.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#c-archivo').click(); } });
zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('sobre'); });
zona.addEventListener('dragleave', () => zona.classList.remove('sobre'));
zona.addEventListener('drop', e => { e.preventDefault(); zona.classList.remove('sobre'); subirArchivos([...e.dataTransfer.files]); });
$('#c-archivo').addEventListener('change', e => { subirArchivos([...e.target.files]); e.target.value = ''; });
async function subirArchivos(archivos) {
  const s = servidorActual();
  if (!s) return toast(t('Elige un perfil con servidor antes de subir.'), 'error');
  for (const f of archivos) {
    toast(t('Subiendo {f}…', { f: f.name }));
    try {
      const r = await api('/api/captura/subir?' + qs({ nombre: f.name, servidor_id: s.id }), { method: 'POST', cuerpoCrudo: f });
      E.sesionSel = r.id; $('#c-revision').dataset.cargada = '';
      toast(t('{f}: procesando…', { f: f.name }), 'ok');
    } catch (_) { }
  }
  refrescarCaptura();
}
$('#c-sesiones').addEventListener('click', e => {
  const b = e.target.closest('[data-revisar]');
  if (b) verSesion(b.dataset.revisar);
});
const CHIP_FILA = { pendiente: ['chip-warn', 'dudosa'], ok: ['chip-gain', 'ok'], corregida: ['chip-accent', 'corregida'], descartada: ['', 'descartada'] };
async function verSesion(id) {
  E.sesionSel = id;
  const cont = $('#c-revision');
  cont.dataset.cargada = '1';
  let s;
  try { s = await api('/api/captura/sesiones/' + id, { silencioso: true }); } catch (e) { cont.innerHTML = avisoHTML(esc(e.message), 'error'); return; }
  const enRevision = s.estado === 'revision';
  const mostrarTodas = leerLocal('verTodas', false);
  const filas = s.filas.filter(f => mostrarTodas || f.estado === 'pendiente' || !enRevision);
  cont.innerHTML = `<div class="pila" style="margin-top:22px"><div class="cab-tarjeta"><h3>${t('Revisión · {n} filas ({d} dudosas)', { n: s.n_filas, d: s.n_dudosas })}</h3>
      <label class="check"><input type="checkbox" id="c-todas" ${mostrarTodas ? 'checked' : ''}> ${t('Mostrar también las correctas')}</label>
      ${enRevision ? `<p class="ayuda">${t('Corrige el objeto, precio o cantidad y pulsa ✓; o descarta la fila con ✕. Al guardar, las filas que sigan pendientes se descartan.')}</p>` : ''}</div>
    <div class="tabla-caja alta"><table><thead><tr><th>${t('Imagen / leído')}</th><th>${t('Objeto')}</th><th class="num">${t('Precio')}</th><th class="num">${t('Cantidad')}</th><th class="ocultar-movil">${t('Motivo')}</th><th>${t('Estado')}</th><th></th></tr></thead><tbody>
    ${filas.length ? filas.map(f => `<tr data-idx="${f.idx}">
      <td>${f.recorte ? `<img class="recorte" loading="lazy" src="/api/captura/sesiones/${s.id}/filas/${f.idx}/recorte" alt="${t('Recorte de la fila leída')}">` : ''}<span class="dim">${esc(f.nombre_leido)}</span></td>
      <td><div class="ac"><input class="r-obj" value="${esc(f.nombre ? nom(f.objeto_id, f.nombre) : '')}" data-id="${f.objeto_id ?? ''}" ${enRevision ? '' : 'disabled'} placeholder="${t('Elige objeto…')}" autocomplete="off" aria-label="${t('Objeto')}"></div></td>
      <td class="num"><input class="r-precio" type="number" value="${f.precio ?? ''}" ${enRevision ? '' : 'disabled'} aria-label="${t('Precio')}"></td>
      <td class="num"><input class="r-cant" type="number" value="${f.cantidad ?? ''}" ${enRevision ? '' : 'disabled'} aria-label="${t('Cantidad')}"></td>
      <td class="dim ocultar-movil" style="font-size:13px">${esc((f.motivos || []).map(tApi).join('; '))}${f.confianza != null ? ` (${Math.round(f.confianza * 100)} %)` : ''}</td>
      <td>${chipDe(CHIP_FILA, f.estado)}</td>
      <td style="white-space:nowrap">${enRevision ? `<button class="btn btn-g btn-icono" data-acc="confirmar" title="${t('Confirmar')}" aria-label="${t('Confirmar')}">✓</button> <button class="btn btn-d btn-icono" data-acc="descartar" title="${t('Descartar')}" aria-label="${t('Descartar')}">✕</button>` : ''}</td></tr>`).join('') : vacio(7, t('No hay filas dudosas.'))}
    </tbody></table></div>
    ${enRevision ? `<div><button class="btn btn-p" id="c-guardar-sesion">${t('Guardar sesión ({n} correctas)', { n: s.n_ok })}</button></div>` : ''}</div>`;
  $$('.r-obj', cont).forEach(i => { if (i.dataset.id === '') delete i.dataset.id; autocompletar(i); });
  $('#c-todas', cont).onchange = e => { guardarLocal('verTodas', e.target.checked); verSesion(id); };
  const g = $('#c-guardar-sesion', cont);
  if (g) g.onclick = async () => {
    try { const r = await api(`/api/captura/sesiones/${id}/guardar`, { method: 'POST' }); toast(tApi(r.mensaje) || t('Sesión guardada.'), 'ok'); }
    catch (_) { }
    verSesion(id); refrescarCaptura();
  };
}
$('#c-revision').addEventListener('click', async e => {
  const b = e.target.closest('[data-acc]');
  if (!b) return;
  const tr = b.closest('tr'), idx = tr.dataset.idx, obj = $('.r-obj', tr);
  const datos = { accion: b.dataset.acc };
  if (b.dataset.acc === 'confirmar') {
    if (!obj.dataset.id) return toast(t('Elige el objeto correcto de la lista de sugerencias.'), 'error');
    Object.assign(datos, { objeto_id: +obj.dataset.id, precio: $('.r-precio', tr).value, cantidad: $('.r-cant', tr).value });
  }
  try { await api(`/api/captura/sesiones/${E.sesionSel}/filas/${idx}`, { method: 'POST', body: datos }); verSesion(E.sesionSel); refrescarCaptura(); }
  catch (_) { }
});

// --- calibration
const CAL = { img: null, ancho: 0, alto: 0, lista: null, columnas: {}, arrastre: null };
const COLORES_CAL = { lista: '#4BE3A8', nombre: '#6FD3FF', precio: '#FFB547', cantidad: '#B9A7FF' };
async function cargarCalibracion() {
  try {
    const c = await api('/api/captura/calibracion', { silencioso: true });
    const res = c.resolucion, act = c.actual;
    const calibrada = act && act.calibrada;
    $('#cal-chip').innerHTML = res ? `<span class="chip ${calibrada ? 'chip-gain' : 'chip-warn'}">${res[0]} × ${res[1]} ${calibrada ? t('calibrada') : t('sin calibrar')}</span>` : '';
    $('#cal-info').innerHTML = res ? (calibrada ? t('Zona de lectura: {z}.', { z: act.lista.join(', ') }) : t('Sin calibrar: se lee la pantalla completa (más lento y con más errores).')) : esc(tApi(c.aviso || ''));
    CAL.guardada = c.datos;
  } catch (e) { $('#cal-info').textContent = e.message; }
}
$('#cal-pantalla').addEventListener('click', async () => {
  const b = $('#cal-pantalla'), txt = $('span:last-child', b);
  b.disabled = true;
  let n = 5; txt.textContent = t('Cambia al juego… {n}', { n });
  const reloj = setInterval(() => { n--; if (n > 0) txt.textContent = t('Cambia al juego… {n}', { n }); }, 1000);
  try {
    const r = await fetch('/api/captura/calibracion/pantalla?espera=5', { method: 'POST' });
    if (!r.ok) throw new Error(tApi((await r.json()).detail) || t('No se pudo capturar la pantalla'));
    const ancho = +r.headers.get('X-Ancho'), alto = +r.headers.get('X-Alto');
    cargarImagenCal(URL.createObjectURL(await r.blob()), ancho, alto);
  } catch (e) { toast(e.message, 'error'); }
  finally { clearInterval(reloj); b.disabled = false; txt.textContent = t('Capturar pantalla (5 s)'); }
});
$('#cal-cargar').addEventListener('click', () => $('#cal-archivo').click());
$('#cal-archivo').addEventListener('change', e => {
  const f = e.target.files[0]; if (!f) return;
  cargarImagenCal(URL.createObjectURL(f));
  e.target.value = '';
});
function cargarImagenCal(url, anchoReal, altoReal) {
  const img = new Image();
  img.onload = () => {
    CAL.img = img; CAL.ancho = anchoReal || img.naturalWidth; CAL.alto = altoReal || img.naturalHeight;
    const conf = CAL.guardada && CAL.guardada.resoluciones && CAL.guardada.resoluciones[`${CAL.ancho}x${CAL.alto}`];
    CAL.lista = conf ? conf.lista.slice() : null;
    CAL.columnas = conf && conf.columnas ? JSON.parse(JSON.stringify(conf.columnas)) : {};
    const lz = $('#cal-lienzo');
    lz.width = img.naturalWidth; lz.height = img.naturalHeight;
    $('#cal-wrap').hidden = false;
    $('#cal-guardar').disabled = !CAL.lista;
    $('#cal-info').innerHTML = t('Imagen {w}×{h}. Arrastra para marcar la <b>zona de la lista</b>{ya}.', { w: CAL.ancho, h: CAL.alto, ya: conf ? t(' (ya había una calibración para esta resolución)') : '' });
    pintarCal();
  };
  img.src = url;
}
function pintarCal() {
  const lz = $('#cal-lienzo'), ctx = lz.getContext('2d'), k = lz.width / CAL.ancho;
  ctx.drawImage(CAL.img, 0, 0, lz.width, lz.height);
  ctx.lineWidth = Math.max(2, lz.width / 500);
  ctx.font = `600 ${Math.max(14, lz.width / 80)}px system-ui, sans-serif`;
  const caja = (x, y, w, h, color, texto) => { ctx.strokeStyle = color; ctx.fillStyle = color + '22'; ctx.fillRect(x * k, y * k, w * k, h * k); ctx.strokeRect(x * k, y * k, w * k, h * k); ctx.fillStyle = color; ctx.fillText(texto, x * k + 4, y * k + 18); };
  if (CAL.lista) {
    const [x, y, w, h] = CAL.lista;
    caja(x, y, w, h, COLORES_CAL.lista, t('Lista'));
    for (const [col, [x0, x1]] of Object.entries(CAL.columnas || {})) caja(x0, y, x1 - x0, h, COLORES_CAL[col] || '#ffffff', t(col));
  }
  if (CAL.arrastre) { const a = CAL.arrastre; caja(Math.min(a.x0, a.x1), Math.min(a.y0, a.y1), Math.abs(a.x1 - a.x0), Math.abs(a.y1 - a.y0), COLORES_CAL[$('#cal-modo').value], ''); }
}
function puntoCal(e) {
  const lz = $('#cal-lienzo'), r = lz.getBoundingClientRect();
  return { x: Math.round((e.clientX - r.left) / r.width * CAL.ancho), y: Math.round((e.clientY - r.top) / r.height * CAL.alto) };
}
$('#cal-lienzo').addEventListener('pointerdown', e => { if (!CAL.img) return; const p = puntoCal(e); CAL.arrastre = { x0: p.x, y0: p.y, x1: p.x, y1: p.y }; e.target.setPointerCapture(e.pointerId); });
$('#cal-lienzo').addEventListener('pointermove', e => { if (!CAL.arrastre) return; const p = puntoCal(e); CAL.arrastre.x1 = p.x; CAL.arrastre.y1 = p.y; pintarCal(); });
$('#cal-lienzo').addEventListener('pointerup', () => {
  const a = CAL.arrastre; CAL.arrastre = null;
  if (!a || Math.abs(a.x1 - a.x0) < 8) { if (CAL.img) pintarCal(); return; }
  const modo = $('#cal-modo').value;
  if (modo === 'lista') {
    if (Math.abs(a.y1 - a.y0) < 8) { pintarCal(); return; }
    CAL.lista = [Math.min(a.x0, a.x1), Math.min(a.y0, a.y1), Math.abs(a.x1 - a.x0), Math.abs(a.y1 - a.y0)];
  } else {
    CAL.columnas[modo] = [Math.min(a.x0, a.x1), Math.max(a.x0, a.x1)];
  }
  $('#cal-guardar').disabled = !CAL.lista;
  pintarCal();
});
$('#cal-guardar').addEventListener('click', async () => {
  const cols = Object.keys(CAL.columnas).length ? CAL.columnas : null;
  try {
    await api('/api/captura/calibracion', { method: 'PUT', body: { ancho: CAL.ancho, alto: CAL.alto, region: CAL.lista, columnas: cols } });
    toast(t('Calibración guardada.'), 'ok');
    cargarCalibracion();
  } catch (_) { }
});

// ================================================================== RECIPES
async function cargarRecetas() {
  const cont = $('#r-lista');
  cont.classList.add('cargando');
  try {
    const r = await api('/api/recetas?' + qs({ perfil_id: E.perfil, q: $('#r-q').value.trim(), profesion: E.rProf, solo_desbloqueadas: $('#r-desb').checked, limite: 400 }), { silencioso: true });
    $('#r-sub').textContent = t('{n} recetas', { n: kin(r.total) }) + (r.faccion ? t(' de tu facción ({f})', { f: nombreFaccion(r.faccion) }) : '') + (E.rProf ? ' · ' + nombreProf(E.rProf) : '');
    $('#r-total').textContent = r.total > r.filas.length ? t('Mostrando {n} de {total}: afina la búsqueda.', { n: r.filas.length, total: kin(r.total) }) : t('{n} recetas', { n: kin(r.filas.length) });
    cont.innerHTML = r.filas.length ? r.filas.map(f => `<tr class="clic ${E.recetaSel === f.id ? 'sel' : ''}" data-receta="${f.id}">
      <td>${objHTML(f.producto, esc(nom(f.producto, f.nombre)) + (f.cantidad > 1 ? ` <span class="dim">×${f.cantidad}</span>` : ''), '', 'ic-s')}</td><td class="ocultar-movil">${esc(nombreProf(f.profesion))}</td>
      <td class="num">${f.nivel ?? '—'}</td><td class="num ocultar-movil">${f.combo_pct ? f.combo_pct + ' %' : '—'}</td>
      <td>${f.desbloqueada ? `<span class="chip chip-gain">${t('Desbloqueada')}</span>` : `<span class="chip">${iconoUI('candado', 14)} ${t('nv. {n}', { n: f.nivel ?? '—' })}</span>`}</td></tr>`).join('')
      : vacio(5, t('Ninguna receta coincide.'));
  } catch (e) { cont.innerHTML = vacio(5, esc(e.message)); }
  cont.classList.remove('cargando');
  if (E.recetaSel) verReceta(E.recetaSel, false);
}
$('#r-q').addEventListener('input', debounce(cargarRecetas, 250));
$('#r-desb').addEventListener('change', cargarRecetas);
$('#r-profs').addEventListener('click', e => {
  const b = e.target.closest('[data-prof]'); if (!b) return;
  E.rProf = b.dataset.prof; guardarLocal('rProf', E.rProf); marcarProfReceta(); cargarRecetas();
});
$('#r-lista').addEventListener('click', e => {
  const tr = e.target.closest('[data-receta]'); if (!tr) return;
  verReceta(+tr.dataset.receta);
  if (window.innerWidth < 900) $('#r-detalle-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

async function verReceta(id, cambiarPestana = true, intentos) {
  E.recetaSel = id;
  if (cambiarPestana && E.tab !== 'recetas') { irA('recetas'); return; }
  $$('#r-lista tr').forEach(tr => tr.classList.toggle('sel', +tr.dataset.receta === id));
  const cont = $('#r-detalle');
  cont.classList.add('cargando');
  let d;
  try { d = await api(`/api/recetas/${id}?` + qs({ perfil_id: E.perfil, intentos: intentos || 1 }), { silencioso: true }); }
  catch (e) { cont.classList.remove('cargando'); cont.innerHTML = avisoHTML(esc(e.message), 'error'); return; }
  cont.classList.remove('cargando');
  const r = d.receta, a = d.analisis, e_ = d.escenario_objetivo;
  const combo = r.producto_combo_nombre ? ' → ' + esc(r.producto_combo ? nom(r.producto_combo, r.producto_combo_nombre) : nomTxt(r.producto_combo_nombre)) : '';
  const det = `${esc(nombreProf(r.profesion))} · ${t('nivel {n}', { n: r.nivel })} · ${r.faccion === 'ambas' ? t('ambas facciones') : esc(nombreFaccion(r.faccion))} · ${t('produce {n}', { n: r.cantidad || 1 })}${r.combo_pct ? ` · ${t('combo {p}', { p: r.combo_pct + ' %' })}${combo}` : ''}`;
  cont.innerHTML = `<div class="pila-grande">
    ${objHTML(r.producto, `<span class="ic-nombre" style="font-size:20px">${esc(nom(r.producto, r.nombre))}</span>`, det, 'ic-l')}
    ${d.aviso ? avisoHTML(esc(avisoTxt(d.aviso)), 'error') : ''}
    ${a ? `<div class="fila"><div class="auto"><label for="rd-n">${t('Intentos')}</label><input id="rd-n" type="number" min="1" value="${a.intentos}" style="width:110px"></div>
      <div class="auto"><button class="btn btn-s" id="rd-re">${t('Recalcular')}</button></div>
      <div class="auto"><button class="btn btn-p" id="rd-lista">${iconoUI('carrito', 18)} ${t('Lista de la compra')}</button></div></div>
    <div class="cifras">
      ${cifra(t('Coste / intento'), kin(a.coste_intento))}${cifra(t('Ingreso / intento'), kin(a.ingreso_esperado))}
      ${cifra(t('Benef. / intento'), conSigno(a.beneficio_intento), claseSigno(a.beneficio_intento))}${cifra(t('Margen'), pct(a.margen))}
      ${cifra(t('Benef. {n} intento(s)', { n: a.intentos }), conSigno(a.beneficio_total, corto), claseSigno(a.beneficio_total))}${cifra(t('Equilibrio'), kin(a.precio_equilibrio))}
      ${cifra(t('Éxito (nv. {n})', { n: a.nivel }), pct(a.p_exito))}${cifra(t('Combo'), pct(a.p_combo))}
      ${cifra(t('Objetos / intento'), num1(a.items_esperados))}${cifra(t('Intentos rentables'), a.max_intentos_mercado == null ? '∞' : kin(a.max_intentos_mercado))}
    </div>
    ${a.mensaje_inventario ? avisoHTML(esc(avisoTxt(a.mensaje_inventario)), 'info') : ''}
    ${avisosHTML(a.avisos)}
    ${e_ && e_.precio_objetivo != null && e_.estado !== 'sin_datos' ? avisoHTML(t('Precio objetivo de venta: <b class="num">{p}</b> ({estado}) → beneficio {b} frente a {ya} vendiendo ya a {pya}.', { p: kin(e_.precio_objetivo), estado: esc(nombreEstado(e_.estado)), b: conSigno(e_.beneficio_total, corto), ya: conSigno(a.beneficio_total, corto), pya: kin(e_.precio_ya) }) + (e_.aviso ? ' ' + esc(avisoTxt(e_.aviso)) : ''), 'info') : ''}
    <section><h3>${t('Ingredientes y mejor origen')}</h3><div class="arbol">${arbolHTML(d.arbol || [])}</div></section>
    <details><summary>${t('Desglose por intento')}</summary><div class="tabla-caja"><table><thead><tr><th>${t('Ingrediente')}</th><th class="num">${t('Cant.')}</th><th>${t('Origen')}</th><th class="num">${t('Coste unit.')}</th><th class="num">${t('Tienes')}</th><th class="num">${t('Faltan')}</th></tr></thead><tbody>
      ${a.desglose_ingredientes.map(i => `<tr><td>${esc(nom(i.id, i.nombre))}</td><td class="num">${num1(i.cantidad)}</td><td>${esc(t({ mercado: 'Mercado', npc: 'Tienda NPC', fabricar: 'Fabricar', inventario: 'Inventario' }[i.origen] || '—'))}</td>
        <td class="num">${kin(i.coste_unit)}</td><td class="num">${kin(i.en_inventario)}</td><td class="num">${kin(i.faltan)}</td></tr>`).join('')}
    </tbody></table></div></details>` : ''}</div>`;
  const re = $('#rd-re'); if (re) re.onclick = () => verReceta(id, false, +$('#rd-n').value || 1);
  const li = $('#rd-lista'); if (li) li.onclick = () => abrirListaCompra(id, +$('#rd-n').value || 1);
}
function arbolHTML(nodos) {
  return nodos.map(n => {
    const f = (k, et, v) => v == null ? '' : `<span class="fuente ${n.mejor === k ? 'mejor' : ''}">${et} ${kin(v)}${n.mejor === k ? ' ✓' : ''}</span>`;
    const nota = n.nota ? esc(tApi(n.nota)) : '';
    const det = n.precio_mercado != null && n.antiguedad_horas != null
      ? `<span class="punto ${semaforoDe(n.antiguedad_horas)}"></span> ${esc(t('mercado {h}', { h: hace(n.antiguedad_horas) }))}${nota ? ' · ' + nota : ''}` : nota;
    const extra = (n.en_inventario ? `<span class="fuente mejor">${t('tienes {n}', { n: kin(n.en_inventario) })}</span>` : '')
      + (n.mejor == null ? `<span class="fuente" style="color:var(--danger)">${t('sin precio')}</span>` : '');
    return `<div class="nodo"><div class="nodo-fila">${objHTML(n.id, `${esc(nom(n.id, n.nombre))} × ${num1(n.cantidad)}`, det, 'ic-s')}
      <div class="fuentes">${f('mercado', t('mercado'), n.precio_mercado)}${f('npc', 'NPC', n.precio_npc)}${f('fabricar', t('fabricar'), n.coste_fabricar)}${extra}</div></div>
      ${n.hijos && n.hijos.length ? `<div class="nodo-hijos">${arbolHTML(n.hijos)}</div>` : ''}</div>`;
  }).join('');
}

// ================================================================== CHARACTER
const iniciales = s => (String(s || '?').trim().split(/\s+/).slice(0, 2).map(p => p[0]).join('') || '?').toUpperCase();
const rangoNivel = n => n > 50 ? t('Especialista (51–100)') : t('Principiante (1–50)');
async function cargarPersonaje() {
  await cargarPerfiles();
  const p = perfilActual();
  $('#p-perfiles').innerHTML = E.perfiles.length ? `<div class="lista-perfiles">${E.perfiles.map(x => {
    const s = x.servidor, activo = x.id === E.perfil;
    return `<div class="perfil-fila ${activo ? 'activo' : ''}"><span class="avatar">${esc(iniciales(x.nombre))}</span>
      <div class="obj-texto" style="flex:1"><span class="obj-nombre">${esc(x.nombre)}</span><span class="obj-det">${s ? `${esc(s.nombre)} · ${nombreFaccion(s.faccion)}` : `<span class="loss">${t('sin servidor')}</span>`}</span></div>
      ${activo ? `<span class="chip chip-accent">${t('Activo')}</span>` : `<button class="btn btn-t" data-usar="${esc(x.id)}">${t('Usar')}</button>`}<button class="btn btn-t" data-editar="${esc(x.id)}">${t('Editar')}</button></div>`;
  }).join('')}</div>` : avisoHTML(t('Crea tu primer perfil: primero un servidor (Servidores) y luego tu personaje.'), 'info');
  const servSel = $('#p-servidor').value;
  $('#p-servidor').innerHTML = `<option value="">${t('— sin servidor —')}</option>` + E.servidores.map(s => `<option value="${esc(s.id)}">${esc(s.nombre)} (${nombreFaccion(s.faccion)})</option>`).join('');
  $('#p-servidor').value = servSel;
  $('#s-lista').innerHTML = E.servidores.length ? `<div class="lista-perfiles">${E.servidores.map(s => `<div class="perfil-fila">
      <div class="obj-texto" style="flex:1"><span class="obj-nombre">${esc(s.nombre)}</span><span class="obj-det">${esc(s.region || '')}${s.region ? ' · ' : ''}${s.comision_registro != null ? t('comisión {p}', { p: pct(s.comision_registro) }) : t('comisión por defecto')} · ${s.impuesto_venta != null ? t('impuesto {p}', { p: pct(s.impuesto_venta) }) : t('impuesto por defecto')}</span></div>
      <span class="faccion">${nombreFaccion(s.faccion)}</span></div>`).join('')}</div>` : `<p class="ayuda">${t('Aún no hay servidores.')}</p>`;
  $('#n-perfil').textContent = p ? '· ' + p.nombre : '';
  if (!p) {
    $('#n-niveles').innerHTML = `<p class="ayuda">${t('Crea un perfil para guardar sus niveles.')}</p>`;
    $('#i-tabla').innerHTML = vacio(4, t('Crea un perfil para guardar su inventario.'));
    return;
  }
  try {
    const niveles = await api(`/api/perfiles/${encodeURIComponent(p.id)}/niveles`, { silencioso: true });
    $('#n-niveles').innerHTML = Object.keys(E.profesiones).map(k => {
      const n = niveles[k] ?? 1, prof = esc(nombreProf(k));
      return `<div class="prof"><div class="prof-cab">${iconoCat(ICONO_PROFESION[k], 'ic-s')}${prof}</div>
        <input type="number" min="1" max="100" data-prof="${k}" value="${n}" aria-label="${t('Nivel de {p}', { p: prof })}">
        <input type="range" min="1" max="100" data-rango="${k}" value="${n}" aria-label="${t('Nivel de {p} (deslizador)', { p: prof })}">
        <div class="prof-rango">${rangoNivel(n)}</div></div>`;
    }).join('');
  } catch (e) { $('#n-niveles').innerHTML = avisoHTML(esc(e.message), 'error'); }
  cargarInventario();
}
$('#p-perfiles').addEventListener('click', e => {
  const u = e.target.closest('[data-usar]');
  if (u) { cambiarPerfil(u.dataset.usar); return; }
  const ed = e.target.closest('[data-editar]');
  if (ed) { const x = E.perfiles.find(p => p.id === ed.dataset.editar); $('#p-id').value = x.id; $('#p-nombre').value = x.nombre; $('#p-servidor').value = x.servidor_id || ''; $('#p-nombre').focus(); }
});
$('#p-guardar').addEventListener('click', async () => {
  try {
    const r = await api('/api/perfiles', { method: 'POST', body: { id: $('#p-id').value || undefined, nombre: $('#p-nombre').value, servidor_id: $('#p-servidor').value || null } });
    toast(t('Perfil guardado.'), 'ok');
    $('#p-id').value = ''; $('#p-nombre').value = '';
    cambiarPerfil(E.perfil || r.id);
  } catch (_) { }
});
$('#s-guardar').addEventListener('click', async () => {
  const com = $('#s-com').value, imp = $('#s-imp').value;
  try {
    await api('/api/servidores', { method: 'POST', body: { nombre: $('#s-nombre').value, faccion: $('#s-faccion').value, region: 'EU', comision_registro: com === '' ? null : com / 100, impuesto_venta: imp === '' ? null : imp / 100 } });
    toast(t('Servidor guardado.'), 'ok');
    ['#s-nombre', '#s-com', '#s-imp'].forEach(i => { $(i).value = ''; });
    cargarPersonaje();
  } catch (_) { }
});
$('#n-niveles').addEventListener('input', e => {
  const i = e.target.closest('input[data-prof], input[data-rango]'); if (!i) return;
  const card = i.closest('.prof'), n = Math.max(1, Math.min(100, +i.value || 1));
  if (i.dataset.rango) $('input[data-prof]', card).value = n; else $('input[data-rango]', card).value = n;
  $('.prof-rango', card).textContent = rangoNivel(n);
});
$('#n-guardar').addEventListener('click', async () => {
  const p = perfilActual(); if (!p) return toast(t('Crea un perfil primero.'), 'error');
  const datos = Object.fromEntries($$('#n-niveles input[data-prof]').map(i => [i.dataset.prof, Math.max(1, Math.min(100, +i.value || 1))]));
  try { await api(`/api/perfiles/${encodeURIComponent(p.id)}/niveles`, { method: 'PUT', body: datos }); toast(t('Niveles guardados.'), 'ok'); } catch (_) { }
});

async function cargarInventario() {
  const p = perfilActual(); if (!p) return;
  try {
    const filas = await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario`, { silencioso: true });
    $('#i-tabla').innerHTML = filas.length ? filas.map(f => { const n = esc(nom(f.objeto_id, f.nombre)); return `<tr data-obj="${f.objeto_id}" data-ubic="${esc(f.ubicacion)}"><td>${objHTML(f.objeto_id, n, '', 'ic-s')}</td><td>${f.ubicacion === 'almacen' ? t('Almacén') : t('Inventario')}</td>
      <td class="num"><input type="number" min="0" value="${f.cantidad}" class="i-cant-ed" aria-label="${t('Cantidad de {o}', { o: n })}"></td><td><button class="btn btn-t" data-borrar>${t('Quitar')}</button></td></tr>`; }).join('')
      : vacio(4, t('Inventario vacío.'));
  } catch (e) { $('#i-tabla').innerHTML = vacio(4, esc(e.message)); }
}
async function guardarInv(filas) {
  const p = perfilActual(); if (!p) { toast(t('Crea un perfil primero.'), 'error'); return false; }
  try { await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario`, { method: 'PUT', body: { filas } }); return true; } catch (_) { return false; }
}
$('#i-tabla').addEventListener('change', async e => {
  const i = e.target.closest('.i-cant-ed'); if (!i) return;
  const tr = i.closest('tr');
  if (await guardarInv([{ objeto_id: +tr.dataset.obj, cantidad: +i.value || 0, ubicacion: tr.dataset.ubic }])) toast(t('Cantidad actualizada.'), 'ok');
});
$('#i-tabla').addEventListener('click', async e => {
  if (!e.target.closest('[data-borrar]')) return;
  const tr = e.target.closest('tr');
  if (await guardarInv([{ objeto_id: +tr.dataset.obj, cantidad: 0, ubicacion: tr.dataset.ubic }])) cargarInventario();
});
autocompletar($('#i-obj'));
$('#i-anadir').addEventListener('click', async () => {
  const o = $('#i-obj');
  if (!o.dataset.id) return toast(t('Elige el objeto de la lista de sugerencias.'), 'error');
  if (await guardarInv([{ objeto_id: +o.dataset.id, cantidad: +$('#i-cant').value || 0, ubicacion: $('#i-ubic').value }])) {
    toast(t('Inventario actualizado.'), 'ok'); o.value = ''; delete o.dataset.id; $('#i-cant').value = ''; cargarInventario();
  }
});
$('#i-pegar').addEventListener('click', async () => {
  const p = perfilActual(); if (!p) return toast(t('Crea un perfil primero.'), 'error');
  const cont = $('#i-pegado');
  try {
    const r = await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario/pegar`, { method: 'POST', body: { texto: $('#i-texto').value } });
    if (!r.filas.length) { cont.innerHTML = `<div style="margin-top:10px">${avisoHTML(t('No hay líneas que leer.'))}</div>`; return; }
    cont.innerHTML = `<div class="tabla-caja" style="margin-top:12px"><table><thead><tr><th>${t('Texto')}</th><th>${t('Objeto')}</th><th class="num">${t('Cantidad')}</th><th></th></tr></thead><tbody>
      ${r.filas.map(f => `<tr><td class="dim">${esc(f.texto)}</td><td><div class="ac"><input class="pg-obj" value="${esc(f.nombre ? nom(f.objeto_id, f.nombre) : '')}" ${f.objeto_id ? `data-id="${f.objeto_id}"` : ''} autocomplete="off" aria-label="${t('Objeto')}"></div></td>
        <td class="num"><input type="number" class="pg-cant" min="0" value="${f.cantidad ?? ''}" aria-label="${t('Cantidad')}"></td>
        <td>${f.dudosa ? `<span class="chip chip-warn">${t('revisar')}</span>` : `<span class="chip chip-gain">${Math.round(f.puntuacion)} %</span>`}</td></tr>`).join('')}
      </tbody></table></div>
      <div class="fila" style="margin-top:12px"><div class="auto"><label for="pg-ubic">${t('Guardar en')}</label><select id="pg-ubic"><option value="inventario">${t('Inventario')}</option><option value="almacen">${t('Almacén')}</option></select></div>
      <div class="auto"><button class="btn btn-p" id="pg-guardar">${t('Guardar las filas con objeto y cantidad')}</button></div></div>`;
    $$('.pg-obj', cont).forEach(i => autocompletar(i));
    $('#pg-guardar', cont).onclick = async () => {
      const ubic = $('#pg-ubic', cont).value;
      const filas = $$('tbody tr', cont).map(tr => ({ id: $('.pg-obj', tr).dataset.id, c: $('.pg-cant', tr).value }))
        .filter(f => f.id && f.c !== '').map(f => ({ objeto_id: +f.id, cantidad: +f.c, ubicacion: ubic }));
      if (!filas.length) return toast(t('Ninguna fila tiene objeto y cantidad.'), 'error');
      if (await guardarInv(filas)) { toast(t('{n} objeto(s) guardados.', { n: filas.length }), 'ok'); cont.innerHTML = ''; $('#i-texto').value = ''; cargarInventario(); }
    };
  } catch (_) { }
});

// ================================================================== SETTINGS
async function cargarAjustes() {
  $('#a-tema').value = leerLocal('tema', 'auto');
  marcarIdioma();
  pintarIconosEstado();
  try {
    const a = E.ajustes = await api('/api/ajustes', { silencioso: true });
    $('#a-com').value = +(a.comision_registro * 100).toFixed(3);
    $('#a-imp').value = +(a.impuesto_venta * 100).toFixed(3);
    $('#a-rebaja').value = a.rebaja_listado;
    $('#a-combo').value = a.combo_fallido;
    $('#a-valinv').value = a.valorar_inventario;
    $('#a-horas').value = a.horas_precio_antiguo ?? 24;
    $('#a-tope').value = a.tope_intentos ?? 100;
    $('#a-anun').value = a.max_anuncios ?? 10;
    $('#a-tmp').value = a.tope_tmp_mb ?? 500;
  } catch (e) { toast(e.message, 'error'); }
  cargarNPC();
  await cargarEstado();
  pintarEstado();
}
$('#a-guardar').addEventListener('click', async () => {
  try {
    await api('/api/ajustes', {
      method: 'PUT', body: {
        comision_registro: (+$('#a-com').value || 0) / 100, impuesto_venta: (+$('#a-imp').value || 0) / 100,
        rebaja_listado: +$('#a-rebaja').value || 0, combo_fallido: $('#a-combo').value, valorar_inventario: $('#a-valinv').value,
        horas_precio_antiguo: +$('#a-horas').value || 24, tope_intentos: +$('#a-tope').value || 100,
        max_anuncios: +$('#a-anun').value || 10, tope_tmp_mb: +$('#a-tmp').value || 500,
      }
    });
    toast(t('Ajustes guardados.'), 'ok');
  } catch (_) { }
});
function elegirTema(v) { guardarLocal('tema', v); $('#a-tema').value = v; aplicarTema(); }
$('#a-tema').addEventListener('change', e => elegirTema(e.target.value));
$$('[data-tema-boton]').forEach(b => b.addEventListener('click', () => elegirTema(b.dataset.temaBoton)));

function pintarIconosEstado() {
  const d = ICONOS.descarga, n = Object.keys(ICONOS.of).length, est = $('#a-iconos-estado'), b = $('#a-iconos');
  const base = t('Opcional. Se descargan de metabot.gg solo en tu equipo (data/iconos) y nunca se suben a GitHub. Son propiedad de NCSOFT.');
  if (d && d.activa) { est.textContent = t('Descargando… {n} de {total}.', { n: d.hechos, total: d.total }); b.disabled = true; }
  else { est.textContent = n ? `${base} ${t('Tienes {n} objetos con icono oficial.', { n: kin(n) })}${d && d.mensaje ? ' ' + tApi(d.mensaje) : ''}` : base; b.disabled = false; }
  $('#a-iconos-uso').hidden = !n;
  $('#a-iconos-uso').value = ICONOS.usarOficiales ? 'oficiales' : 'propios';
}
$('#a-iconos').addEventListener('click', async () => {
  try { ICONOS.descarga = await api('/api/catalogo/iconos/descargar', { method: 'POST' }); } catch (_) { return; }
  pintarIconosEstado();
  if (!ICONOS.descarga.activa) return;
  clearInterval(E.pollIconos);
  E.pollIconos = setInterval(async () => {
    await cargarIconos();
    pintarIconosEstado();
    if (!ICONOS.descarga || !ICONOS.descarga.activa) { clearInterval(E.pollIconos); E.pollIconos = null; toast(tApi(ICONOS.descarga && ICONOS.descarga.mensaje) || t('Iconos descargados.'), 'ok'); }
  }, 2000);
});
$('#a-iconos-uso').addEventListener('change', e => {
  ICONOS.usarOficiales = e.target.value === 'oficiales';
  guardarLocal('iconosOficiales', ICONOS.usarOficiales);
  cargarNPC();
});

async function cargarNPC() {
  try {
    const filas = await api('/api/precios-npc', { silencioso: true });
    $('#npc-tabla').innerHTML = filas.length ? filas.map(f => { const n = esc(nom(f.objeto_id, f.nombre)); return `<tr data-obj="${f.objeto_id}"><td>${objHTML(f.objeto_id, n, '', 'ic-s')}</td>
      <td class="num"><input type="number" min="0" class="npc-ed" value="${f.precio ?? ''}" aria-label="${t('Precio NPC de {o}', { o: n })}"></td><td><span class="chip ${f.origen === 'manual' ? 'chip-accent' : ''}">${f.origen === 'manual' ? t('tuyo') : esc(nombreFuente(f.origen))}</span></td>
      <td>${f.origen === 'manual' ? `<button class="btn btn-t" data-quitar title="${t('Volver al precio del catálogo')}">${t('Quitar')}</button>` : ''}</td></tr>`; }).join('')
      : vacio(4, t('Sin precios NPC.'));
  } catch (e) { $('#npc-tabla').innerHTML = vacio(4, esc(e.message)); }
}
autocompletar($('#npc-obj'));
$('#npc-guardar').addEventListener('click', async () => {
  const o = $('#npc-obj');
  if (!o.dataset.id) return toast(t('Elige el objeto de la lista de sugerencias.'), 'error');
  try { await api('/api/precios-npc', { method: 'PUT', body: { objeto_id: +o.dataset.id, precio: $('#npc-precio').value } }); toast(t('Precio NPC guardado.'), 'ok'); o.value = ''; $('#npc-precio').value = ''; cargarNPC(); } catch (_) { }
});
$('#npc-tabla').addEventListener('change', async e => {
  const i = e.target.closest('.npc-ed'); if (!i) return;
  try { await api('/api/precios-npc', { method: 'PUT', body: { objeto_id: +i.closest('tr').dataset.obj, precio: i.value === '' ? null : i.value } }); toast(t('Precio NPC guardado.'), 'ok'); cargarNPC(); } catch (_) { }
});
$('#npc-tabla').addEventListener('click', async e => {
  if (!e.target.closest('[data-quitar]')) return;
  try { await api('/api/precios-npc', { method: 'PUT', body: { objeto_id: +e.target.closest('tr').dataset.obj, precio: null } }); cargarNPC(); } catch (_) { }
});
function pintarEstado() {
  const s = E.estado; if (!s) return;
  const nombres = { catalogo: 'Catálogo', repo: 'Base de datos', motor: 'Motor de cálculo', precio_objetivo: 'Precio objetivo', ocr: 'OCR', parser: 'Lector de filas', grabacion: 'Modo grabación', video: 'Importar vídeo', calibracion: 'Calibración', temporales: 'Limpieza de temporales' };
  const comp = Object.entries(s.componentes || {}).map(([k, v]) => `<tr><td>${esc(t(nombres[k] || k))}</td><td>${v.ok ? `<span class="chip chip-gain">${t('ok')}</span>` : `<span class="chip chip-danger">${t('no disponible')}</span>`}</td><td class="dim" style="font-size:13px">${esc(tApi(v.mensaje || ''))}</td></tr>`).join('');
  const tmp = s.temporales || {};
  const bd = s.backend === 'supabase' ? t('Supabase conectado.') : s.backend === 'local' ? t('Base de datos local (SQLite).') : t('Sin base de datos.');
  $('#a-estado').innerHTML = `<div class="pila">
    <div class="aviso info"><span class="estado-bd ${!s.backend ? 'mal' : s.en_cola ? 'cola' : 'ok'}" style="margin-top:5px"></span><span><b>${bd}</b> ${t('{n} lote(s) en cola.', { n: kin(s.en_cola ?? 0) })}</span></div>
    <div class="cifras">${cifra(t('Temporales ({n} arch.)', { n: kin(tmp.archivos ?? 0) }), `${num1(tmp.mb ?? 0)} MB`)}${cifra(t('Tope temporales'), `${tmp.tope_mb ?? '—'} MB`)}${cifra(t('Recetas'), s.catalogo ? kin(s.catalogo.recetas) : '—')}</div>
    ${s.catalogo && s.catalogo.version_cliente ? `<p class="ayuda">${t('Catálogo del cliente {v}.', { v: esc(s.catalogo.version_cliente) })}</p>` : ''}
    ${s.backend === 'local' ? `<p class="ayuda">${t('Para guardar el histórico en la nube, crea tu propio proyecto gratuito de Supabase, pon su URL y tu clave secreta en el archivo .env (guía: docs/supabase.md) y reinicia la app.')}</p>` : ''}
    <details><summary>${t('Componentes')}</summary><div class="tabla-caja"><table><tbody>${comp}</tbody></table></div></details></div>`;
}
$('#a-subir').addEventListener('click', async () => {
  try { const r = await api('/api/estado/subir-cola', { method: 'POST' }); toast(t('Subidos {n} lote(s).', { n: r.subidas }), 'ok'); E.estado = r; pintarEstado(); cargarEstado(); } catch (_) { }
});

// ------------------------------------------------------------------ profile and start-up
function cambiarPerfil(id) {
  E.perfil = id || null;
  guardarLocal('perfil', E.perfil);
  cargarPerfiles().then(() => CARGADORES[E.tab]());
}
$('#sel-perfil').addEventListener('change', e => cambiarPerfil(e.target.value));
$('#nav').addEventListener('click', e => { const b = e.target.closest('button[data-tab]'); if (b) irA(b.dataset.tab); });
window.addEventListener('hashchange', () => { const t = location.hash.slice(1); if (t !== E.tab) irA(t); });
['#f-prof', '#f-inter', '#f-usarinv'].forEach(id => $(id).addEventListener('change', cargarPanel));
['#f-inv', '#f-margen'].forEach(id => $(id).addEventListener('input', debounce(cargarPanel, 600)));
$$('[data-idioma]').forEach(b => b.addEventListener('click', () => cambiarIdioma(b.dataset.idioma)));
$('#a-idioma').addEventListener('change', e => cambiarIdioma(e.target.value));
document.addEventListener('click', e => {
  const ir = e.target.closest('[data-ir]');
  if (ir) { irA(ir.dataset.ir); return; }
  const b = e.target.closest('[data-ver-receta]');
  if (b) { cerrarCajon(); verReceta(+b.dataset.verReceta); }
});

(async function iniciar() {
  capturarEstaticos();
  pintarEstaticos();
  marcarIdioma();
  $('#marca-logo').innerHTML = iconoUI('logo', 22);
  pintarIconosUI();
  const f = leerLocal('filtros', null);
  await Promise.all([cargarEstado(), cargarIconos()]);
  llenarProfesiones();
  if (f) {
    $('#f-prof').value = f.profesion || ''; $('#f-inv').value = f.inversion_max || ''; $('#f-margen').value = f.margen_min || '';
    $('#f-inter').checked = f.incluir_intermedios !== false; $('#f-usarinv').checked = f.usar_inventario !== false;
  }
  await cargarPerfiles();
  irA(location.hash.slice(1) || 'panel');
  setInterval(cargarEstado, 60000);
})();
