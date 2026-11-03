/* Life Skill Manager - Aion 2 — SPA en JavaScript sin dependencias (Chart.js por CDN; iconos propios en iconos.js).
   Tema: la facción del servidor del perfil activo (Asmodian → Forja nocturna, Elyos → Atelier claro), salvo que
   se fuerce uno en Ajustes. */
'use strict';

// ------------------------------------------------------------------ utilidades
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
// useGrouping 'always': en es-ES, sin él, 2449 sale sin punto de miles
const NF = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0, useGrouping: 'always' });
const NF1 = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1, useGrouping: 'always' });
const NF2 = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
/* avisos de precio antiguo o sin histórico: ya los resumen el aviso de lectura y «Ojo con» */
const avisoRepetido = a => /antiguo|hist[oó]rico insuficiente/i.test(a || '');
const vale = v => v != null && isFinite(v);
const kin = v => vale(v) ? NF.format(Math.round(v)) : '—';
const num1 = v => vale(v) ? NF1.format(v) : '—';
const pct = v => vale(v) ? NF1.format(v * 100) + ' %' : '—';
const pct0 = v => vale(v) ? NF.format(v * 100) + ' %' : '—';
/* cifras grandes en corto: 3,79 M · 908 k · 12.857 */
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
  if (h == null) return 'sin datos';
  if (h < 1) return `hace ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `hace ${Math.round(h)} h`;
  return `hace ${Math.round(h / 24)} d`;
}
function haceLargo(h) {
  if (h == null) return 'sin fecha';
  if (h < 1) return `hace ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `hace ${Math.round(h)} h`;
  return `hace ${Math.round(h / 24)} días`;
}
function fecha(isoTxt) {
  if (!isoTxt) return '—';
  return new Date(isoTxt).toLocaleString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
const semaforoDe = h => h == null ? '' : h <= 6 ? 'verde' : h <= 24 ? 'ambar' : 'rojo';
const CHIP_SEMAFORO = { verde: 'chip-gain', ambar: 'chip-warn', rojo: 'chip-danger' };
const chipEdad = (s, h) => `<span class="chip ${CHIP_SEMAFORO[s] || ''}">${esc(hace(h))}</span>`;
const ESTADOS = { normal: 'normal', hundido: 'precio hundido', saturado: 'saturado', sin_datos: 'sin histórico' };
const CHIP_ESTADO = { normal: 'chip-gain', hundido: 'chip-danger', saturado: 'chip-warn' };
const nombreFaccion = f => f === 'elyos' ? 'Elyos' : 'Asmodian';

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
  catch (e) { const err = new Error('No hay conexión con la app local. ¿Sigue abierta la ventana de iniciar.bat?'); if (!silencioso) toast(err.message, 'error'); throw err; }
  const tipo = r.headers.get('content-type') || '';
  const datos = tipo.includes('json') ? await r.json() : await r.blob();
  if (!r.ok) {
    let msg = (datos && datos.detail) || `Error ${r.status}`;
    if (Array.isArray(msg)) msg = msg.map(d => d.msg).join('; ');
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
  toast('Lista copiada al portapapeles.', 'ok');
}

// ------------------------------------------------------------------ iconos
const ICONOS = { cat: {}, of: {}, descarga: null, usarOficiales: leerLocal('iconosOficiales', true) };
async function cargarIconos() {
  try {
    const r = await api('/api/catalogo/iconos', { silencioso: true });
    ICONOS.cat = r.categorias || {}; ICONOS.of = r.oficiales || {}; ICONOS.descarga = r.descarga || null;
  } catch (_) { /* sin catálogo: todo usa el icono genérico */ }
}
function iconoCat(cat, tam = '') {
  const c = ICONOS_CATEGORIA[cat] ? cat : 'otro';
  return `<span class="ic ${tam}" data-cat="${c}">${svgIcono(ICONOS_CATEGORIA[c])}</span>`;
}
function icono(oid, tam = '') {
  const cat = ICONOS.cat[oid] || 'otro', of = ICONOS.usarOficiales ? ICONOS.of[oid] : null;
  if (!of) return iconoCat(cat, tam);
  return `<span class="ic ${tam}" data-cat="${cat}"><img src="/api/iconos/${encodeURIComponent(of)}" alt="" loading="lazy"></span>`;
}
/* objeto: icono + nombre (HTML ya escapado) + detalle opcional */
function objHTML(oid, nombreHTML, detHTML = '', tam = '') {
  return `<div class="obj">${icono(oid, tam)}<div class="obj-texto"><span class="obj-nombre">${nombreHTML}</span>${detHTML ? `<span class="obj-det">${detHTML}</span>` : ''}</div></div>`;
}
function pintarIconosUI(raiz = document) {
  $$('[data-icono]', raiz).forEach(el => { if (!el.firstElementChild) el.innerHTML = iconoUI(el.dataset.icono); });
}

// autocompletar contra el catálogo
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
    lista.innerHTML = items.map((it, i) => `<button type="button" data-i="${i}" role="option">${icono(it.id)}<span class="obj-texto"><span class="obj-nombre">${esc(it.nombre)}</span><span class="obj-det">${esc(it.nombre_en || '')}${it.vinculado ? ' · vinculado' : ''}</span></span></button>`).join('');
    lista.addEventListener('mousedown', e => { const b = e.target.closest('button[data-i]'); if (b) { e.preventDefault(); elegir(+b.dataset.i); } });
    cont.appendChild(lista);
    act = -1;
  }
  function marcar() { $$('button', lista).forEach((d, i) => d.classList.toggle('sel', i === act)); }
  function elegir(i) { const it = items[i]; if (!it) return; input.value = it.nombre; input.dataset.id = it.id; cerrar(); alElegir && alElegir(it); }
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

// cajón lateral (detalle y lista de la compra)
function cerrarCajon() { $('#cajon-raiz').innerHTML = ''; document.body.style.overflow = ''; }
function abrirCajon(cabHTML, cuerpoHTML) {
  const raiz = $('#cajon-raiz');
  raiz.innerHTML = `<div class="cajon-fondo" data-cerrar></div>
    <aside class="cajon" role="dialog" aria-modal="true" tabindex="-1">
      <div class="cajon-cab"><div style="min-width:0">${cabHTML}</div><button class="btn btn-s btn-icono" data-cerrar aria-label="Cerrar">${iconoUI('cerrar', 18)}</button></div>
      <div class="cajon-cuerpo pila-grande">${cuerpoHTML}</div>
    </aside>`;
  document.body.style.overflow = 'hidden';
  $('.cajon', raiz).focus();
  return { cuerpo: $('.cajon-cuerpo', raiz), cab: $('.cajon-cab > div', raiz) };
}
$('#cajon-raiz').addEventListener('click', e => { if (e.target.closest('[data-cerrar]')) cerrarCajon(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#cajon-raiz').firstElementChild) cerrarCajon(); });

// ------------------------------------------------------------------ estado global
const E = {
  perfiles: [], servidores: [], perfil: null, profesiones: {
    herreria: 'Herrería', armadura: 'Armadura', orfebreria: 'Orfebrería', alquimia: 'Alquimia', cocina: 'Cocina'
  },
  estado: null, ajustes: null, tab: 'panel', grafico: null, ultimoHist: null, objMercado: null, recetaSel: null,
  sesionSel: null, pollCaptura: null, pollIconos: null, ultimasMercado: [], rProf: leerLocal('rProf', ''),
};
const perfilActual = () => E.perfiles.find(p => p.id === E.perfil) || null;
const servidorActual = () => (perfilActual() || {}).servidor || null;
const nombreProf = k => E.profesiones[k] || k || '';

// tema según facción (o forzado en Ajustes)
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
  catch (_) { const el = $('#estado-bd'); el.className = 'estado-bd mal'; el.title = 'Sin conexión con la app local'; return; }
  const s = E.estado, el = $('#estado-bd');
  const bd = s.backend === 'supabase' ? 'Supabase' : s.backend === 'local' ? 'Local (SQLite)' : 'sin base de datos';
  el.className = 'estado-bd ' + (!s.backend ? 'mal' : s.en_cola ? 'cola' : 'ok');
  el.title = `Base de datos: ${bd}${s.en_cola ? ` · ${s.en_cola} en cola` : ''}`;
  const c = s.componentes || {}, avisos = [];
  for (const k of ['catalogo', 'repo', 'motor']) if (c[k] && !c[k].ok) avisos.push(esc(c[k].mensaje || k));
  if (s.catalogo && s.catalogo.aviso) avisos.push(esc(s.catalogo.aviso));
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
  sel.innerHTML = E.perfiles.length ? E.perfiles.map(p => `<option value="${esc(p.id)}">${esc(p.nombre)}${p.servidor ? ` · ${esc(p.servidor.nombre)}` : ' · sin servidor'}</option>`).join('')
    : '<option value="">Crea un perfil</option>';
  sel.value = E.perfil || '';
  aplicarTema();
}

function llenarProfesiones() {
  const el = $('#f-prof'), v = el.value;
  el.innerHTML = '<option value="">Todas las profesiones</option>' + Object.entries(E.profesiones).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join('');
  el.value = v;
  $('#r-profs').innerHTML = `<button class="btn btn-s btn-chip" data-prof="">Todas</button>` + Object.entries(E.profesiones)
    .map(([k, n]) => `<button class="btn btn-s btn-chip" data-prof="${k}">${iconoCat(ICONO_PROFESION[k], 'ic-s')}${esc(n)}</button>`).join('');
  marcarProfReceta();
}
function marcarProfReceta() { $$('#r-profs [data-prof]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.prof === E.rProf))); }

// ------------------------------------------------------------------ pestañas
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
    pintarPlan(null, { avisos: [e.message] });
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
  if (!f && !(r && r.n_precios)) { titulo = 'Aún no hay precios'; det = 'Lee el mercado para empezar a calcular'; }
  else if (h == null) { titulo = 'Precios sin fecha'; det = 'Haz una lectura antes de comprar'; }
  else { titulo = `Precios de ${haceLargo(h)}`; det = fresca ? 'Recién leídos: puedes comprar con confianza' : 'Haz una lectura antes de comprar'; }
  $('#panel-lectura').innerHTML = `<div class="lectura ${fresca ? 'fresca' : ''}">${iconoUI('reloj')}<div class="lectura-texto"><div class="lectura-titulo">${titulo}</div><div class="lectura-det">${det}</div></div><button class="btn" data-ir="captura">Leer mercado</button></div>`;
}

function pintarPlan(f, r) {
  const plan = $('#panel-plan');
  pintarLectura(f, r);
  const p = perfilActual();
  if (!f) {
    const avisos = (r && r.avisos) || [];
    $('#panel-eyebrow').textContent = 'Tu plan de hoy';
    $('#panel-titular').innerHTML = avisos.length ? 'Prepara tu <span class="resalte">primer plan</span>' : 'Nada rentable <span class="resalte">con estos filtros</span>';
    $('#panel-sub').textContent = avisos[0] || 'Prueba a quitar filtros, subir tus niveles en Personaje o leer más precios del mercado.';
    plan.hidden = true; plan.innerHTML = '';
    return;
  }
  const e = f.escenario_objetivo;
  const usaObjetivo = !!(e && e.precio_objetivo != null && e.estado !== 'sin_datos');
  const precio = usaObjetivo ? e.precio_objetivo : f.precio_venta;
  const ganancia = usaObjetivo && vale(e.beneficio_total) ? e.beneficio_total : f.beneficio_total;
  const n = f.intentos_recomendados || 1;
  const unidades = vale(f.items_esperados) ? f.items_esperados * n : null;

  $('#panel-eyebrow').textContent = 'Tu plan de hoy · 3 pasos';
  $('#panel-titular').innerHTML = `Fabrica<br><span class="resalte">${esc(f.nombre)}</span><br>y gana ~${corto(ganancia)}`;
  $('#panel-sub').textContent = `${p ? p.nombre + (p.servidor ? ' · ' + p.servidor.nombre : '') + ' · ' : ''}${n} intentos · inviertes ${corto(f.inversion)} · margen ${pct0(f.margen)}`;

  const notas = [];
  (f.avisos || []).filter(a => !avisoRepetido(a)).forEach(a => notas.push(`<div class="nota">${iconoUI('alerta')}<span>${esc(a)}</span></div>`));
  if (e && e.estado && e.estado !== 'normal' && e.estado !== 'sin_datos') notas.push(`<div class="nota mala">${iconoUI('alerta')}<span>Mercado ${esc(ESTADOS[e.estado] || e.estado)}${e.aviso ? ': ' + esc(e.aviso) : ''}</span></div>`);
  else if (e && e.aviso && !avisoRepetido(e.aviso)) notas.push(`<div class="nota">${iconoUI('alerta')}<span>${esc(e.aviso)}</span></div>`);

  plan.hidden = false;
  plan.innerHTML = `
    <div class="paso" id="paso-compra"><div class="paso-cab"><span class="paso-n">1</span><span class="paso-titulo">Compra</span><span class="paso-meta num" id="paso-compra-meta">…</span></div>
      <div class="paso-lista" id="paso-compra-lista"><div class="paso-item dim">Calculando la lista…</div></div>
      <div class="paso-pie"><button class="btn btn-s" id="paso-copiar" disabled>${iconoUI('copiar', 18)} Copiar lista</button><button class="btn btn-t" id="paso-lista">Ver lista</button><span class="mas">para ${n} intentos</span></div></div>
    <div class="paso"><div class="paso-cab"><span class="paso-n">2</span><span class="paso-titulo">Fabrica</span><span class="paso-meta">${esc(f.profesion_nombre)} · nv. ${f.nivel_receta ?? '—'}</span></div>
      <div class="paso-item">${objHTML(f.producto, esc(f.nombre), `${n} intentos · éxito ${pct0(f.p_exito)}`)}</div>
      <div class="chips"><span class="chip chip-gain num">${conSigno(f.beneficio_intento)} / intento</span><span class="chip num">margen ${pct0(f.margen)}</span>${f.p_combo ? `<span class="chip num">combo ${pct0(f.p_combo)}</span>` : ''}${f.es_intermedio ? '<span class="chip">intermedio</span>' : ''}</div>
      <div class="paso-pie"><button class="btn btn-t" data-ver-receta="${f.receta_id}">Ver receta y árbol</button></div></div>
    <div class="paso"><div class="paso-cab"><span class="paso-n">3</span><span class="paso-titulo">Vende</span><span class="paso-meta num gain">${conSigno(ganancia, corto)}</span></div>
      <div class="paso-item">${objHTML(f.producto, `a <span class="num">${kin(precio)}</span> c/u`, `${usaObjetivo ? 'precio objetivo' : 'precio actual'}${unidades != null ? ` · ~${kin(unidades)} unidades` : ''}`)}</div>
      ${notas.join('')}
      <div class="paso-pie"><button class="btn btn-t" data-detalle="0">Ver detalle</button>${usaObjetivo && vale(e.precio_ya) ? `<span class="mas">vender ya: ${kin(e.precio_ya)} c/u</span>` : ''}</div></div>`;
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
  const origen = i => i.origen === 'npc' ? 'tienda NPC' : 'mercado';
  const precioTxt = i => i.comprar_por_debajo_de != null ? `por debajo de <b>${kin(i.comprar_por_debajo_de)}</b> c/u · ${origen(i)}` : `a ~<b>${kin(i.coste_unit)}</b> c/u · ${origen(i)}`;
  let html = items.slice(0, 4).map(i => `<div class="paso-item">${objHTML(i.id, `${esc(i.nombre)} × ${kin(i.cantidad)}`, precioTxt(i))}</div>`).join('');
  if (items.length > 4) html += `<span class="mas">y ${items.length - 4} más en la lista</span>`;
  if (!items.length) html = '<div class="paso-item dim">No hace falta comprar nada: lo tienes todo.</div>';
  if ((l.fabricar || []).length) html += `<div class="nota">${iconoUI('martillo')}<span>Antes fabrica: ${l.fabricar.map(x => `${esc(x.nombre)} × ${x.intentos}`).join(', ')}</span></div>`;
  if ((l.de_inventario || []).length) html += `<div class="nota" style="color:var(--gain)">${iconoUI('escudo')}<span>De tu inventario: ${l.de_inventario.map(x => `${esc(x.nombre)} × ${kin(x.cantidad)}`).join(', ')}</span></div>`;
  $('#paso-compra-lista').innerHTML = html;
  $('#paso-compra-meta').textContent = corto(l.coste_total);
  const b = $('#paso-copiar');
  b.disabled = !l.texto;
  b.onclick = () => copiar(l.texto);
}

function jugadaHTML(f, i) {
  const av = (f.avisos || []).length;
  const det = `<span class="punto ${f.semaforo || ''}" title="Precios ${esc(hace(f.antiguedad_precios_horas))}"></span>${esc(f.profesion_nombre)} · invierte ${corto(f.inversion)}${f.es_intermedio ? ' · intermedio' : ''}${av ? ` · ${av} aviso${av > 1 ? 's' : ''}` : ''}`;
  return `<button class="jugada" data-detalle="${i}"><span class="jugada-rank">${String(i + 1).padStart(2, '0')}</span>${icono(f.producto)}
    <span class="obj-texto"><span class="obj-nombre">${esc(f.nombre)}</span><span class="obj-det">${det}</span></span>
    <span class="num ${claseSigno(f.beneficio_intento)} col-intento">${conSigno(f.beneficio_intento)}</span><span class="num dim col-margen">${pct0(f.margen)}</span>
    <span class="num col-total">${conSigno(f.beneficio_total, corto)}</span><span class="col-flecha dim">${iconoUI('flecha', 18)}</span></button>`;
}
function pintarJugadas(desde) {
  const cont = $('#panel-tabla');
  const resto = filasPanel.slice(desde);
  if (!resto.length) {
    cont.innerHTML = `<div class="tarjeta vacio">${filasPanel.length ? 'No hay más recetas rentables con estos filtros.' : 'Sin oportunidades todavía. Prueba a quitar filtros o a leer más precios del mercado.'}</div>`;
    return;
  }
  cont.innerHTML = resto.slice(0, panelVer).map((f, k) => jugadaHTML(f, desde + k)).join('')
    + (resto.length > panelVer ? `<button class="btn btn-s ver-mas" id="panel-mas">Ver ${Math.min(10, resto.length - panelVer)} más (de ${resto.length - panelVer})</button>` : '');
  const mas = $('#panel-mas');
  if (mas) mas.onclick = () => { panelVer += 10; pintarJugadas(desde); };
}

async function pintarOjo(r, turno) {
  const items = [];
  (r.avisos || []).forEach(a => items.push(['rojo', esc(a)]));
  const s = servidorActual();
  if (s && r.n_precios) {
    try {
      const ult = await api('/api/mercado/ultimas?' + qs({ servidor_id: s.id, limite: 2000 }), { silencioso: true });
      if (turno !== turnoPanel) return;
      E.ultimasMercado = ult;
      const viejos = ult.filter(x => x.semaforo === 'rojo').length;
      if (viejos) items.push(['rojo', `<b>${kin(viejos)} de ${kin(ult.length)} precios</b> tienen más de 24 h. Los cálculos pueden estar desfasados.`]);
    } catch (_) { }
  }
  const vistos = new Set();
  filasPanel.slice(0, 6).forEach(f => {
    (f.avisos || []).filter(a => !avisoRepetido(a)).forEach(a => {
      const k = f.nombre + '|' + a;
      if (!vistos.has(k)) { vistos.add(k); items.push(['ambar', `<b>${esc(f.nombre)}:</b> ${esc(a)}`]); }
    });
    const e = f.escenario_objetivo;
    if (e && (e.estado === 'saturado' || e.estado === 'hundido')) items.push(['ambar', `<b>${esc(f.nombre)}:</b> mercado ${esc(ESTADOS[e.estado])}.`]);
    if (vale(f.margen) && f.margen < 0.1 && f.beneficio_total > 0) items.push(['ambar', `<b>${esc(f.nombre)}</b> deja solo un ${pct0(f.margen)} de margen.`]);
  });
  if (filasPanel.slice(0, 15).some(f => f.escenario_objetivo && f.escenario_objetivo.estado === 'sin_datos'))
    items.push(['info', 'Sin histórico suficiente en algunos productos: el precio objetivo usa el precio actual. Cada lectura del mercado lo mejora.']);
  if (turno !== turnoPanel) return;
  $('#panel-ojo').innerHTML = items.length
    ? items.slice(0, 8).map(([t, h]) => `<div class="aviso ${t === 'info' ? 'info' : ''}"><span class="punto ${t === 'info' ? '' : t}"></span><span>${h}</span></div>`).join('')
    : avisoHTML('Todo en orden: precios recientes y sin mercados saturados.', 'ok');
}

/* avisos de una receta: los de «precio antiguo» se agrupan en una sola línea */
function avisosHTML(lista) {
  const viejos = [], otros = [];
  (lista || []).forEach(a => { const m = /^Precio de (.+) antiguo \((\d+) h\)/.exec(a || ''); if (m) viejos.push(m); else otros.push(a); });
  let html = otros.map(a => `<div class="aviso"><span class="punto ambar"></span><span>${esc(a)}</span></div>`).join('');
  if (viejos.length) html += `<div class="aviso"><span class="punto rojo"></span><span><b>${viejos.length} precio${viejos.length > 1 ? 's' : ''} antiguo${viejos.length > 1 ? 's' : ''}</b> (${esc(haceLargo(Math.max(...viejos.map(m => +m[2]))))}): ${viejos.map(m => esc(m[1])).join(', ')}. Haz una lectura del mercado.</span></div>`;
  return html;
}
function cifra(et, v, clase = '') { return `<div class="cifra"><div class="cifra-et">${et}</div><div class="cifra-v ${clase}">${v}</div></div>`; }

function abrirDetallePanel(f) {
  const e = f.escenario_objetivo;
  let escenario = '';
  if (e && e.estado === 'sin_datos') {
    escenario = avisoHTML('Precio objetivo: hace falta más histórico de este producto (al menos 3 lecturas). Por ahora se usa el precio actual.', 'info');
  } else if (e && e.precio_objetivo != null) {
    escenario = `<section><h3>Vender ya o esperar al precio objetivo</h3><div class="cifras">
      ${cifra('Precio ya', kin(e.precio_ya))}${cifra('Beneficio ya', conSigno(f.beneficio_total, corto), claseSigno(f.beneficio_total))}
      ${cifra(`Precio objetivo · ${esc(ESTADOS[e.estado] || e.estado)}`, kin(e.precio_objetivo))}${cifra('Beneficio objetivo', conSigno(e.beneficio_total, corto), claseSigno(e.beneficio_total))}
      ${cifra('Tiempo de venta', e.dias_para_vender != null ? num1(e.dias_para_vender) + ' d' : '—')}</div>
      ${e.aviso ? `<div style="margin-top:10px">${avisoHTML(esc(e.aviso))}</div>` : ''}</section>`;
  } else if (e && e.aviso) escenario = avisoHTML(esc(e.aviso), 'info');
  const cab = objHTML(f.producto, `<span class="ic-nombre" style="font-size:22px">${esc(f.nombre)}</span>`,
    `${esc(f.profesion_nombre)} · nivel ${f.nivel_receta ?? '—'}${f.es_intermedio ? ' · intermedio' : ''} · precios ${esc(hace(f.antiguedad_precios_horas))}`, 'ic-l');
  const { cuerpo } = abrirCajon(cab, `
    <div class="cifras">
      ${cifra('Benef. / intento', conSigno(f.beneficio_intento), claseSigno(f.beneficio_intento))}${cifra('Margen', pct(f.margen))}
      ${cifra('Intentos', kin(f.intentos_recomendados))}${cifra('Inversión', corto(f.inversion))}
      ${cifra('Benef. total', conSigno(f.beneficio_total, corto), claseSigno(f.beneficio_total))}${cifra('Coste / intento', kin(f.coste_intento))}
      ${cifra('Precio de venta', kin(f.precio_venta))}${cifra('Equilibrio', kin(f.precio_equilibrio))}
      ${cifra('Éxito', pct(f.p_exito))}${cifra('Combo', pct(f.p_combo))}${cifra('Objetos / intento', num1(f.items_esperados))}
    </div>
    ${f.mensaje_inventario ? avisoHTML(esc(f.mensaje_inventario), 'info') : ''}
    ${avisosHTML(f.avisos)}
    ${escenario}
    <div class="fila"><div class="auto"><button class="btn btn-p" id="dp-lista">${iconoUI('carrito', 18)} Lista de la compra</button></div>
      <div class="auto"><button class="btn btn-s" data-ver-receta="${f.receta_id}">Ver receta y árbol</button></div></div>`);
  $('#dp-lista', cuerpo).onclick = () => abrirListaCompra(f.receta_id, f.intentos_recomendados);
}

async function abrirListaCompra(recetaId, intentos) {
  const { cuerpo, cab } = abrirCajon('<p class="eyebrow">Lista de la compra</p><h2>Calculando…</h2>', '<div class="vacio">Calculando…</div>');
  async function pintar(n) {
    let r;
    try { r = await api(`/api/recetas/${recetaId}/lista-compra?` + qs({ perfil_id: E.perfil, intentos: n })); }
    catch (e) { cuerpo.innerHTML = avisoHTML(esc(e.message), 'error'); return; }
    cab.innerHTML = `<p class="eyebrow">Lista de la compra</p><h2>${esc(r.nombre)}</h2><p class="ayuda">${r.intentos} intento(s) · coste estimado <b class="num">${kin(r.coste_total)}</b> Kinah</p>`;
    cuerpo.innerHTML = `
      <div class="fila"><div><label for="lc-n">Intentos</label><input type="number" min="1" id="lc-n" value="${r.intentos}"></div>
        <div class="auto"><button class="btn btn-s" id="lc-re">Recalcular</button></div>
        <div class="auto"><button class="btn btn-p" id="lc-copiar">${iconoUI('copiar', 18)} Copiar texto</button></div></div>
      <section><h3>Comprar</h3><div class="arbol">
        ${r.comprar.length ? r.comprar.map(i => `<div class="nodo-fila">${objHTML(i.id, `${esc(i.nombre)} × <span class="num">${kin(i.cantidad)}</span>`,
          `${i.origen === 'npc' ? 'tienda NPC' : 'mercado'} · ~<b>${kin(i.coste_unit)}</b> c/u${i.comprar_por_debajo_de != null ? ` · compra por debajo de <b>${kin(i.comprar_por_debajo_de)}</b>` : ''}`)}
          <span class="num" title="Coste">${kin(i.coste)}</span></div>`).join('') : '<div class="vacio">Nada que comprar: lo tienes todo.</div>'}
      </div></section>
      ${r.fabricar.length ? `<section><h3>Fabricar antes</h3><ul class="lista-plana">${r.fabricar.map(f => `<li>${esc(f.nombre)} × ${f.intentos} intento(s) · ${esc(nombreProf(f.profesion))}</li>`).join('')}</ul></section>` : ''}
      ${r.de_inventario.length ? `<section><h3>Usar de tu inventario</h3><ul class="lista-plana">${r.de_inventario.map(f => `<li>${esc(f.nombre)} × ${kin(f.cantidad)}</li>`).join('')}</ul></section>` : ''}
      <div><label for="lc-texto">Texto para pegar</label><textarea id="lc-texto" readonly>${esc(r.texto)}</textarea></div>`;
    $('#lc-re', cuerpo).onclick = () => pintar(+$('#lc-n', cuerpo).value || 1);
    $('#lc-copiar', cuerpo).onclick = () => copiar($('#lc-texto', cuerpo).value, $('#lc-texto', cuerpo));
  }
  pintar(intentos);
}

$('#tab-panel').addEventListener('click', e => {
  const d = e.target.closest('[data-detalle]');
  if (d) { const f = filasPanel[+d.dataset.detalle]; if (f) abrirDetallePanel(f); }
});

// ================================================================== MERCADO
async function cargarMercado() {
  const s = servidorActual();
  if (!s) {
    $('#mercado-servidor').textContent = 'Elige un perfil con servidor';
    $('#m-ultimas').innerHTML = vacio(6, 'Crea un perfil con servidor en Personaje.');
    $('#m-detalle').innerHTML = avisoHTML('Cada servidor tiene su propio mercado: crea un perfil con servidor en Personaje.', 'info');
    return;
  }
  try {
    E.ultimasMercado = await api('/api/mercado/ultimas?' + qs({ servidor_id: s.id, limite: 2000 }), { silencioso: true });
    pintarUltimas();
  } catch (e) { $('#m-ultimas').innerHTML = vacio(6, esc(e.message)); }
  $('#mercado-servidor').textContent = `${s.nombre} · ${nombreFaccion(s.faccion)} · ${kin(E.ultimasMercado.length)} objetos con precio`;
  if (E.objMercado) cargarObjetoMercado(E.objMercado);
  else $('#m-detalle').innerHTML = `<div class="vacio pila" style="align-items:center">${iconoCat('otro', 'ic-l')}<span>Busca un objeto arriba o pulsa una fila de «Últimas lecturas» para ver su histórico, las ofertas y el precio objetivo.</span></div>`;
}
function pintarUltimas() {
  const q = $('#m-filtro').value.trim().toLowerCase();
  const filas = E.ultimasMercado.filter(f => !q || (f.nombre || '').toLowerCase().includes(q));
  $('#m-ultimas').innerHTML = filas.length ? filas.slice(0, 500).map(f => `<tr class="clic ${E.objMercado === f.objeto_id ? 'sel' : ''}" data-obj="${f.objeto_id}">
      <td>${objHTML(f.objeto_id, esc(f.nombre), '', 'ic-s')}</td><td class="num">${kin(f.precio_min)}</td><td class="num">${kin(f.cantidad_total)}</td>
      <td class="num ocultar-movil">${f.num_anuncios ?? '—'}</td><td class="ocultar-movil"><span class="chip">${esc(f.fuente)}</span></td>
      <td>${chipEdad(f.semaforo, f.antiguedad_horas)}</td></tr>`).join('')
    : vacio(6, E.ultimasMercado.length ? 'Ningún objeto coincide.' : 'Aún no hay lecturas en este servidor.');
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
  if (!s) { cont.innerHTML = avisoHTML('Elige un perfil con servidor para ver su mercado.'); return; }
  const dias = $('#m-dias') ? $('#m-dias').value : 30;
  cont.classList.add('cargando');
  let d;
  try { d = await api(`/api/mercado/objeto/${oid}?` + qs({ servidor_id: s.id, dias }), { silencioso: true }); }
  catch (e) { cont.classList.remove('cargando'); cont.innerHTML = avisoHTML(esc(e.message), 'error'); return; }
  cont.classList.remove('cargando');
  const a = d.actual, v = d.objetivo_venta || {}, c = d.objetivo_compra || {}, o = d.objeto;
  const det = [o.nombre_en ? esc(o.nombre_en) : '', o.vinculado ? 'vinculado' : 'comerciable', d.recetas.length ? `se fabrica (${d.recetas.length} receta${d.recetas.length > 1 ? 's' : ''})` : ''].filter(Boolean).join(' · ');
  const ofertas = (a && a.ofertas) || [];
  const maxQ = Math.max(1, ...ofertas.map(([, q]) => q || 0));
  let rango = '<p class="ayuda" style="margin-top:10px">Hace falta más histórico (al menos 3 lecturas) para calcular el precio objetivo.</p>';
  if (v.rango_p25 != null && v.rango_p75 != null) {
    const p25 = v.rango_p25, p75 = v.rango_p75, rec = v.precio_recomendado;
    const ancho = Math.max(p75 - p25, Math.abs(p25) * 0.05, 1);
    const lo = Math.min(p25, rec ?? p25) - ancho * 0.6, hi = Math.max(p75, rec ?? p75) + ancho * 0.6;
    const pos = x => Math.max(0, Math.min(100, (x - lo) / (hi - lo) * 100));
    rango = `<div class="rango" style="margin-top:14px"><div class="rango-barra"><span class="tramo" style="left:${pos(p25).toFixed(1)}%;width:${(pos(p75) - pos(p25)).toFixed(1)}%"></span>${rec != null ? `<span class="marca-v" style="left:${pos(rec).toFixed(1)}%"></span>` : ''}</div>
      <div class="rango-et num"><span>p25 ${kin(p25)}</span><span>objetivo ${kin(rec)}</span><span>p75 ${kin(p75)}</span></div></div>`;
  }
  cont.innerHTML = `
    <div class="ficha">${objHTML(oid, `<span class="ic-nombre" style="font-size:24px">${esc(o.nombre)}</span>`, det, 'ic-xl')}
      <div class="ficha-precio"><div class="num">${kin(a && a.precio_min)}</div><div class="ayuda">precio mínimo · ${a ? chipEdad(a.semaforo, a.antiguedad_horas) : 'sin lecturas'}</div></div></div>
    <div class="cifras" style="margin-top:18px">
      ${cifra('En oferta', kin(a && a.cantidad_total))}${cifra('Anuncios', a && a.num_anuncios != null ? a.num_anuncios : '—')}
      ${cifra('Volumen / día', d.volumen_dia != null ? num1(d.volumen_dia) : '—')}${cifra('Compra por debajo de', kin(c.comprar_por_debajo_de))}
      ${cifra('Precio objetivo', kin(v.precio_recomendado), 'gain')}</div>
    ${v.aviso ? `<div style="margin-top:12px">${avisoHTML(esc(v.aviso))}</div>` : ''}${c.aviso && c.estado === 'oportunidad' ? `<div style="margin-top:12px">${avisoHTML(esc(c.aviso), 'ok')}</div>` : ''}
    ${d.aviso_objetivo ? `<div style="margin-top:12px">${avisoHTML(esc(d.aviso_objetivo), 'error')}</div>` : ''}
    <div class="fila" style="margin-top:16px"><div class="auto"><label for="m-dias">Histórico</label>
      <select id="m-dias">${[7, 30, 90, 365].map(n => `<option value="${n}" ${n == d.dias ? 'selected' : ''}>${n} días</option>`).join('')}</select></div>
      <div class="auto"><button class="btn btn-s" id="m-a-manual">${iconoUI('etiqueta', 18)} Apuntar precio</button></div>
      ${d.recetas.length ? `<div class="auto"><button class="btn btn-s" data-ver-receta="${d.recetas[0].id}">Ver su receta</button></div>` : ''}</div>
    <div class="grafico" style="margin-top:14px">${d.historico.length ? '<canvas id="m-grafico" aria-label="Histórico de precio y unidades en oferta"></canvas>' : '<div class="vacio">Sin histórico en este periodo.</div>'}</div>
    <div class="g2" style="margin-top:18px">
      <div><h3>Ofertas ahora</h3>${ofertas.length ? `<div class="profundidad" style="margin-top:10px">${ofertas.slice(0, 8).map(([p, q]) => `<div class="prof-fila"><span class="num">${kin(p)}</span><div class="prof-barra"><span style="width:${Math.round((q || 0) / maxQ * 100)}%"></span></div><span class="num dim" style="text-align:right">${kin(q)}</span></div>`).join('')}</div>` : '<p class="ayuda" style="margin-top:10px">La última lectura no trae el libro de ofertas.</p>'}</div>
      <div><h3>Precio objetivo de venta ${v.estado ? `<span class="chip ${CHIP_ESTADO[v.estado] || ''}">${esc(ESTADOS[v.estado] || v.estado)}</span>` : ''}</h3>${rango}</div>
    </div>`;
  $('#m-dias').onchange = () => cargarObjetoMercado(oid);
  $('#m-a-manual').onclick = () => { const i = $('#mm-obj'); i.value = o.nombre; i.dataset.id = oid; $('#m-manual-card').scrollIntoView({ behavior: 'smooth' }); $('#mm-precio').focus(); };
  if (d.historico.length) pintarGrafico(d.historico);
  else { if (E.grafico) E.grafico.destroy(); E.grafico = null; }
}
function colorVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function pintarGrafico(hist) {
  E.ultimoHist = hist;
  if (E.grafico) { E.grafico.destroy(); E.grafico = null; }
  const lienzo = $('#m-grafico');
  if (!lienzo) return;
  if (!window.Chart) { lienzo.replaceWith(Object.assign(document.createElement('div'), { className: 'vacio', textContent: 'No se pudo cargar Chart.js (¿sin internet?).' })); return; }
  const acento = colorVar('--accent'), suave = colorVar('--accent-soft'), linea = colorVar('--line'), apagado = colorVar('--muted'), texto = colorVar('--text'), segundo = colorVar('--gain');
  const puntos = campo => hist.filter(l => l[campo] != null).map(l => ({ x: new Date(l.fecha).getTime(), y: l[campo] }));
  const cantidades = puntos('cantidad_total');
  const series = [{ label: 'Precio mínimo', data: puntos('precio_min'), borderColor: acento, backgroundColor: suave, fill: true, yAxisID: 'y', tension: 0.25, pointRadius: 2, borderWidth: 3 }];
  if (cantidades.length) series.push({ label: 'Unidades en oferta', data: cantidades, borderColor: segundo, backgroundColor: segundo, yAxisID: 'y2', tension: 0.25, pointRadius: 0, borderWidth: 1.5, borderDash: [4, 4] });
  Chart.defaults.font.family = colorVar('--font-body');
  E.grafico = new Chart(lienzo, {
    type: 'line',
    data: { datasets: series },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { type: 'linear', ticks: { color: apagado, maxTicksLimit: 8, callback: v => new Date(v).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' }) }, grid: { color: linea } },
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
  if (!s) return toast('Elige un perfil con servidor.', 'error');
  if (!obj.dataset.id) return toast('Elige el objeto de la lista de sugerencias.', 'error');
  const oid = +obj.dataset.id;
  try {
    const r = await api('/api/mercado/manual', {
      method: 'POST', body: {
        servidor_id: s.id, objeto_id: oid, precio_min: $('#mm-precio').value || null,
        cantidad_total: $('#mm-cant').value || null, num_anuncios: $('#mm-anun').value || null, ofertas_texto: $('#mm-ofertas').value,
      }
    });
    toast(r.en_cola ? 'Guardado en la cola offline (se subirá al reconectar).' : 'Lectura guardada.', 'ok');
    ['#mm-precio', '#mm-cant', '#mm-anun', '#mm-ofertas'].forEach(id => { $(id).value = ''; });
    E.objMercado = oid;
    cargarMercado();
  } catch (_) { }
});

// ================================================================== CAPTURA
async function cargarCaptura() {
  await refrescarCaptura();
  cargarCalibracion();
}
function pararPoll() { if (E.pollCaptura) { clearInterval(E.pollCaptura); E.pollCaptura = null; } }
const CHIP_SESION = { revision: ['chip-warn', 'Por revisar'], terminada: ['chip-gain', 'Guardada'], error: ['chip-danger', 'Error'] };
async function refrescarCaptura() {
  let st;
  try { st = await api('/api/captura/estado', { silencioso: true }); } catch (e) { $('#c-sesiones').innerHTML = vacio(7, esc(e.message)); return; }
  const g = st.grabacion, terminar = $('#c-terminar');
  $('#c-empezar').disabled = st.grabando;
  terminar.disabled = !st.grabando;
  terminar.classList.toggle('btn-d', !!st.grabando); terminar.classList.toggle('btn-s', !st.grabando);
  $('#c-estado-grab').innerHTML = st.grabando
    ? `<span class="punto vivo"></span> Leyendo… ${g ? `${Math.round(g.segundos || 0)} s · ${g.fotogramas_procesados ?? 0} pantallas distintas · ${g.filas_leidas ?? 0} filas` : ''}${g && g.error ? ` <span class="loss">${esc(g.error)}</span>` : ''}`
    : '';
  const ses = st.sesiones || [];
  $('#c-sesiones').innerHTML = ses.length ? ses.map(s => {
    const prog = Math.round((s.progreso || 0) * 100);
    const est = s.estado === 'procesando' ? `<div class="progreso" title="${prog} %"><span style="width:${prog}%"></span></div>`
      : CHIP_SESION[s.estado] ? `<span class="chip ${CHIP_SESION[s.estado][0]}">${CHIP_SESION[s.estado][1]}</span>` : esc(s.estado);
    const origen = { grabacion: 'Grabación', video: 'Vídeo', imagen: 'Captura' }[s.origen] || s.origen;
    return `<tr class="${E.sesionSel === s.id ? 'sel' : ''}"><td>${fecha(s.creada)}</td><td>${origen}${s.nombre_archivo ? ` <span class="dim">${esc(s.nombre_archivo)}</span>` : ''}</td><td>${est}</td>
      <td class="num">${s.n_filas}</td><td class="num">${s.n_dudosas}</td><td class="dim ocultar-movil">${esc(s.error || s.mensaje || '')}</td>
      <td>${s.estado === 'revision' ? `<button class="btn btn-p" data-revisar="${s.id}">Revisar</button>` : s.n_filas ? `<button class="btn btn-s" data-revisar="${s.id}">Ver</button>` : ''}</td></tr>`;
  }).join('') : vacio(7, 'Todavía no hay lecturas.');
  const activo = st.grabando || ses.some(s => s.estado === 'procesando');
  if (activo && !E.pollCaptura) E.pollCaptura = setInterval(refrescarCaptura, 2000);
  if (!activo) pararPoll();
  if (E.sesionSel && ses.some(s => s.id === E.sesionSel && s.estado !== 'procesando') && !$('#c-revision').dataset.cargada) verSesion(E.sesionSel);
}
$('#c-empezar').addEventListener('click', async () => {
  const s = servidorActual();
  if (!s) return toast('Elige un perfil con servidor: las lecturas van al mercado de ese servidor.', 'error');
  try { await api('/api/captura/grabacion/iniciar', { method: 'POST', body: { servidor_id: s.id } }); toast('Lectura en marcha: cambia al juego y recorre el mercado.', 'ok'); }
  catch (_) { }
  refrescarCaptura();
});
$('#c-terminar').addEventListener('click', async () => {
  $('#c-terminar').disabled = true;
  try {
    const r = await api('/api/captura/grabacion/detener', { method: 'POST' });
    toast(r.estado === 'revision' ? `Lectura terminada: ${r.n_dudosas} fila(s) para revisar.` : (r.mensaje || 'Lectura terminada.'), r.estado === 'error' ? 'error' : 'ok');
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
  if (!s) return toast('Elige un perfil con servidor antes de subir.', 'error');
  for (const f of archivos) {
    toast(`Subiendo ${f.name}…`);
    try {
      const r = await api('/api/captura/subir?' + qs({ nombre: f.name, servidor_id: s.id }), { method: 'POST', cuerpoCrudo: f });
      E.sesionSel = r.id; $('#c-revision').dataset.cargada = '';
      toast(`${f.name}: procesando…`, 'ok');
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
  cont.innerHTML = `<div class="pila" style="margin-top:22px"><div class="cab-tarjeta"><h3>Revisión · ${s.n_filas} filas (${s.n_dudosas} dudosas)</h3>
      <label class="check"><input type="checkbox" id="c-todas" ${mostrarTodas ? 'checked' : ''}> Mostrar también las correctas</label>
      ${enRevision ? '<p class="ayuda">Corrige el objeto, precio o cantidad y pulsa ✓; o descarta la fila con ✕. Al guardar, las filas que sigan pendientes se descartan.</p>' : ''}</div>
    <div class="tabla-caja alta"><table><thead><tr><th>Imagen / leído</th><th>Objeto</th><th class="num">Precio</th><th class="num">Cantidad</th><th class="ocultar-movil">Motivo</th><th>Estado</th><th></th></tr></thead><tbody>
    ${filas.length ? filas.map(f => `<tr data-idx="${f.idx}">
      <td>${f.recorte ? `<img class="recorte" loading="lazy" src="/api/captura/sesiones/${s.id}/filas/${f.idx}/recorte" alt="Recorte de la fila leída">` : ''}<span class="dim">${esc(f.nombre_leido)}</span></td>
      <td><div class="ac"><input class="r-obj" value="${esc(f.nombre || '')}" data-id="${f.objeto_id ?? ''}" ${enRevision ? '' : 'disabled'} placeholder="Elige objeto…" autocomplete="off" aria-label="Objeto"></div></td>
      <td class="num"><input class="r-precio" type="number" value="${f.precio ?? ''}" ${enRevision ? '' : 'disabled'} aria-label="Precio"></td>
      <td class="num"><input class="r-cant" type="number" value="${f.cantidad ?? ''}" ${enRevision ? '' : 'disabled'} aria-label="Cantidad"></td>
      <td class="dim ocultar-movil" style="font-size:13px">${esc((f.motivos || []).join('; '))}${f.confianza != null ? ` (${Math.round(f.confianza * 100)} %)` : ''}</td>
      <td>${CHIP_FILA[f.estado] ? `<span class="chip ${CHIP_FILA[f.estado][0]}">${CHIP_FILA[f.estado][1]}</span>` : esc(f.estado)}</td>
      <td style="white-space:nowrap">${enRevision ? `<button class="btn btn-g btn-icono" data-acc="confirmar" title="Confirmar" aria-label="Confirmar">✓</button> <button class="btn btn-d btn-icono" data-acc="descartar" title="Descartar" aria-label="Descartar">✕</button>` : ''}</td></tr>`).join('') : vacio(7, 'No hay filas dudosas.')}
    </tbody></table></div>
    ${enRevision ? `<div><button class="btn btn-p" id="c-guardar-sesion">Guardar sesión (${s.n_ok} correctas)</button></div>` : ''}</div>`;
  $$('.r-obj', cont).forEach(i => { if (i.dataset.id === '') delete i.dataset.id; autocompletar(i); });
  $('#c-todas', cont).onchange = e => { guardarLocal('verTodas', e.target.checked); verSesion(id); };
  const g = $('#c-guardar-sesion', cont);
  if (g) g.onclick = async () => {
    try { const r = await api(`/api/captura/sesiones/${id}/guardar`, { method: 'POST' }); toast(r.mensaje || 'Sesión guardada.', 'ok'); }
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
    if (!obj.dataset.id) return toast('Elige el objeto correcto de la lista de sugerencias.', 'error');
    Object.assign(datos, { objeto_id: +obj.dataset.id, precio: $('.r-precio', tr).value, cantidad: $('.r-cant', tr).value });
  }
  try { await api(`/api/captura/sesiones/${E.sesionSel}/filas/${idx}`, { method: 'POST', body: datos }); verSesion(E.sesionSel); refrescarCaptura(); }
  catch (_) { }
});

// --- calibración
const CAL = { img: null, ancho: 0, alto: 0, lista: null, columnas: {}, arrastre: null };
const COLORES_CAL = { lista: '#4BE3A8', nombre: '#6FD3FF', precio: '#FFB547', cantidad: '#B9A7FF' };
async function cargarCalibracion() {
  try {
    const c = await api('/api/captura/calibracion', { silencioso: true });
    const res = c.resolucion, act = c.actual;
    const calibrada = act && act.calibrada;
    $('#cal-chip').innerHTML = res ? `<span class="chip ${calibrada ? 'chip-gain' : 'chip-warn'}">${res[0]} × ${res[1]} ${calibrada ? 'calibrada' : 'sin calibrar'}</span>` : '';
    $('#cal-info').innerHTML = res ? (calibrada ? `Zona de lectura: ${act.lista.join(', ')}.` : 'Sin calibrar: se lee la pantalla completa (más lento y con más errores).') : esc(c.aviso || '');
    CAL.guardada = c.datos;
  } catch (e) { $('#cal-info').textContent = e.message; }
}
$('#cal-pantalla').addEventListener('click', async () => {
  const b = $('#cal-pantalla'), txt = $('span:last-child', b);
  b.disabled = true;
  let n = 5; txt.textContent = `Cambia al juego… ${n}`;
  const t = setInterval(() => { n--; if (n > 0) txt.textContent = `Cambia al juego… ${n}`; }, 1000);
  try {
    const r = await fetch('/api/captura/calibracion/pantalla?espera=5', { method: 'POST' });
    if (!r.ok) throw new Error((await r.json()).detail || 'No se pudo capturar la pantalla');
    const ancho = +r.headers.get('X-Ancho'), alto = +r.headers.get('X-Alto');
    cargarImagenCal(URL.createObjectURL(await r.blob()), ancho, alto);
  } catch (e) { toast(e.message, 'error'); }
  finally { clearInterval(t); b.disabled = false; txt.textContent = 'Capturar pantalla (5 s)'; }
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
    $('#cal-info').innerHTML = `Imagen ${CAL.ancho}×${CAL.alto}. Arrastra para marcar la <b>zona de la lista</b>${conf ? ' (ya había una calibración para esta resolución)' : ''}.`;
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
    caja(x, y, w, h, COLORES_CAL.lista, 'Lista');
    for (const [col, [x0, x1]] of Object.entries(CAL.columnas || {})) caja(x0, y, x1 - x0, h, COLORES_CAL[col] || '#ffffff', col);
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
    toast('Calibración guardada.', 'ok');
    cargarCalibracion();
  } catch (_) { }
});

// ================================================================== RECETAS
async function cargarRecetas() {
  const cont = $('#r-lista');
  cont.classList.add('cargando');
  try {
    const r = await api('/api/recetas?' + qs({ perfil_id: E.perfil, q: $('#r-q').value.trim(), profesion: E.rProf, solo_desbloqueadas: $('#r-desb').checked, limite: 400 }), { silencioso: true });
    $('#r-sub').textContent = `${kin(r.total)} recetas${r.faccion ? ` de tu facción (${nombreFaccion(r.faccion)})` : ''}${E.rProf ? ' · ' + nombreProf(E.rProf) : ''}`;
    $('#r-total').textContent = r.total > r.filas.length ? `Mostrando ${r.filas.length} de ${kin(r.total)}: afina la búsqueda.` : `${kin(r.filas.length)} recetas`;
    cont.innerHTML = r.filas.length ? r.filas.map(f => `<tr class="clic ${E.recetaSel === f.id ? 'sel' : ''}" data-receta="${f.id}">
      <td>${objHTML(f.producto, esc(f.nombre) + (f.cantidad > 1 ? ` <span class="dim">×${f.cantidad}</span>` : ''), '', 'ic-s')}</td><td class="ocultar-movil">${esc(f.profesion_nombre)}</td>
      <td class="num">${f.nivel ?? '—'}</td><td class="num ocultar-movil">${f.combo_pct ? f.combo_pct + ' %' : '—'}</td>
      <td>${f.desbloqueada ? '<span class="chip chip-gain">Desbloqueada</span>' : `<span class="chip">${iconoUI('candado', 14)} nv. ${f.nivel ?? '—'}</span>`}</td></tr>`).join('')
      : vacio(5, 'Ninguna receta coincide.');
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
  const det = `${esc(r.profesion_nombre)} · nivel ${r.nivel} · ${r.faccion === 'ambas' ? 'ambas facciones' : esc(nombreFaccion(r.faccion))} · produce ${r.cantidad || 1}${r.combo_pct ? ` · combo ${r.combo_pct} %${r.producto_combo_nombre ? ' → ' + esc(r.producto_combo_nombre) : ''}` : ''}`;
  cont.innerHTML = `<div class="pila-grande">
    ${objHTML(r.producto, `<span class="ic-nombre" style="font-size:20px">${esc(r.nombre)}</span>`, det, 'ic-l')}
    ${d.aviso ? avisoHTML(esc(d.aviso), 'error') : ''}
    ${a ? `<div class="fila"><div class="auto"><label for="rd-n">Intentos</label><input id="rd-n" type="number" min="1" value="${a.intentos}" style="width:110px"></div>
      <div class="auto"><button class="btn btn-s" id="rd-re">Recalcular</button></div>
      <div class="auto"><button class="btn btn-p" id="rd-lista">${iconoUI('carrito', 18)} Lista de la compra</button></div></div>
    <div class="cifras">
      ${cifra('Coste / intento', kin(a.coste_intento))}${cifra('Ingreso / intento', kin(a.ingreso_esperado))}
      ${cifra('Benef. / intento', conSigno(a.beneficio_intento), claseSigno(a.beneficio_intento))}${cifra('Margen', pct(a.margen))}
      ${cifra(`Benef. ${a.intentos} intento(s)`, conSigno(a.beneficio_total, corto), claseSigno(a.beneficio_total))}${cifra('Equilibrio', kin(a.precio_equilibrio))}
      ${cifra(`Éxito (nv. ${a.nivel})`, pct(a.p_exito))}${cifra('Combo', pct(a.p_combo))}
      ${cifra('Objetos / intento', num1(a.items_esperados))}${cifra('Intentos rentables', a.max_intentos_mercado == null ? '∞' : kin(a.max_intentos_mercado))}
    </div>
    ${a.mensaje_inventario ? avisoHTML(esc(a.mensaje_inventario), 'info') : ''}
    ${avisosHTML(a.avisos)}
    ${e_ && e_.precio_objetivo != null && e_.estado !== 'sin_datos' ? avisoHTML(`Precio objetivo de venta: <b class="num">${kin(e_.precio_objetivo)}</b> (${esc(ESTADOS[e_.estado] || e_.estado)}) → beneficio ${conSigno(e_.beneficio_total, corto)} frente a ${conSigno(a.beneficio_total, corto)} vendiendo ya a ${kin(e_.precio_ya)}.${e_.aviso ? ' ' + esc(e_.aviso) : ''}`, 'info') : ''}
    <section><h3>Ingredientes y mejor origen</h3><div class="arbol">${arbolHTML(d.arbol || [])}</div></section>
    <details><summary>Desglose por intento</summary><div class="tabla-caja"><table><thead><tr><th>Ingrediente</th><th class="num">Cant.</th><th>Origen</th><th class="num">Coste unit.</th><th class="num">Tienes</th><th class="num">Faltan</th></tr></thead><tbody>
      ${a.desglose_ingredientes.map(i => `<tr><td>${esc(i.nombre)}</td><td class="num">${num1(i.cantidad)}</td><td>${esc({ mercado: 'Mercado', npc: 'Tienda NPC', fabricar: 'Fabricar', inventario: 'Inventario' }[i.origen] || '—')}</td>
        <td class="num">${kin(i.coste_unit)}</td><td class="num">${kin(i.en_inventario)}</td><td class="num">${kin(i.faltan)}</td></tr>`).join('')}
    </tbody></table></div></details>` : ''}</div>`;
  const re = $('#rd-re'); if (re) re.onclick = () => verReceta(id, false, +$('#rd-n').value || 1);
  const li = $('#rd-lista'); if (li) li.onclick = () => abrirListaCompra(id, +$('#rd-n').value || 1);
}
function arbolHTML(nodos) {
  return nodos.map(n => {
    const f = (k, et, v) => v == null ? '' : `<span class="fuente ${n.mejor === k ? 'mejor' : ''}">${et} ${kin(v)}${n.mejor === k ? ' ✓' : ''}</span>`;
    const det = n.precio_mercado != null && n.antiguedad_horas != null
      ? `<span class="punto ${semaforoDe(n.antiguedad_horas)}"></span> mercado ${esc(hace(n.antiguedad_horas))}${n.nota ? ' · ' + esc(n.nota) : ''}` : (n.nota ? esc(n.nota) : '');
    const extra = (n.en_inventario ? `<span class="fuente mejor">tienes ${kin(n.en_inventario)}</span>` : '')
      + (n.mejor == null ? '<span class="fuente" style="color:var(--danger)">sin precio</span>' : '');
    return `<div class="nodo"><div class="nodo-fila">${objHTML(n.id, `${esc(n.nombre)} × ${num1(n.cantidad)}`, det, 'ic-s')}
      <div class="fuentes">${f('mercado', 'mercado', n.precio_mercado)}${f('npc', 'NPC', n.precio_npc)}${f('fabricar', 'fabricar', n.coste_fabricar)}${extra}</div></div>
      ${n.hijos && n.hijos.length ? `<div class="nodo-hijos">${arbolHTML(n.hijos)}</div>` : ''}</div>`;
  }).join('');
}

// ================================================================== PERSONAJE
const iniciales = t => (String(t || '?').trim().split(/\s+/).slice(0, 2).map(p => p[0]).join('') || '?').toUpperCase();
const rangoNivel = n => n > 50 ? 'Especialista (51–100)' : 'Principiante (1–50)';
async function cargarPersonaje() {
  await cargarPerfiles();
  const p = perfilActual();
  $('#p-perfiles').innerHTML = E.perfiles.length ? `<div class="lista-perfiles">${E.perfiles.map(x => {
    const s = x.servidor, activo = x.id === E.perfil;
    return `<div class="perfil-fila ${activo ? 'activo' : ''}"><span class="avatar">${esc(iniciales(x.nombre))}</span>
      <div class="obj-texto" style="flex:1"><span class="obj-nombre">${esc(x.nombre)}</span><span class="obj-det">${s ? `${esc(s.nombre)} · ${nombreFaccion(s.faccion)}` : '<span class="loss">sin servidor</span>'}</span></div>
      ${activo ? '<span class="chip chip-accent">Activo</span>' : `<button class="btn btn-t" data-usar="${esc(x.id)}">Usar</button>`}<button class="btn btn-t" data-editar="${esc(x.id)}">Editar</button></div>`;
  }).join('')}</div>` : avisoHTML('Crea tu primer perfil: primero un servidor (Servidores) y luego tu personaje.', 'info');
  $('#p-servidor').innerHTML = '<option value="">— sin servidor —</option>' + E.servidores.map(s => `<option value="${esc(s.id)}">${esc(s.nombre)} (${nombreFaccion(s.faccion)})</option>`).join('');
  $('#s-lista').innerHTML = E.servidores.length ? `<div class="lista-perfiles">${E.servidores.map(s => `<div class="perfil-fila">
      <div class="obj-texto" style="flex:1"><span class="obj-nombre">${esc(s.nombre)}</span><span class="obj-det">${esc(s.region || '')}${s.region ? ' · ' : ''}${s.comision_registro != null ? `comisión ${pct(s.comision_registro)}` : 'comisión por defecto'} · ${s.impuesto_venta != null ? `impuesto ${pct(s.impuesto_venta)}` : 'impuesto por defecto'}</span></div>
      <span class="faccion">${nombreFaccion(s.faccion)}</span></div>`).join('')}</div>` : '<p class="ayuda">Aún no hay servidores.</p>';
  $('#n-perfil').textContent = p ? '· ' + p.nombre : '';
  if (!p) {
    $('#n-niveles').innerHTML = '<p class="ayuda">Crea un perfil para guardar sus niveles.</p>';
    $('#i-tabla').innerHTML = vacio(4, 'Crea un perfil para guardar su inventario.');
    return;
  }
  try {
    const niveles = await api(`/api/perfiles/${encodeURIComponent(p.id)}/niveles`, { silencioso: true });
    $('#n-niveles').innerHTML = Object.entries(E.profesiones).map(([k, nom]) => {
      const n = niveles[k] ?? 1;
      return `<div class="prof"><div class="prof-cab">${iconoCat(ICONO_PROFESION[k], 'ic-s')}${esc(nom)}</div>
        <input type="number" min="1" max="100" data-prof="${k}" value="${n}" aria-label="Nivel de ${esc(nom)}">
        <input type="range" min="1" max="100" data-rango="${k}" value="${n}" aria-label="Nivel de ${esc(nom)} (deslizador)">
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
    toast('Perfil guardado.', 'ok');
    $('#p-id').value = ''; $('#p-nombre').value = '';
    cambiarPerfil(E.perfil || r.id);
  } catch (_) { }
});
$('#s-guardar').addEventListener('click', async () => {
  const com = $('#s-com').value, imp = $('#s-imp').value;
  try {
    await api('/api/servidores', { method: 'POST', body: { nombre: $('#s-nombre').value, faccion: $('#s-faccion').value, region: 'EU', comision_registro: com === '' ? null : com / 100, impuesto_venta: imp === '' ? null : imp / 100 } });
    toast('Servidor guardado.', 'ok');
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
  const p = perfilActual(); if (!p) return toast('Crea un perfil primero.', 'error');
  const datos = Object.fromEntries($$('#n-niveles input[data-prof]').map(i => [i.dataset.prof, Math.max(1, Math.min(100, +i.value || 1))]));
  try { await api(`/api/perfiles/${encodeURIComponent(p.id)}/niveles`, { method: 'PUT', body: datos }); toast('Niveles guardados.', 'ok'); } catch (_) { }
});

async function cargarInventario() {
  const p = perfilActual(); if (!p) return;
  try {
    const filas = await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario`, { silencioso: true });
    $('#i-tabla').innerHTML = filas.length ? filas.map(f => `<tr data-obj="${f.objeto_id}" data-ubic="${esc(f.ubicacion)}"><td>${objHTML(f.objeto_id, esc(f.nombre), '', 'ic-s')}</td><td>${f.ubicacion === 'almacen' ? 'Almacén' : 'Inventario'}</td>
      <td class="num"><input type="number" min="0" value="${f.cantidad}" class="i-cant-ed" aria-label="Cantidad de ${esc(f.nombre)}"></td><td><button class="btn btn-t" data-borrar>Quitar</button></td></tr>`).join('')
      : vacio(4, 'Inventario vacío.');
  } catch (e) { $('#i-tabla').innerHTML = vacio(4, esc(e.message)); }
}
async function guardarInv(filas) {
  const p = perfilActual(); if (!p) { toast('Crea un perfil primero.', 'error'); return false; }
  try { await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario`, { method: 'PUT', body: { filas } }); return true; } catch (_) { return false; }
}
$('#i-tabla').addEventListener('change', async e => {
  const i = e.target.closest('.i-cant-ed'); if (!i) return;
  const tr = i.closest('tr');
  if (await guardarInv([{ objeto_id: +tr.dataset.obj, cantidad: +i.value || 0, ubicacion: tr.dataset.ubic }])) toast('Cantidad actualizada.', 'ok');
});
$('#i-tabla').addEventListener('click', async e => {
  if (!e.target.closest('[data-borrar]')) return;
  const tr = e.target.closest('tr');
  if (await guardarInv([{ objeto_id: +tr.dataset.obj, cantidad: 0, ubicacion: tr.dataset.ubic }])) cargarInventario();
});
autocompletar($('#i-obj'));
$('#i-anadir').addEventListener('click', async () => {
  const o = $('#i-obj');
  if (!o.dataset.id) return toast('Elige el objeto de la lista de sugerencias.', 'error');
  if (await guardarInv([{ objeto_id: +o.dataset.id, cantidad: +$('#i-cant').value || 0, ubicacion: $('#i-ubic').value }])) {
    toast('Inventario actualizado.', 'ok'); o.value = ''; delete o.dataset.id; $('#i-cant').value = ''; cargarInventario();
  }
});
$('#i-pegar').addEventListener('click', async () => {
  const p = perfilActual(); if (!p) return toast('Crea un perfil primero.', 'error');
  const cont = $('#i-pegado');
  try {
    const r = await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario/pegar`, { method: 'POST', body: { texto: $('#i-texto').value } });
    if (!r.filas.length) { cont.innerHTML = `<div style="margin-top:10px">${avisoHTML('No hay líneas que leer.')}</div>`; return; }
    cont.innerHTML = `<div class="tabla-caja" style="margin-top:12px"><table><thead><tr><th>Texto</th><th>Objeto</th><th class="num">Cantidad</th><th></th></tr></thead><tbody>
      ${r.filas.map(f => `<tr><td class="dim">${esc(f.texto)}</td><td><div class="ac"><input class="pg-obj" value="${esc(f.nombre || '')}" ${f.objeto_id ? `data-id="${f.objeto_id}"` : ''} autocomplete="off" aria-label="Objeto"></div></td>
        <td class="num"><input type="number" class="pg-cant" min="0" value="${f.cantidad ?? ''}" aria-label="Cantidad"></td>
        <td>${f.dudosa ? '<span class="chip chip-warn">revisar</span>' : `<span class="chip chip-gain">${Math.round(f.puntuacion)} %</span>`}</td></tr>`).join('')}
      </tbody></table></div>
      <div class="fila" style="margin-top:12px"><div class="auto"><label for="pg-ubic">Guardar en</label><select id="pg-ubic"><option value="inventario">Inventario</option><option value="almacen">Almacén</option></select></div>
      <div class="auto"><button class="btn btn-p" id="pg-guardar">Guardar las filas con objeto y cantidad</button></div></div>`;
    $$('.pg-obj', cont).forEach(i => autocompletar(i));
    $('#pg-guardar', cont).onclick = async () => {
      const ubic = $('#pg-ubic', cont).value;
      const filas = $$('tbody tr', cont).map(tr => ({ id: $('.pg-obj', tr).dataset.id, c: $('.pg-cant', tr).value }))
        .filter(f => f.id && f.c !== '').map(f => ({ objeto_id: +f.id, cantidad: +f.c, ubicacion: ubic }));
      if (!filas.length) return toast('Ninguna fila tiene objeto y cantidad.', 'error');
      if (await guardarInv(filas)) { toast(`${filas.length} objeto(s) guardados.`, 'ok'); cont.innerHTML = ''; $('#i-texto').value = ''; cargarInventario(); }
    };
  } catch (_) { }
});

// ================================================================== AJUSTES
async function cargarAjustes() {
  $('#a-tema').value = leerLocal('tema', 'auto');
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
    toast('Ajustes guardados.', 'ok');
  } catch (_) { }
});
function elegirTema(v) { guardarLocal('tema', v); $('#a-tema').value = v; aplicarTema(); }
$('#a-tema').addEventListener('change', e => elegirTema(e.target.value));
$$('[data-tema-boton]').forEach(b => b.addEventListener('click', () => elegirTema(b.dataset.temaBoton)));

function pintarIconosEstado() {
  const d = ICONOS.descarga, n = Object.keys(ICONOS.of).length, est = $('#a-iconos-estado'), b = $('#a-iconos');
  const base = 'Opcional. Se descargan de metabot.gg solo en tu equipo (data/iconos) y nunca se suben a GitHub. Son propiedad de NCSOFT.';
  if (d && d.activa) { est.textContent = `Descargando… ${d.hechos} de ${d.total}.`; b.disabled = true; }
  else { est.textContent = n ? `${base} Tienes ${kin(n)} objetos con icono oficial.${d && d.mensaje ? ' ' + d.mensaje : ''}` : base; b.disabled = false; }
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
    if (!ICONOS.descarga || !ICONOS.descarga.activa) { clearInterval(E.pollIconos); E.pollIconos = null; toast(ICONOS.descarga && ICONOS.descarga.mensaje || 'Iconos descargados.', 'ok'); }
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
    $('#npc-tabla').innerHTML = filas.length ? filas.map(f => `<tr data-obj="${f.objeto_id}"><td>${objHTML(f.objeto_id, esc(f.nombre), '', 'ic-s')}</td>
      <td class="num"><input type="number" min="0" class="npc-ed" value="${f.precio ?? ''}" aria-label="Precio NPC de ${esc(f.nombre)}"></td><td><span class="chip ${f.origen === 'manual' ? 'chip-accent' : ''}">${f.origen === 'manual' ? 'tuyo' : esc(f.origen)}</span></td>
      <td>${f.origen === 'manual' ? '<button class="btn btn-t" data-quitar title="Volver al precio del catálogo">Quitar</button>' : ''}</td></tr>`).join('')
      : vacio(4, 'Sin precios NPC.');
  } catch (e) { $('#npc-tabla').innerHTML = vacio(4, esc(e.message)); }
}
autocompletar($('#npc-obj'));
$('#npc-guardar').addEventListener('click', async () => {
  const o = $('#npc-obj');
  if (!o.dataset.id) return toast('Elige el objeto de la lista de sugerencias.', 'error');
  try { await api('/api/precios-npc', { method: 'PUT', body: { objeto_id: +o.dataset.id, precio: $('#npc-precio').value } }); toast('Precio NPC guardado.', 'ok'); o.value = ''; $('#npc-precio').value = ''; cargarNPC(); } catch (_) { }
});
$('#npc-tabla').addEventListener('change', async e => {
  const i = e.target.closest('.npc-ed'); if (!i) return;
  try { await api('/api/precios-npc', { method: 'PUT', body: { objeto_id: +i.closest('tr').dataset.obj, precio: i.value === '' ? null : i.value } }); toast('Precio NPC guardado.', 'ok'); cargarNPC(); } catch (_) { }
});
$('#npc-tabla').addEventListener('click', async e => {
  if (!e.target.closest('[data-quitar]')) return;
  try { await api('/api/precios-npc', { method: 'PUT', body: { objeto_id: +e.target.closest('tr').dataset.obj, precio: null } }); cargarNPC(); } catch (_) { }
});
function pintarEstado() {
  const s = E.estado; if (!s) return;
  const nombres = { catalogo: 'Catálogo', repo: 'Base de datos', motor: 'Motor de cálculo', precio_objetivo: 'Precio objetivo', ocr: 'OCR', parser: 'Lector de filas', grabacion: 'Modo grabación', video: 'Importar vídeo', calibracion: 'Calibración', temporales: 'Limpieza de temporales' };
  const comp = Object.entries(s.componentes || {}).map(([k, v]) => `<tr><td>${esc(nombres[k] || k)}</td><td>${v.ok ? '<span class="chip chip-gain">ok</span>' : '<span class="chip chip-danger">no disponible</span>'}</td><td class="dim" style="font-size:13px">${esc(v.mensaje || '')}</td></tr>`).join('');
  const t = s.temporales || {};
  const bd = s.backend === 'supabase' ? 'Supabase conectado.' : s.backend === 'local' ? 'Base de datos local (SQLite).' : 'Sin base de datos.';
  $('#a-estado').innerHTML = `<div class="pila">
    <div class="aviso info"><span class="estado-bd ${!s.backend ? 'mal' : s.en_cola ? 'cola' : 'ok'}" style="margin-top:5px"></span><span><b>${bd}</b> ${kin(s.en_cola ?? 0)} lote(s) en cola.</span></div>
    <div class="cifras">${cifra(`Temporales (${kin(t.archivos ?? 0)} arch.)`, `${num1(t.mb ?? 0)} MB`)}${cifra('Tope temporales', `${t.tope_mb ?? '—'} MB`)}${cifra('Recetas', s.catalogo ? kin(s.catalogo.recetas) : '—')}</div>
    ${s.catalogo && s.catalogo.version_cliente ? `<p class="ayuda">Catálogo del cliente ${esc(s.catalogo.version_cliente)}.</p>` : ''}
    ${s.backend === 'local' ? `<p class="ayuda">Para guardar el histórico en la nube, crea tu propio proyecto gratuito de Supabase, pon su URL y tu clave secreta en el archivo .env (guía: docs/supabase.md) y reinicia la app.</p>` : ''}
    <details><summary>Componentes</summary><div class="tabla-caja"><table><tbody>${comp}</tbody></table></div></details></div>`;
}
$('#a-subir').addEventListener('click', async () => {
  try { const r = await api('/api/estado/subir-cola', { method: 'POST' }); toast(`Subidos ${r.subidas} lote(s).`, 'ok'); E.estado = r; pintarEstado(); cargarEstado(); } catch (_) { }
});

// ------------------------------------------------------------------ perfil y arranque
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
document.addEventListener('click', e => {
  const ir = e.target.closest('[data-ir]');
  if (ir) { irA(ir.dataset.ir); return; }
  const b = e.target.closest('[data-ver-receta]');
  if (b) { cerrarCajon(); verReceta(+b.dataset.verReceta); }
});

(async function iniciar() {
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
