/* AION 2 · Rentabilidad de artesanía — SPA en JavaScript sin dependencias (Chart.js por CDN). */
'use strict';

// ------------------------------------------------------------------ utilidades
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const NF = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
const kin = v => (v == null || !isFinite(v)) ? '—' : NF.format(Math.round(v));
const num1 = v => (v == null || !isFinite(v)) ? '—' : NF1.format(v);
const pct = v => (v == null || !isFinite(v)) ? '—' : NF1.format(v * 100) + ' %';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const signo = v => v == null ? '' : (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function hace(h) {
  if (h == null) return 'sin datos';
  if (h < 1) return `hace ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `hace ${Math.round(h)} h`;
  return `hace ${Math.round(h / 24)} d`;
}
function fecha(isoTxt) {
  if (!isoTxt) return '—';
  const d = new Date(isoTxt);
  return d.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}
const ESTADOS = { normal: 'normal', hundido: 'precio hundido', saturado: 'saturado', sin_datos: 'sin histórico' };
const semaforoHTML =(s, h) => `<span class="semaforo s-${s || 'gris'}" title="Precios ${esc(hace(h))}"></span>`;

function guardarLocal(clave, valor) { try { localStorage.setItem('aion2.' + clave, JSON.stringify(valor)); } catch (_) { } }
function leerLocal(clave, defecto) { try { const v = localStorage.getItem('aion2.' + clave); return v == null ? defecto : JSON.parse(v); } catch (_) { return defecto; } }

function toast(msg, tipo = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + tipo;
  t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), tipo === 'err' ? 8000 : 4000);
}

async function api(ruta, { method = 'GET', body, cuerpoCrudo, silencioso = false } = {}) {
  const opts = { method, headers: {} };
  if (cuerpoCrudo !== undefined) { opts.body = cuerpoCrudo; opts.headers['Content-Type'] = 'application/octet-stream'; }
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  let r;
  try { r = await fetch(ruta, opts); }
  catch (e) { const err = new Error('No hay conexión con la app local. ¿Sigue abierta la ventana de iniciar.bat?'); if (!silencioso) toast(err.message, 'err'); throw err; }
  const tipo = r.headers.get('content-type') || '';
  const datos = tipo.includes('json') ? await r.json() : await r.blob();
  if (!r.ok) {
    let msg = (datos && datos.detail) || `Error ${r.status}`;
    if (Array.isArray(msg)) msg = msg.map(d => d.msg).join('; ');
    const err = new Error(msg); err.status = r.status; err.datos = datos;
    if (!silencioso) toast(msg, 'err');
    throw err;
  }
  return datos;
}
const qs = o => Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

function avisoHTML(msg, tipo = '') { return `<div class="aviso ${tipo}">${msg}</div>`; }
function vacio(colspan, msg) { return `<tr><td colspan="${colspan}" class="vacio">${msg}</td></tr>`; }

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
    items.forEach((it, i) => {
      const d = document.createElement('div');
      d.innerHTML = `<span>${esc(it.nombre)}${it.vinculado ? ' <small>(vinculado)</small>' : ''}</span><small>${esc(it.nombre_en || '')}</small>`;
      d.addEventListener('mousedown', e => { e.preventDefault(); elegir(i); });
      lista.appendChild(d);
    });
    cont.appendChild(lista);
    act = -1;
  }
  function marcar() { $$('div', lista).forEach((d, i) => d.classList.toggle('act', i === act)); }
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

function modal(titulo, html) {
  const fondo = document.createElement('div');
  fondo.className = 'modal-fondo';
  fondo.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><h2><span>${esc(titulo)}</span><button class="btn btn-s btn-sm" data-cerrar>Cerrar</button></h2><div class="cuerpo">${html}</div></div>`;
  const cerrar = () => fondo.remove();
  fondo.addEventListener('click', e => { if (e.target === fondo || e.target.closest('[data-cerrar]')) cerrar(); });
  document.addEventListener('keydown', function esc_(e) { if (e.key === 'Escape') { cerrar(); document.removeEventListener('keydown', esc_); } });
  document.body.appendChild(fondo);
  return { fondo, cuerpo: $('.cuerpo', fondo), cerrar };
}

// ------------------------------------------------------------------ estado global
const E = {
  perfiles: [], servidores: [], perfil: null, profesiones: {
    herreria: 'Herrería', armadura: 'Armadura', orfebreria: 'Orfebrería', alquimia: 'Alquimia', cocina: 'Cocina'
  },
  estado: null, tab: 'panel', grafico: null, objMercado: null, recetaSel: null, sesionSel: null,
  pollCaptura: null, ultimasMercado: [],
};
const perfilActual = () => E.perfiles.find(p => p.id === E.perfil) || null;
const servidorActual = () => (perfilActual() || {}).servidor || null;
const nombreProf = k => E.profesiones[k] || k || '';

async function cargarEstado() {
  try {
    E.estado = await api('/api/estado', { silencioso: true });
  } catch (_) { $('#estado-bd').textContent = 'sin conexión'; return; }
  const s = E.estado, el = $('#estado-bd');
  const bd = s.backend === 'supabase' ? 'Supabase' : s.backend === 'local' ? 'Local (SQLite)' : 'sin BD';
  const cola = s.en_cola ? ` · ${s.en_cola} en cola` : '';
  el.innerHTML = `<span class="semaforo s-${s.backend ? (s.en_cola ? 'ambar' : 'verde') : 'rojo'}"></span>BD: ${bd}${cola}`;
  // avisos de módulos que faltan
  const c = s.componentes || {}, avisos = [];
  for (const k of ['catalogo', 'repo', 'motor']) if (c[k] && !c[k].ok) avisos.push(esc(c[k].mensaje || k));
  if (s.catalogo && s.catalogo.aviso) avisos.push(esc(s.catalogo.aviso));
  $('#avisos-globales').innerHTML = avisos.map(a => avisoHTML(a, 'err')).join('');
  if (s.catalogo) {
    // profesiones del catálogo
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
  sel.innerHTML = E.perfiles.length ? E.perfiles.map(p => {
    const s = p.servidor;
    return `<option value="${esc(p.id)}">${esc(p.nombre)}${s ? ` — ${esc(s.nombre)} (${s.faccion === 'elyos' ? 'Elyos' : 'Asmodian'})` : ' — sin servidor'}</option>`;
  }).join('') : '<option value="">— crea un perfil en Personaje —</option>';
  sel.value = E.perfil || '';
}

function llenarProfesiones() {
  const opciones = '<option value="">Todas</option>' + Object.entries(E.profesiones).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
  for (const id of ['#f-prof', '#r-prof']) { const el = $(id), v = el.value; el.innerHTML = opciones; el.value = v; }
}

// ------------------------------------------------------------------ pestañas
const CARGADORES = {
  panel: () => cargarPanel(), mercado: () => cargarMercado(), captura: () => cargarCaptura(),
  recetas: () => cargarRecetas(), personaje: () => cargarPersonaje(), ajustes: () => cargarAjustes(),
};
function irA(tab) {
  if (!CARGADORES[tab]) tab = 'panel';
  E.tab = tab;
  $$('#nav button').forEach(b => b.classList.toggle('activa', b.dataset.tab === tab));
  $$('.pestana').forEach(s => s.classList.toggle('activa', s.id === 'tab-' + tab));
  if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
  if (tab !== 'captura') pararPoll();
  CARGADORES[tab]();
}

// ================================================================== PANEL
let filasPanel = [];
async function cargarPanel() {
  const cuerpo = $('#panel-tabla');
  const p = perfilActual();
  $('#panel-sub').textContent = p ? `${p.nombre}${p.servidor ? ' · ' + p.servidor.nombre : ''}` : '';
  const filtros = leerFiltrosPanel();
  guardarLocal('filtros', filtros);
  cuerpo.closest('table').classList.add('cargando');
  try {
    const r = await api('/api/oportunidades?' + qs({ perfil_id: E.perfil, ...filtros }), { silencioso: true });
    filasPanel = r.filas || [];
    $('#panel-avisos').innerHTML = (r.avisos || []).map(a => avisoHTML(esc(a))).join('');
    if (!filasPanel.length) {
      cuerpo.innerHTML = vacio(10, (r.avisos || []).length ? 'Sin oportunidades todavía.' :
        'No hay recetas rentables con estos filtros y precios. Prueba a quitar filtros o a leer más precios del mercado.');
    } else {
      cuerpo.innerHTML = filasPanel.map((f, i) => filaPanelHTML(f, i)).join('');
    }
  } catch (e) {
    filasPanel = [];
    $('#panel-avisos').innerHTML = avisoHTML(esc(e.message), 'err');
    cuerpo.innerHTML = vacio(10, 'No se pudo calcular el panel.');
  } finally { cuerpo.closest('table').classList.remove('cargando'); }
}
function leerFiltrosPanel() {
  return {
    profesion: $('#f-prof').value || undefined,
    inversion_max: $('#f-inv').value || undefined,
    margen_min: $('#f-margen').value || undefined,
    incluir_intermedios: $('#f-inter').checked,
    usar_inventario: $('#f-usarinv').checked,
  };
}
function filaPanelHTML(f, i) {
  const esc_ = f.escenario_objetivo;
  let obj = '<span class="dim">—</span>';
  if (esc_ && esc_.beneficio_total != null && esc_.estado !== 'sin_datos') {
    const tag = esc_.estado === 'hundido' ? '<span class="tag tag-r">hundido</span>' : esc_.estado === 'saturado' ? '<span class="tag tag-o">saturado</span>' : '';
    obj = `<span class="${signo(esc_.beneficio_total)}">${kin(esc_.beneficio_total)}</span> ${tag}`;
  } else if (esc_ && esc_.estado === 'sin_datos') obj = '<span class="dim" title="Hace falta más histórico">sin histórico</span>';
  const avisos = (f.avisos || []).length;
  return `<tr class="clic" data-i="${i}">
    <td>${semaforoHTML(f.semaforo, f.antiguedad_precios_horas)}</td>
    <td><span class="fuerte">${esc(f.nombre)}</span>${f.es_intermedio ? ' <span class="tag tag-p" title="Es ingrediente de otras recetas">intermedio</span>' : ''}${avisos ? ` <span class="tag tag-o" title="${avisos} aviso(s)">⚠ ${avisos}</span>` : ''}</td>
    <td class="ocultar-movil">${esc(f.profesion_nombre)} <span class="dim">${f.nivel_receta ?? ''}</span></td>
    <td class="num ${signo(f.beneficio_intento)}">${kin(f.beneficio_intento)}</td>
    <td class="num ${signo(f.margen)}">${pct(f.margen)}</td>
    <td class="num">${f.intentos_recomendados ?? '—'}</td>
    <td class="num">${kin(f.inversion)}</td>
    <td class="num fuerte ${signo(f.beneficio_total)}">${kin(f.beneficio_total)}</td>
    <td class="num">${obj}</td>
    <td><button class="btn btn-s btn-sm" data-lista="${i}" title="Lista de la compra">🛒 Lista</button></td></tr>`;
}
function detallePanelHTML(f) {
  const e = f.escenario_objetivo;
  let escenario = '';
  if (e && e.estado === 'sin_datos') {
    escenario = avisoHTML('Precio objetivo: hace falta más histórico de este producto (al menos 3 lecturas) para calcularlo; por ahora se usa el precio actual.', 'info');
  } else if (e && e.precio_objetivo != null) {
    escenario = `<h3>Vender ya vs. a precio objetivo</h3>
      <div class="stats">
        <div class="stat"><div class="val">${kin(e.precio_ya)}</div><div class="lbl">Precio de venta ya</div></div>
        <div class="stat"><div class="val ${signo(f.beneficio_total)}">${kin(f.beneficio_total)}</div><div class="lbl">Beneficio vendiendo ya</div></div>
        <div class="stat"><div class="val">${kin(e.precio_objetivo)}</div><div class="lbl">Precio objetivo (${esc(ESTADOS[e.estado] || e.estado)})</div></div>
        <div class="stat"><div class="val ${signo(e.beneficio_total)}">${kin(e.beneficio_total)}</div><div class="lbl">Beneficio a precio objetivo</div></div>
        <div class="stat"><div class="val">${e.dias_para_vender != null ? num1(e.dias_para_vender) + ' d' : '—'}</div><div class="lbl">Tiempo estimado de venta</div></div>
      </div>${e.aviso ? avisoHTML(esc(e.aviso)) : ''}`;
  } else if (e && e.aviso) escenario = avisoHTML(esc(e.aviso), 'info');
  return `<div class="stats">
      <div class="stat"><div class="val">${kin(f.coste_intento)}</div><div class="lbl">Coste por intento</div></div>
      <div class="stat"><div class="val">${kin(f.precio_venta)}</div><div class="lbl">Precio de venta</div></div>
      <div class="stat"><div class="val">${kin(f.precio_equilibrio)}</div><div class="lbl">Precio de equilibrio</div></div>
      <div class="stat"><div class="val">${pct(f.p_exito)}</div><div class="lbl">Éxito</div></div>
      <div class="stat"><div class="val">${pct(f.p_combo)}</div><div class="lbl">Combo</div></div>
      <div class="stat"><div class="val">${num1(f.items_esperados)}</div><div class="lbl">Objetos por intento</div></div>
    </div>
    ${f.mensaje_inventario ? avisoHTML(esc(f.mensaje_inventario), 'info') : ''}
    ${(f.avisos || []).length ? `<ul class="avisos">${f.avisos.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}
    ${escenario}
    <div style="margin-top:10px"><button class="btn btn-s btn-sm" data-ver-receta="${f.receta_id}">Ver receta y árbol de ingredientes</button></div>`;
}
$('#panel-tabla').addEventListener('click', e => {
  const bl = e.target.closest('[data-lista]');
  if (bl) { const f = filasPanel[+bl.dataset.lista]; abrirListaCompra(f.receta_id, f.intentos_recomendados); return; }
  const br = e.target.closest('[data-ver-receta]');
  if (br) { verReceta(+br.dataset.verReceta); return; }
  const tr = e.target.closest('tr.clic');
  if (!tr) return;
  const sig = tr.nextElementSibling;
  if (sig && sig.classList.contains('detalle')) { sig.remove(); tr.classList.remove('sel'); return; }
  tr.classList.add('sel');
  tr.insertAdjacentHTML('afterend', `<tr class="detalle"><td colspan="10">${detallePanelHTML(filasPanel[+tr.dataset.i])}</td></tr>`);
});

async function abrirListaCompra(recetaId, intentos) {
  const m = modal('Lista de la compra', '<div class="vacio">Calculando…</div>');
  async function pintar(n) {
    try {
      const r = await api(`/api/recetas/${recetaId}/lista-compra?` + qs({ perfil_id: E.perfil, intentos: n }));
      m.cuerpo.innerHTML = `
        <div class="fila"><div><label>Intentos</label><input type="number" min="1" id="lc-n" value="${r.intentos}"></div>
          <div class="auto"><button class="btn btn-s" id="lc-re">Recalcular</button></div>
          <div class="auto"><button class="btn btn-p" id="lc-copiar">Copiar texto</button></div></div>
        <p class="ayuda">${esc(r.nombre)} × ${r.intentos} intento(s) · coste estimado <b>${kin(r.coste_total)}</b> Kinah</p>
        <div class="tbl-wrap"><table><thead><tr><th>Comprar</th><th class="num">Cantidad</th><th>Dónde</th><th class="num">Precio aprox.</th><th class="num">Coste</th><th class="num">Compra por debajo de</th></tr></thead><tbody>
        ${r.comprar.length ? r.comprar.map(i => `<tr><td>${esc(i.nombre)}</td><td class="num fuerte">${kin(i.cantidad)}</td><td>${i.origen === 'npc' ? 'Tienda NPC' : 'Mercado'}</td>
          <td class="num">${kin(i.coste_unit)}</td><td class="num">${kin(i.coste)}</td><td class="num">${kin(i.comprar_por_debajo_de)}</td></tr>`).join('') : vacio(6, 'Nada que comprar: lo tienes todo.')}
        </tbody></table></div>
        ${r.fabricar.length ? `<h3>Fabricar antes</h3><ul class="avisos" style="color:var(--text)">${r.fabricar.map(f => `<li>${esc(f.nombre)} × ${f.intentos} intento(s) (${esc(nombreProf(f.profesion))})</li>`).join('')}</ul>` : ''}
        ${r.de_inventario.length ? `<h3>Usar de tu inventario</h3><ul class="avisos" style="color:var(--text)">${r.de_inventario.map(f => `<li>${esc(f.nombre)} × ${kin(f.cantidad)}</li>`).join('')}</ul>` : ''}
        <textarea id="lc-texto" style="margin-top:10px" readonly>${esc(r.texto)}</textarea>`;
      $('#lc-re', m.cuerpo).onclick = () => pintar(+$('#lc-n', m.cuerpo).value || 1);
      $('#lc-copiar', m.cuerpo).onclick = async () => {
        const t = $('#lc-texto', m.cuerpo);
        try { await navigator.clipboard.writeText(t.value); } catch (_) { t.select(); document.execCommand('copy'); }
        toast('Lista copiada', 'ok');
      };
    } catch (e) { m.cuerpo.innerHTML = avisoHTML(esc(e.message), 'err'); }
  }
  pintar(intentos);
}

// ================================================================== MERCADO
async function cargarMercado() {
  const s = servidorActual();
  $('#mercado-servidor').textContent = s ? `${s.nombre} (${s.faccion === 'elyos' ? 'Elyos' : 'Asmodian'})` : 'elige un perfil con servidor';
  if (!s) { $('#m-ultimas').innerHTML = vacio(6, 'Crea un perfil con servidor en Personaje.'); return; }
  try {
    E.ultimasMercado = await api('/api/mercado/ultimas?' + qs({ servidor_id: s.id, limite: 2000 }), { silencioso: true });
    pintarUltimas();
  } catch (e) { $('#m-ultimas').innerHTML = vacio(6, esc(e.message)); }
  if (E.objMercado) cargarObjetoMercado(E.objMercado);
}
function pintarUltimas() {
  const q = $('#m-filtro').value.trim().toLowerCase();
  const filas = E.ultimasMercado.filter(f => !q || (f.nombre || '').toLowerCase().includes(q));
  $('#m-ultimas').innerHTML = filas.length ? filas.slice(0, 500).map(f => `<tr class="clic" data-obj="${f.objeto_id}">
      <td>${esc(f.nombre)}</td><td class="num">${kin(f.precio_min)}</td><td class="num">${kin(f.cantidad_total)}</td>
      <td class="num ocultar-movil">${f.num_anuncios ?? '—'}</td><td><span class="tag tag-gris">${esc(f.fuente)}</span></td>
      <td>${semaforoHTML(f.semaforo, f.antiguedad_horas)}${esc(hace(f.antiguedad_horas))}</td></tr>`).join('')
    : vacio(6, E.ultimasMercado.length ? 'Ningún objeto coincide.' : 'Aún no hay lecturas en este servidor.');
}
$('#m-filtro').addEventListener('input', debounce(pintarUltimas, 150));
$('#m-ultimas').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-obj]');
  if (tr) { cargarObjetoMercado(+tr.dataset.obj); window.scrollTo({ top: 0, behavior: 'smooth' }); }
});
autocompletar($('#m-buscar'), it => cargarObjetoMercado(it.id));

async function cargarObjetoMercado(oid) {
  E.objMercado = oid;
  const s = servidorActual(), cont = $('#m-detalle');
  if (!s) { cont.innerHTML = avisoHTML('Elige un perfil con servidor para ver su mercado.'); return; }
  cont.innerHTML = '<div class="vacio">Cargando…</div>';
  let d;
  try { d = await api(`/api/mercado/objeto/${oid}?` + qs({ servidor_id: s.id, dias: $('#m-dias') ? $('#m-dias').value : 30 }), { silencioso: true }); }
  catch (e) { cont.innerHTML = avisoHTML(esc(e.message), 'err'); return; }
  const a = d.actual, v = d.objetivo_venta || {}, c = d.objetivo_compra || {};
  const estadoTag = { normal: 'tag-g', hundido: 'tag-r', saturado: 'tag-o', sin_datos: 'tag-gris' }[v.estado] || 'tag-gris';
  cont.innerHTML = `
    <h3 style="font-size:1.05rem;margin-top:14px">${esc(d.objeto.nombre)} <span class="dim" style="font-weight:400;font-size:.8rem">${esc(d.objeto.nombre_en || '')}</span>
      ${d.objeto.vinculado ? '<span class="tag tag-o">vinculado</span>' : ''}</h3>
    <div class="stats">
      <div class="stat"><div class="val">${kin(a && a.precio_min)}</div><div class="lbl">Precio mínimo</div></div>
      <div class="stat"><div class="val">${kin(a && a.cantidad_total)}</div><div class="lbl">Unidades en oferta</div></div>
      <div class="stat"><div class="val">${a && a.num_anuncios != null ? a.num_anuncios : '—'}</div><div class="lbl">Anuncios</div></div>
      <div class="stat"><div class="val" style="font-size:1rem">${a ? semaforoHTML(a.semaforo, a.antiguedad_horas) + esc(hace(a.antiguedad_horas)) : '—'}</div><div class="lbl">Última lectura</div></div>
      <div class="stat"><div class="val">${d.volumen_dia != null ? num1(d.volumen_dia) : '—'}</div><div class="lbl">Volumen estimado / día</div></div>
      <div class="stat"><div class="val pos">${kin(v.precio_recomendado)}</div><div class="lbl">Precio objetivo de venta <span class="tag ${estadoTag}">${esc(ESTADOS[v.estado] || v.estado || '—')}</span></div></div>
      <div class="stat"><div class="val">${kin(c.comprar_por_debajo_de)}</div><div class="lbl">Comprar por debajo de</div></div>
      <div class="stat"><div class="val" style="font-size:1rem">${v.rango_p25 != null ? `${kin(v.rango_p25)} – ${kin(v.rango_p75)}` : '—'}</div><div class="lbl">Rango normal (P25–P75)</div></div>
    </div>
    ${v.aviso ? avisoHTML(esc(v.aviso)) : ''}${c.aviso && c.estado === 'oportunidad' ? avisoHTML(esc(c.aviso), 'ok') : ''}
    ${d.aviso_objetivo ? avisoHTML(esc(d.aviso_objetivo), 'err') : ''}
    <div class="fila" style="margin:8px 0"><div class="auto"><label for="m-dias">Histórico</label>
      <select id="m-dias">${[7, 30, 90, 365].map(n => `<option value="${n}" ${n == d.dias ? 'selected' : ''}>${n} días</option>`).join('')}</select></div>
      <div class="auto"><button class="btn btn-s" id="m-a-manual">Apuntar precio de este objeto</button></div>
      ${d.recetas.length ? `<div class="auto"><button class="btn btn-s" data-ver-receta="${d.recetas[0].id}">Ver su receta</button></div>` : ''}</div>
    <div style="position:relative;height:280px">${d.historico.length ? '<canvas id="m-grafico"></canvas>' : '<div class="vacio">Sin histórico en este periodo.</div>'}</div>
    ${a && a.ofertas && a.ofertas.length ? `<h3>Libro de ofertas (última lectura)</h3><div class="tbl-wrap" style="max-height:240px"><table><thead><tr><th class="num">Precio</th><th class="num">Cantidad</th></tr></thead><tbody>
      ${a.ofertas.map(([p, q]) => `<tr><td class="num">${kin(p)}</td><td class="num">${kin(q)}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
  $('#m-dias').onchange = () => cargarObjetoMercado(oid);
  $('#m-a-manual').onclick = () => { const i = $('#mm-obj'); i.value = d.objeto.nombre; i.dataset.id = oid; $('#mm-precio').focus(); $('#m-manual-card').scrollIntoView({ behavior: 'smooth' }); };
  const br = $('[data-ver-receta]', cont); if (br) br.onclick = () => verReceta(+br.dataset.verReceta);
  if (d.historico.length) pintarGrafico(d.historico);
}
function pintarGrafico(hist) {
  if (E.grafico) { E.grafico.destroy(); E.grafico = null; }
  const lienzo = $('#m-grafico');
  if (!window.Chart) { lienzo.replaceWith(Object.assign(document.createElement('div'), { className: 'vacio', textContent: 'No se pudo cargar Chart.js (¿sin internet?).' })); return; }
  const puntos = campo => hist.filter(l => l[campo] != null).map(l => ({ x: new Date(l.fecha).getTime(), y: l[campo] }));
  const cantidades = puntos('cantidad_total');
  const series = [{ label: 'Precio mínimo', data: puntos('precio_min'), borderColor: '#6c9fff', backgroundColor: '#6c9fff', yAxisID: 'y', tension: .2, pointRadius: 3 }];
  if (cantidades.length) series.push({ label: 'Unidades en oferta', data: cantidades, borderColor: '#fbbf24', backgroundColor: '#fbbf24', yAxisID: 'y2', tension: .2, pointRadius: 2, borderDash: [4, 3] });
  E.grafico = new Chart(lienzo, {
    type: 'line',
    data: { datasets: series },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { type: 'linear', ticks: { color: '#8a95b0', callback: v => new Date(v).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' }) }, grid: { color: '#2a3456' } },
        y: { position: 'left', ticks: { color: '#6c9fff', callback: v => NF.format(v) }, grid: { color: '#2a3456' } },
        y2: { display: cantidades.length > 0, position: 'right', ticks: { color: '#fbbf24', callback: v => NF.format(v) }, grid: { display: false } },
      },
      plugins: {
        legend: { labels: { color: '#e2e8f0' } },
        tooltip: { callbacks: { title: items => fecha(new Date(items[0].parsed.x).toISOString()), label: c => `${c.dataset.label}: ${NF.format(c.parsed.y)}` } },
      },
    },
  });
}
autocompletar($('#mm-obj'));
$('#mm-guardar').addEventListener('click', async () => {
  const s = servidorActual(), obj = $('#mm-obj');
  if (!s) return toast('Elige un perfil con servidor.', 'err');
  if (!obj.dataset.id) return toast('Elige el objeto de la lista de sugerencias.', 'err');
  try {
    const r = await api('/api/mercado/manual', {
      method: 'POST', body: {
        servidor_id: s.id, objeto_id: +obj.dataset.id, precio_min: $('#mm-precio').value || null,
        cantidad_total: $('#mm-cant').value || null, num_anuncios: $('#mm-anun').value || null, ofertas_texto: $('#mm-ofertas').value,
      }
    });
    toast(r.en_cola ? 'Guardado en la cola offline (se subirá al reconectar).' : 'Lectura guardada.', 'ok');
    ['#mm-precio', '#mm-cant', '#mm-anun', '#mm-ofertas'].forEach(id => $(id).value = '');
    cargarMercado();
    if (!E.objMercado || E.objMercado !== +obj.dataset.id) cargarObjetoMercado(+obj.dataset.id);
  } catch (_) { }
});

// ================================================================== CAPTURA
async function cargarCaptura() {
  await refrescarCaptura();
  cargarCalibracion();
}
function pararPoll() { if (E.pollCaptura) { clearInterval(E.pollCaptura); E.pollCaptura = null; } }
async function refrescarCaptura() {
  let st;
  try { st = await api('/api/captura/estado', { silencioso: true }); } catch (e) { $('#c-sesiones').innerHTML = vacio(7, esc(e.message)); return; }
  const g = st.grabacion;
  $('#c-empezar').disabled = st.grabando;
  $('#c-terminar').disabled = !st.grabando;
  $('#c-estado-grab').innerHTML = st.grabando
    ? `<span class="punto-rec"></span> Leyendo… ${g ? `${Math.round(g.segundos || 0)} s · ${g.fotogramas_procesados ?? 0} pantallas distintas · ${g.filas_leidas ?? 0} filas` : ''}${g && g.error ? ` <span class="neg">${esc(g.error)}</span>` : ''}`
    : '';
  const ses = st.sesiones || [];
  $('#c-sesiones').innerHTML = ses.length ? ses.map(s => {
    const est = { procesando: `<div class="progreso" title="${Math.round((s.progreso || 0) * 100)} %"><div style="width:${Math.round((s.progreso || 0) * 100)}%"></div></div>`, revision: '<span class="tag tag-o">por revisar</span>', terminada: '<span class="tag tag-g">guardada</span>', error: '<span class="tag tag-r">error</span>' }[s.estado] || esc(s.estado);
    const origen = { grabacion: 'Grabación', video: 'Vídeo', imagen: 'Captura' }[s.origen] || s.origen;
    return `<tr class="${E.sesionSel === s.id ? 'sel' : ''}"><td>${fecha(s.creada)}</td><td>${origen}${s.nombre_archivo ? ` <span class="dim">${esc(s.nombre_archivo)}</span>` : ''}</td><td>${est}</td>
      <td class="num">${s.n_filas}</td><td class="num">${s.n_dudosas}</td><td class="dim">${esc(s.error || s.mensaje || '')}</td>
      <td>${s.estado === 'revision' ? `<button class="btn btn-p btn-sm" data-revisar="${s.id}">Revisar</button>` : s.n_filas ? `<button class="btn btn-s btn-sm" data-revisar="${s.id}">Ver</button>` : ''}</td></tr>`;
  }).join('') : vacio(7, 'Todavía no hay lecturas.');
  const activo = st.grabando || ses.some(s => s.estado === 'procesando');
  if (activo && !E.pollCaptura) E.pollCaptura = setInterval(refrescarCaptura, 2000);
  if (!activo) pararPoll();
  if (E.sesionSel && ses.some(s => s.id === E.sesionSel && s.estado !== 'procesando') && !$('#c-revision').dataset.cargada) verSesion(E.sesionSel);
}
$('#c-empezar').addEventListener('click', async () => {
  const s = servidorActual();
  if (!s) return toast('Elige un perfil con servidor: las lecturas van al mercado de ese servidor.', 'err');
  try { await api('/api/captura/grabacion/iniciar', { method: 'POST', body: { servidor_id: s.id } }); toast('Lectura en marcha: cambia al juego y recorre el mercado.', 'ok'); }
  catch (_) { }
  refrescarCaptura();
});
$('#c-terminar').addEventListener('click', async () => {
  $('#c-terminar').disabled = true;
  try {
    const r = await api('/api/captura/grabacion/detener', { method: 'POST' });
    toast(r.estado === 'revision' ? `Lectura terminada: ${r.n_dudosas} fila(s) para revisar.` : (r.mensaje || 'Lectura terminada.'), r.estado === 'error' ? 'err' : 'ok');
    E.sesionSel = r.id; $('#c-revision').dataset.cargada = '';
  } catch (_) { }
  refrescarCaptura();
});
const zona = $('#c-zona');
zona.addEventListener('click', () => $('#c-archivo').click());
zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('encima'); });
zona.addEventListener('dragleave', () => zona.classList.remove('encima'));
zona.addEventListener('drop', e => { e.preventDefault(); zona.classList.remove('encima'); subirArchivos([...e.dataTransfer.files]); });
$('#c-archivo').addEventListener('change', e => { subirArchivos([...e.target.files]); e.target.value = ''; });
async function subirArchivos(archivos) {
  const s = servidorActual();
  if (!s) return toast('Elige un perfil con servidor antes de subir.', 'err');
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
async function verSesion(id) {
  E.sesionSel = id;
  const cont = $('#c-revision');
  cont.dataset.cargada = '1';
  let s;
  try { s = await api('/api/captura/sesiones/' + id, { silencioso: true }); } catch (e) { cont.innerHTML = avisoHTML(esc(e.message), 'err'); return; }
  const enRevision = s.estado === 'revision';
  const mostrarTodas = leerLocal('verTodas', false);
  const filas = s.filas.filter(f => mostrarTodas || f.estado === 'pendiente' || !enRevision);
  cont.innerHTML = `<h3>Revisión · ${s.n_filas} filas (${s.n_dudosas} dudosas)</h3>
    ${enRevision ? '<p class="ayuda">Corrige el objeto, precio o cantidad y pulsa ✓; o descarta la fila con ✕. Al guardar, las filas que sigan pendientes se descartan.</p>' : ''}
    <label class="check"><input type="checkbox" id="c-todas" ${mostrarTodas ? 'checked' : ''}> Mostrar también las filas correctas</label>
    <div class="tbl-wrap"><table><thead><tr><th>Imagen / leído</th><th>Objeto</th><th class="num">Precio</th><th class="num">Cantidad</th><th>Motivo</th><th>Estado</th><th></th></tr></thead><tbody>
    ${filas.length ? filas.map(f => `<tr data-idx="${f.idx}">
      <td>${f.recorte ? `<img class="recorte" loading="lazy" src="/api/captura/sesiones/${s.id}/filas/${f.idx}/recorte" alt="">` : ''}<span class="dim">${esc(f.nombre_leido)}</span></td>
      <td><div class="ac"><input class="r-obj" value="${esc(f.nombre || '')}" data-id="${f.objeto_id ?? ''}" ${enRevision ? '' : 'disabled'} placeholder="Elige objeto…" autocomplete="off"></div></td>
      <td class="num"><input class="r-precio" type="number" value="${f.precio ?? ''}" ${enRevision ? '' : 'disabled'}></td>
      <td class="num"><input class="r-cant" type="number" value="${f.cantidad ?? ''}" ${enRevision ? '' : 'disabled'}></td>
      <td class="dim" style="font-size:.78rem">${esc((f.motivos || []).join('; '))}${f.confianza != null ? ` (${Math.round(f.confianza * 100)} %)` : ''}</td>
      <td>${{ pendiente: '<span class="tag tag-o">dudosa</span>', ok: '<span class="tag tag-g">ok</span>', corregida: '<span class="tag tag-b">corregida</span>', descartada: '<span class="tag tag-gris">descartada</span>' }[f.estado] || esc(f.estado)}</td>
      <td style="white-space:nowrap">${enRevision ? `<button class="btn btn-g btn-sm" data-acc="confirmar" title="Confirmar">✓</button> <button class="btn btn-d btn-sm" data-acc="descartar" title="Descartar">✕</button>` : ''}</td></tr>`).join('') : vacio(7, 'No hay filas dudosas.')}
    </tbody></table></div>
    ${enRevision ? `<div style="margin-top:10px"><button class="btn btn-p" id="c-guardar-sesion">Guardar sesión (${s.n_ok} correctas)</button></div>` : ''}`;
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
    if (!obj.dataset.id) return toast('Elige el objeto correcto de la lista de sugerencias.', 'err');
    Object.assign(datos, { objeto_id: +obj.dataset.id, precio: $('.r-precio', tr).value, cantidad: $('.r-cant', tr).value });
  }
  try { await api(`/api/captura/sesiones/${E.sesionSel}/filas/${idx}`, { method: 'POST', body: datos }); verSesion(E.sesionSel); refrescarCaptura(); }
  catch (_) { }
});

// --- calibración
const CAL = { img: null, ancho: 0, alto: 0, lista: null, columnas: {}, arrastre: null };
const COLORES_CAL = { lista: '#4ade80', nombre: '#6c9fff', precio: '#fbbf24', cantidad: '#a78bfa' };
async function cargarCalibracion() {
  try {
    const c = await api('/api/captura/calibracion', { silencioso: true });
    const res = c.resolucion, act = c.actual;
    $('#cal-info').innerHTML = res ? `Pantalla: <b>${res[0]}×${res[1]}</b> · ${act && act.calibrada ? `calibrada (zona ${act.lista.join(', ')})` : '<span class="neg">sin calibrar: se lee la pantalla completa</span>'}`
      : esc(c.aviso || '');
    CAL.guardada = c.datos;
  } catch (e) { $('#cal-info').textContent = e.message; }
}
$('#cal-pantalla').addEventListener('click', async () => {
  const b = $('#cal-pantalla');
  b.disabled = true;
  let n = 5; b.textContent = `Cambia al juego… ${n}`;
  const t = setInterval(() => { n--; if (n > 0) b.textContent = `Cambia al juego… ${n}`; }, 1000);
  try {
    const r = await fetch('/api/captura/calibracion/pantalla?espera=5', { method: 'POST' });
    if (!r.ok) throw new Error((await r.json()).detail || 'No se pudo capturar la pantalla');
    const ancho = +r.headers.get('X-Ancho'), alto = +r.headers.get('X-Alto');
    const url = URL.createObjectURL(await r.blob());
    cargarImagenCal(url, ancho, alto);
  } catch (e) { toast(e.message, 'err'); }
  finally { clearInterval(t); b.disabled = false; b.textContent = '📷 Capturar pantalla (5 s)'; }
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
  ctx.font = `${Math.max(14, lz.width / 80)}px Segoe UI`;
  const caja = (x, y, w, h, color, texto) => { ctx.strokeStyle = color; ctx.fillStyle = color + '22'; ctx.fillRect(x * k, y * k, w * k, h * k); ctx.strokeRect(x * k, y * k, w * k, h * k); ctx.fillStyle = color; ctx.fillText(texto, x * k + 4, y * k + 18); };
  if (CAL.lista) {
    const [x, y, w, h] = CAL.lista;
    caja(x, y, w, h, COLORES_CAL.lista, 'Lista');
    for (const [col, [x0, x1]] of Object.entries(CAL.columnas || {})) caja(x0, y, x1 - x0, h, COLORES_CAL[col] || '#fff', col);
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
  if (!a || Math.abs(a.x1 - a.x0) < 8) { pintarCal(); return; }
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
  try {
    const r = await api('/api/recetas?' + qs({ perfil_id: E.perfil, q: $('#r-q').value.trim(), profesion: $('#r-prof').value, solo_desbloqueadas: $('#r-desb').checked, limite: 400 }), { silencioso: true });
    cont.innerHTML = r.filas.length ? r.filas.map(f => `<tr class="clic ${E.recetaSel === f.id ? 'sel' : ''}" data-receta="${f.id}">
      <td>${esc(f.nombre)}${f.cantidad > 1 ? ` <span class="dim">×${f.cantidad}</span>` : ''}</td><td>${esc(f.profesion_nombre)}</td>
      <td class="num">${f.nivel ?? '—'}</td><td class="num">${f.combo_pct ? f.combo_pct + ' %' : '—'}</td>
      <td>${f.desbloqueada ? '<span class="tag tag-g">desbloqueada</span>' : '<span class="tag tag-gris">bloqueada</span>'}</td></tr>`).join('')
      + (r.total > r.filas.length ? `<tr><td colspan="5" class="dim">… y ${r.total - r.filas.length} más: afina la búsqueda.</td></tr>` : '')
      : vacio(5, 'Ninguna receta coincide.');
  } catch (e) { cont.innerHTML = vacio(5, esc(e.message)); }
  if (E.recetaSel) verReceta(E.recetaSel, false);
}
$('#r-q').addEventListener('input', debounce(cargarRecetas, 250));
$('#r-prof').addEventListener('change', cargarRecetas);
$('#r-desb').addEventListener('change', cargarRecetas);
$('#r-lista').addEventListener('click', e => { const tr = e.target.closest('[data-receta]'); if (tr) verReceta(+tr.dataset.receta); });

async function verReceta(id, cambiarPestana = true, intentos) {
  E.recetaSel = id;
  if (cambiarPestana && E.tab !== 'recetas') { irA('recetas'); return; }
  $$('#r-lista tr').forEach(tr => tr.classList.toggle('sel', +tr.dataset.receta === id));
  const card = $('#r-detalle-card'), cont = $('#r-detalle');
  card.hidden = false;
  cont.innerHTML = '<div class="vacio">Calculando…</div>';
  let d;
  try { d = await api(`/api/recetas/${id}?` + qs({ perfil_id: E.perfil, intentos: intentos || 1 }), { silencioso: true }); }
  catch (e) { cont.innerHTML = avisoHTML(esc(e.message), 'err'); return; }
  const r = d.receta, a = d.analisis, e_ = d.escenario_objetivo;
  cont.innerHTML = `<h2>${esc(r.nombre)} <span class="sub">${esc(r.profesion_nombre)} · nivel ${r.nivel} · ${r.faccion === 'ambas' ? 'ambas facciones' : esc(r.faccion)}${r.combo_pct ? ` · combo ${r.combo_pct} %${r.producto_combo_nombre ? ' → ' + esc(r.producto_combo_nombre) : ''}` : ''}</span></h2>
    ${d.aviso ? avisoHTML(esc(d.aviso), 'err') : ''}
    ${a ? `<div class="fila"><div class="auto"><label for="rd-n">Intentos</label><input id="rd-n" type="number" min="1" value="${a.intentos}" style="width:110px"></div>
      <div class="auto"><button class="btn btn-s" id="rd-re">Recalcular</button></div>
      <div class="auto"><button class="btn btn-p" id="rd-lista">🛒 Lista de la compra</button></div></div>
    <div class="stats">
      <div class="stat"><div class="val">${kin(a.coste_intento)}</div><div class="lbl">Coste / intento</div></div>
      <div class="stat"><div class="val">${kin(a.ingreso_esperado)}</div><div class="lbl">Ingreso esperado / intento</div></div>
      <div class="stat"><div class="val ${signo(a.beneficio_intento)}">${kin(a.beneficio_intento)}</div><div class="lbl">Beneficio / intento</div></div>
      <div class="stat"><div class="val ${signo(a.margen)}">${pct(a.margen)}</div><div class="lbl">Margen</div></div>
      <div class="stat"><div class="val ${signo(a.beneficio_total)}">${kin(a.beneficio_total)}</div><div class="lbl">Beneficio con ${a.intentos} intento(s)</div></div>
      <div class="stat"><div class="val">${kin(a.precio_equilibrio)}</div><div class="lbl">Precio de equilibrio</div></div>
      <div class="stat"><div class="val">${pct(a.p_exito)}</div><div class="lbl">Éxito (nivel ${a.nivel})</div></div>
      <div class="stat"><div class="val">${pct(a.p_combo)}</div><div class="lbl">Combo conseguido</div></div>
      <div class="stat"><div class="val">${num1(a.items_esperados)}</div><div class="lbl">Objetos / intento</div></div>
      <div class="stat"><div class="val">${a.max_intentos_mercado == null ? '∞' : kin(a.max_intentos_mercado)}</div><div class="lbl">Intentos rentables con el mercado</div></div>
    </div>
    ${a.mensaje_inventario ? avisoHTML(esc(a.mensaje_inventario), 'info') : ''}
    ${(a.avisos || []).length ? `<ul class="avisos">${a.avisos.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${e_ && e_.precio_objetivo != null && e_.estado !== 'sin_datos' ? avisoHTML(`Precio objetivo de venta: <b>${kin(e_.precio_objetivo)}</b> (${esc(ESTADOS[e_.estado] || e_.estado)}) → beneficio ${kin(e_.beneficio_total)} frente a ${kin(a.beneficio_total)} vendiendo ya a ${kin(e_.precio_ya)}.${e_.aviso ? ' ' + esc(e_.aviso) : ''}`, 'info') : ''}
    <h3>Ingredientes por intento</h3>
    <div class="tbl-wrap"><table><thead><tr><th>Ingrediente</th><th class="num">Cant.</th><th>Origen</th><th class="num">Coste unit.</th><th class="num">Tienes</th><th class="num">Faltan</th></tr></thead><tbody>
      ${a.desglose_ingredientes.map(i => `<tr><td>${esc(i.nombre)}</td><td class="num">${i.cantidad}</td><td>${esc({ mercado: 'Mercado', npc: 'Tienda NPC', fabricar: 'Fabricar', inventario: 'Inventario' }[i.origen] || '—')}</td>
        <td class="num">${kin(i.coste_unit)}</td><td class="num">${kin(i.en_inventario)}</td><td class="num">${kin(i.faltan)}</td></tr>`).join('')}
    </tbody></table></div>
    <h3>Árbol: comprar o fabricar</h3>
    <ul class="arbol">${arbolHTML(d.arbol || [])}</ul>` : ''}`;
  const re = $('#rd-re'); if (re) re.onclick = () => verReceta(id, false, +$('#rd-n').value || 1);
  const li = $('#rd-lista'); if (li) li.onclick = () => abrirListaCompra(id, +$('#rd-n').value || 1);
}
function arbolHTML(nodos) {
  return nodos.map(n => {
    const op = (k, etiqueta, v) => v == null ? '' : `<span class="op ${n.mejor === k ? 'mejor' : ''}">${etiqueta}: <b>${kin(v)}</b>${n.mejor === k ? ' ✓' : ''}</span>`;
    return `<li><div class="nodo"><span class="n">${n.cantidad}× ${esc(n.nombre)}</span>
      ${op('mercado', 'Mercado', n.precio_mercado)}${op('npc', 'NPC', n.precio_npc)}${op('fabricar', 'Fabricar', n.coste_fabricar)}
      ${n.en_inventario ? `<span class="tag tag-b">tienes ${kin(n.en_inventario)}</span>` : ''}
      ${n.precio_mercado != null && n.antiguedad_horas != null ? `<span class="op">${semaforoHTML(n.antiguedad_horas <= 6 ? 'verde' : n.antiguedad_horas <= 24 ? 'ambar' : 'rojo', n.antiguedad_horas)}${esc(hace(n.antiguedad_horas))}</span>` : ''}
      ${n.mejor == null ? '<span class="tag tag-r">sin precio</span>' : ''}${n.nota ? `<span class="op">${esc(n.nota)}</span>` : ''}</div>
      ${n.hijos && n.hijos.length ? `<ul>${arbolHTML(n.hijos)}</ul>` : ''}</li>`;
  }).join('');
}

// ================================================================== PERSONAJE
async function cargarPersonaje() {
  await cargarPerfiles();
  const p = perfilActual();
  $('#p-perfiles').innerHTML = E.perfiles.length ? `<div class="tbl-wrap"><table><thead><tr><th>Personaje</th><th>Servidor</th><th></th></tr></thead><tbody>
    ${E.perfiles.map(x => `<tr class="${x.id === E.perfil ? 'sel' : ''}"><td>${esc(x.nombre)}</td><td>${x.servidor ? `${esc(x.servidor.nombre)} <span class="tag ${x.faccion === 'elyos' ? 'tag-b' : 'tag-p'}">${x.faccion === 'elyos' ? 'Elyos' : 'Asmodian'}</span>` : '<span class="neg">sin servidor</span>'}</td>
      <td style="white-space:nowrap">${x.id !== E.perfil ? `<button class="btn btn-s btn-sm" data-usar="${esc(x.id)}">Usar</button> ` : ''}<button class="btn btn-s btn-sm" data-editar="${esc(x.id)}">Editar</button></td></tr>`).join('')}
    </tbody></table></div>` : avisoHTML('Crea tu primer perfil: primero un servidor (derecha) y luego tu personaje.', 'info');
  $('#p-servidor').innerHTML = '<option value="">— sin servidor —</option>' + E.servidores.map(s => `<option value="${esc(s.id)}">${esc(s.nombre)} (${s.faccion === 'elyos' ? 'Elyos' : 'Asmodian'})</option>`).join('');
  $('#s-lista').innerHTML = E.servidores.length ? `<div class="tbl-wrap"><table><thead><tr><th>Servidor</th><th>Facción</th><th class="num">Comisión</th><th class="num">Impuesto</th></tr></thead><tbody>
    ${E.servidores.map(s => `<tr><td>${esc(s.nombre)} <span class="dim">${esc(s.id)}</span></td><td>${s.faccion === 'elyos' ? 'Elyos' : 'Asmodian'}</td><td class="num">${s.comision_registro != null ? pct(s.comision_registro) : 'por defecto'}</td><td class="num">${s.impuesto_venta != null ? pct(s.impuesto_venta) : 'por defecto'}</td></tr>`).join('')}
    </tbody></table></div>` : '<p class="ayuda">Aún no hay servidores.</p>';
  $('#n-perfil').textContent = p ? p.nombre : '';
  if (!p) {
    $('#n-niveles').innerHTML = '<p class="ayuda">Crea un perfil para guardar sus niveles.</p>';
    $('#i-tabla').innerHTML = vacio(4, 'Crea un perfil para guardar su inventario.');
    return;
  }
  try {
    const niveles = await api(`/api/perfiles/${encodeURIComponent(p.id)}/niveles`, { silencioso: true });
    $('#n-niveles').innerHTML = Object.entries(E.profesiones).map(([k, nom]) => {
      const n = niveles[k] ?? 1;
      return `<div class="prof"><div class="nom">${esc(nom)}</div><input type="number" min="1" max="100" data-prof="${k}" value="${n}" aria-label="Nivel de ${esc(nom)}">
        <div class="barra"><div class="${n > 50 ? 'esp' : ''}" style="width:${Math.min(100, n)}%"></div></div>
        <div class="rango">${n > 50 ? 'Especialista (51–100)' : 'Principiante (1–50)'}</div></div>`;
    }).join('');
  } catch (e) { $('#n-niveles').innerHTML = avisoHTML(esc(e.message), 'err'); }
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
    if (!E.perfil) E.perfil = r.id;
    cambiarPerfil(E.perfil || r.id);
  } catch (_) { }
});
$('#s-guardar').addEventListener('click', async () => {
  const com = $('#s-com').value, imp = $('#s-imp').value;
  try {
    await api('/api/servidores', { method: 'POST', body: { nombre: $('#s-nombre').value, faccion: $('#s-faccion').value, region: 'EU', comision_registro: com === '' ? null : com / 100, impuesto_venta: imp === '' ? null : imp / 100 } });
    toast('Servidor guardado.', 'ok');
    ['#s-nombre', '#s-com', '#s-imp'].forEach(i => $(i).value = '');
    cargarPersonaje();
  } catch (_) { }
});
$('#n-niveles').addEventListener('input', e => {
  const i = e.target.closest('input[data-prof]'); if (!i) return;
  const n = Math.max(0, Math.min(100, +i.value || 0)), card = i.closest('.prof');
  $('.barra div', card).style.width = n + '%'; $('.barra div', card).className = n > 50 ? 'esp' : '';
  $('.rango', card).textContent = n > 50 ? 'Especialista (51–100)' : 'Principiante (1–50)';
});
$('#n-guardar').addEventListener('click', async () => {
  const p = perfilActual(); if (!p) return toast('Crea un perfil primero.', 'err');
  const datos = Object.fromEntries($$('#n-niveles input[data-prof]').map(i => [i.dataset.prof, +i.value || 1]));
  try { await api(`/api/perfiles/${encodeURIComponent(p.id)}/niveles`, { method: 'PUT', body: datos }); toast('Niveles guardados.', 'ok'); } catch (_) { }
});

async function cargarInventario() {
  const p = perfilActual(); if (!p) return;
  try {
    const filas = await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario`, { silencioso: true });
    $('#i-tabla').innerHTML = filas.length ? filas.map(f => `<tr data-obj="${f.objeto_id}" data-ubic="${esc(f.ubicacion)}"><td>${esc(f.nombre)}</td><td>${f.ubicacion === 'almacen' ? 'Almacén' : 'Inventario'}</td>
      <td class="num"><input type="number" min="0" value="${f.cantidad}" class="i-cant-ed"></td><td><button class="btn btn-d btn-sm" data-borrar title="Quitar">✕</button></td></tr>`).join('')
      : vacio(4, 'Inventario vacío.');
  } catch (e) { $('#i-tabla').innerHTML = vacio(4, esc(e.message)); }
}
async function guardarInv(filas) {
  const p = perfilActual(); if (!p) { toast('Crea un perfil primero.', 'err'); return false; }
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
  if (!o.dataset.id) return toast('Elige el objeto de la lista de sugerencias.', 'err');
  if (await guardarInv([{ objeto_id: +o.dataset.id, cantidad: +$('#i-cant').value || 0, ubicacion: $('#i-ubic').value }])) {
    toast('Inventario actualizado.', 'ok'); o.value = ''; delete o.dataset.id; $('#i-cant').value = ''; cargarInventario();
  }
});
$('#i-pegar').addEventListener('click', async () => {
  const p = perfilActual(); if (!p) return toast('Crea un perfil primero.', 'err');
  const cont = $('#i-pegado');
  try {
    const r = await api(`/api/perfiles/${encodeURIComponent(p.id)}/inventario/pegar`, { method: 'POST', body: { texto: $('#i-texto').value } });
    if (!r.filas.length) { cont.innerHTML = avisoHTML('No hay líneas que leer.'); return; }
    cont.innerHTML = `<div class="tbl-wrap" style="margin-top:10px"><table><thead><tr><th>Texto</th><th>Objeto</th><th class="num">Cantidad</th><th></th></tr></thead><tbody>
      ${r.filas.map(f => `<tr><td class="dim">${esc(f.texto)}</td><td><div class="ac"><input class="pg-obj" value="${esc(f.nombre || '')}" ${f.objeto_id ? `data-id="${f.objeto_id}"` : ''} autocomplete="off"></div></td>
        <td class="num"><input type="number" class="pg-cant" min="0" value="${f.cantidad ?? ''}"></td>
        <td>${f.dudosa ? '<span class="tag tag-o">revisar</span>' : `<span class="tag tag-g">${Math.round(f.puntuacion)} %</span>`}</td></tr>`).join('')}
      </tbody></table></div>
      <div class="fila" style="margin-top:8px"><div class="auto"><label for="pg-ubic">Guardar en</label><select id="pg-ubic"><option value="inventario">Inventario</option><option value="almacen">Almacén</option></select></div>
      <div class="auto"><button class="btn btn-p" id="pg-guardar">Guardar las filas con objeto y cantidad</button></div></div>`;
    $$('.pg-obj', cont).forEach(i => autocompletar(i));
    $('#pg-guardar', cont).onclick = async () => {
      const ubic = $('#pg-ubic', cont).value;
      const filas = $$('tbody tr', cont).map(tr => ({ id: $('.pg-obj', tr).dataset.id, c: $('.pg-cant', tr).value }))
        .filter(f => f.id && f.c !== '').map(f => ({ objeto_id: +f.id, cantidad: +f.c, ubicacion: ubic }));
      if (!filas.length) return toast('Ninguna fila tiene objeto y cantidad.', 'err');
      if (await guardarInv(filas)) { toast(`${filas.length} objeto(s) guardados.`, 'ok'); cont.innerHTML = ''; $('#i-texto').value = ''; cargarInventario(); }
    };
  } catch (_) { }
});

// ================================================================== AJUSTES
async function cargarAjustes() {
  try {
    const a = await api('/api/ajustes', { silencioso: true });
    $('#a-com').value = +(a.comision_registro * 100).toFixed(3);
    $('#a-imp').value = +(a.impuesto_venta * 100).toFixed(3);
    $('#a-rebaja').value = a.rebaja_listado;
    $('#a-combo').value = a.combo_fallido;
    $('#a-valinv').value = a.valorar_inventario;
    $('#a-horas').value = a.horas_precio_antiguo ?? 24;
    $('#a-tope').value = a.tope_intentos ?? 100;
    $('#a-anun').value = a.max_anuncios ?? 10;
    $('#a-tmp').value = a.tope_tmp_mb ?? 500;
  } catch (e) { toast(e.message, 'err'); }
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
async function cargarNPC() {
  try {
    const filas = await api('/api/precios-npc', { silencioso: true });
    $('#npc-tabla').innerHTML = filas.length ? filas.map(f => `<tr data-obj="${f.objeto_id}"><td>${esc(f.nombre)}</td>
      <td class="num"><input type="number" min="0" class="npc-ed" value="${f.precio ?? ''}"></td><td><span class="tag ${f.origen === 'manual' ? 'tag-b' : 'tag-gris'}">${esc(f.origen)}</span></td>
      <td>${f.origen === 'manual' ? '<button class="btn btn-s btn-sm" data-quitar title="Volver al precio del catálogo">Quitar</button>' : ''}</td></tr>`).join('')
      : vacio(4, 'Sin precios NPC.');
  } catch (e) { $('#npc-tabla').innerHTML = vacio(4, esc(e.message)); }
}
autocompletar($('#npc-obj'));
$('#npc-guardar').addEventListener('click', async () => {
  const o = $('#npc-obj');
  if (!o.dataset.id) return toast('Elige el objeto de la lista de sugerencias.', 'err');
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
  const comp = Object.entries(s.componentes || {}).map(([k, v]) => `<tr><td>${esc(nombres[k] || k)}</td><td>${v.ok ? '<span class="tag tag-g">ok</span>' : '<span class="tag tag-r">no disponible</span>'}</td><td class="dim" style="font-size:.78rem">${esc(v.mensaje || '')}</td></tr>`).join('');
  const t = s.temporales || {};
  $('#a-estado').innerHTML = `<div class="stats">
      <div class="stat"><div class="val" style="font-size:1.05rem">${s.backend === 'supabase' ? 'Supabase' : s.backend === 'local' ? 'Local (SQLite)' : '—'}</div><div class="lbl">Base de datos</div></div>
      <div class="stat"><div class="val">${s.en_cola ?? '—'}</div><div class="lbl">Lotes en cola offline</div></div>
      <div class="stat"><div class="val">${t.archivos ?? 0}</div><div class="lbl">Temporales (${num1(t.mb)} MB de ${t.tope_mb ?? '—'})</div></div>
      <div class="stat"><div class="val">${s.catalogo ? kin(s.catalogo.recetas) : '—'}</div><div class="lbl">Recetas en el catálogo${s.catalogo && s.catalogo.version_cliente ? ` (cliente ${esc(s.catalogo.version_cliente)})` : ''}</div></div>
    </div>
    ${s.backend === 'local' ? avisoHTML('Usando la base de datos local (data/aion2.db). Para guardar el histórico en la nube, crea tu propio proyecto gratuito de Supabase, pon su URL y tu clave secreta en el archivo .env (guía: docs/supabase.md) y reinicia la app.', 'info') : ''}
    <div class="tbl-wrap"><table><tbody>${comp}</tbody></table></div>`;
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
window.addEventListener('hashchange', () => irA(location.hash.slice(1)));
$('#btn-panel').addEventListener('click', cargarPanel);
['#f-prof', '#f-inter', '#f-usarinv'].forEach(id => $(id).addEventListener('change', cargarPanel));
['#f-inv', '#f-margen'].forEach(id => $(id).addEventListener('input', debounce(cargarPanel, 600)));
document.addEventListener('click', e => { const b = e.target.closest('[data-ver-receta]'); if (b && !b.closest('#panel-tabla') && !b.closest('#m-detalle')) verReceta(+b.dataset.verReceta); });

(async function iniciar() {
  const f = leerLocal('filtros', null);
  await cargarEstado();
  llenarProfesiones();
  if (f) {
    $('#f-prof').value = f.profesion || ''; $('#f-inv').value = f.inversion_max || ''; $('#f-margen').value = f.margen_min || '';
    $('#f-inter').checked = f.incluir_intermedios !== false; $('#f-usarinv').checked = f.usar_inventario !== false;
  }
  await cargarPerfiles();
  irA(location.hash.slice(1) || 'panel');
  setInterval(cargarEstado, 60000);
})();
