/* Life Skill Manager's own icons (stroke SVG, 24×24). They are original and ship with the project.
   The official game icons belong to NCSOFT and are not in the repository; if the user downloads them
   (Settings), they are stored in data/iconos/ and the API serves them locally only.
   Format: one category per line, a list of "d" paths. */
"use strict";

const ICONOS_CATEGORIA = {
  mineral: ["M4 15l4-9 8-2 4 7-3 9H8z", "M8 6l3 7 9-2M11 13l-3 7M11 13l6 7"],
  gema: ["M6 4h12l3 5-9 11L3 9z", "M3 9h18M9 4l-1 5 4 11 4-11-1-5"],
  madera: ["M8 7h10a4 5 0 0 1 0 10H8", "M4 12a4 5 0 1 0 8 0a4 5 0 1 0 -8 0", "M6.5 12a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0 -3 0"],
  hierba: ["M5 19C5 10 10 5 20 4c0 10-5 15-14 15z", "M5 19l9-9"],
  carne: ["M12.5 3.5a6 6 0 0 1 8 8l-5 2.5-5.5-5.5z", "M10 9l-3.5 3.5a2 2 0 1 0 2.8 2.8L13 12"],
  escama: ["M4 6c4-3 12-3 16 0-1 8-4 12-8 14-4-2-7-6-8-14z", "M8 9c2 2 6 2 8 0M9 13c2 1.5 4 1.5 6 0"],
  esencia: ["M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z", "M9.5 14.5a2.5 2.5 0 0 0 2.5 2.5"],
  cristal: ["M12 2l5 7-5 13-5-13z", "M7 9h10"],
  condimento: ["M8 9h8l1 11H7z", "M9 9a3 3 0 0 1 6 0M11 13h.01M13 16h.01"],
  herramienta: ["M14 6l4 4M4 20l9-9M12 4l8 8-3 3-8-8z"],
  pocion: ["M9 3h6M10 3v5L5 17a3 3 0 0 0 2.6 4.5h8.8A3 3 0 0 0 19 17l-5-9V3", "M7 14h10"],
  comida: ["M3 12h18a9 9 0 0 1-18 0z", "M8 8c0-2 2-2 2-4M13 8c0-2 2-2 2-4"],
  pergamino: ["M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7", "M6 4a2 2 0 0 0-2 2v2h4V6a2 2 0 0 0-2-2zM7 20a2 2 0 0 1-2-2v-1h4v1a2 2 0 0 1-2 2zM10 9h6M10 13h6"],
  piedra: ["M12 3l8 5v8l-8 5-8-5V8z", "M12 8l3 4-3 4-3-4z"],
  refinamiento: ["M3 15l9-9 6 6-9 9z", "M7 11l6 6M14 4l6 6"],
  arma: ["M19 3h2v2L10 16l-2-2L19 3z", "M6 12l6 6M5 19l2-2M3 21l2-2"],
  armadura: ["M8 3l4 2 4-2 4 3-2 4v9a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-9L4 6z", "M12 5v15"],
  joya: ["M6 15a6 6 0 1 0 12 0a6 6 0 1 0 -12 0", "M9 6l3-3 3 3-3 3z"],
  otro: ["M4 8l8-4 8 4v8l-8 4-8-4z", "M4 8l8 4 8-4M12 12v8"],
};

const ICONOS_UI = {
  logo: ["M12 2l2.6 5.6L20 9l-4 4.3.9 6.2L12 16.8 7.1 19.5 8 13.3 4 9l5.4-1.4z", "M12 8v5"],
  reloj: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7v5l3 2"],
  alerta: ["M12 3l10 18H2z", "M12 10v4M12 17v.5"],
  escudo: ["M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z", "M9 12l2 2 4-4"],
  ojo: ["M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6z"],
  copiar: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
  flecha: ["M9 6l6 6-6 6"],
  buscar: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "M20 20l-4-4"],
  subir: ["M12 16V4M7 9l5-5 5 5", "M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"],
  play: ["M7 4l13 8-13 8z"],
  stop: ["M6 6h12v12H6z"],
  camara: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 10a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z"],
  candado: ["M6 11h12v9H6z", "M8 11V8a4 4 0 0 1 8 0v3"],
  cerrar: ["M6 6l12 12M18 6L6 18"],
  carrito: ["M3 4h2l2.5 11h10L20 7H6.2", "M9 20a1 1 0 1 0 0-2a1 1 0 1 0 0 2zM17 20a1 1 0 1 0 0-2a1 1 0 1 0 0 2z"],
  martillo: ["M14 6l4 4M4 20l9-9M12 4l8 8-3 3-8-8z"],
  etiqueta: ["M3 12V4h8l10 10-8 8z", "M7.5 8.5h.01"],
  descargar: ["M12 4v12M7 11l5 5 5-5", "M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"],
};

/* Icon of each profession (catalog key → icon category) */
const ICONO_PROFESION = { herreria: "arma", armadura: "armadura", orfebreria: "joya", alquimia: "pocion", cocina: "comida" };

function svgIcono(trazos, tam) {
  const t = tam || 24;
  return `<svg width="${t}" height="${t}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${(trazos || []).map(d => `<path d="${d}"></path>`).join("")}</svg>`;
}
function iconoUI(nombre, tam) { return svgIcono(ICONOS_UI[nombre], tam); }
