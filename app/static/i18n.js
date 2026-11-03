/* Life Skill Manager - Aion 2 — interface translations (ES/EN).
   Spanish is the source language: t('Texto {n}', { n }) returns the English entry when the language is EN,
   or the Spanish text itself. The API answers in Spanish, so tApi() translates its messages on the client:
   exact texts first, then patterns (object names inside them go through traducirNombre). */
'use strict';

const IDIOMAS = ['es', 'en'];
let IDIOMA = (() => {
  try { const v = JSON.parse(localStorage.getItem('aion2.idioma') || 'null'); return IDIOMAS.includes(v) ? v : 'es'; }
  catch (_) { return 'es'; }
})();
const LOCALE = () => (IDIOMA === 'en' ? 'en-US' : 'es-ES');
/* set by app.js: Spanish object name → name in the current language */
let traducirNombre = s => s;

const PROFESIONES_EN = {
  herreria: 'Weaponsmithing', armadura: 'Armorsmithing', orfebreria: 'Handicrafting', alquimia: 'Alchemy', cocina: 'Cooking',
};

const EN = {
  // --- header and navigation
  'Life Skill Manager · Aion 2 — ir al Panel': 'Life Skill Manager · Aion 2 — go to Dashboard',
  'Secciones': 'Sections',
  'Panel': 'Dashboard', 'Mercado': 'Market', 'Captura': 'Capture', 'Recetas': 'Recipes', 'Personaje': 'Character', 'Ajustes': 'Settings',
  'Base de datos': 'Database', 'Perfil activo': 'Active profile', 'Perfil (personaje y servidor)': 'Profile (character and server)',
  'Idioma': 'Language', 'Idioma de la interfaz': 'Interface language',
  'Nombres de objetos, avisos y números en el idioma elegido.': 'Object names, warnings and numbers in the chosen language.',

  // --- dashboard (static)
  'Tu plan de hoy': "Today's plan", 'Calculando…': 'Calculating…', 'Más jugadas': 'More plays',
  'Profesión': 'Profession', 'Todas las profesiones': 'All professions', 'Inversión máxima': 'Maximum investment',
  'Inversión máx.': 'Max. investment', 'Margen mínimo (%)': 'Minimum margin (%)', 'Margen mín. %': 'Min. margin %',
  'Intermedios': 'Intermediates', 'Usar mi inventario': 'Use my inventory', 'Receta': 'Recipe',
  'Benef./intento': 'Profit/attempt', 'Margen': 'Margin', 'Total': 'Total', 'Ojo con': 'Watch out',
  'Solo recetas desbloqueadas con tus niveles y de la facción de tu servidor. Beneficio esperado tras comisión e impuesto, con probabilidad de éxito y combo. Punto de color: antigüedad de los precios (verde ≤ 6 h, ámbar ≤ 24 h, rojo más).':
    "Only recipes unlocked at your levels and from your server's faction. Expected profit after fee and tax, with success and combo chance. Colour dot: price age (green ≤ 6 h, amber ≤ 24 h, red older).",

  // --- dashboard (dynamic)
  'Aún no hay precios': 'No prices yet', 'Lee el mercado para empezar a calcular': 'Read the market to start calculating',
  'Precios sin fecha': 'Prices without a date', 'Haz una lectura antes de comprar': 'Do a market read before buying',
  'Precios de {h}': 'Prices from {h}', 'Recién leídos: puedes comprar con confianza': 'Freshly read: you can buy with confidence',
  'Leer mercado': 'Read market',
  'Prepara tu <span class="resalte">primer plan</span>': 'Set up your <span class="resalte">first plan</span>',
  'Nada rentable <span class="resalte">con estos filtros</span>': 'Nothing profitable <span class="resalte">with these filters</span>',
  'Prueba a quitar filtros, subir tus niveles en Personaje o leer más precios del mercado.': 'Try removing filters, raising your levels in Character or reading more market prices.',
  'Tu plan de hoy · 3 pasos': "Today's plan · 3 steps",
  'Fabrica<br><span class="resalte">{nombre}</span><br>y gana ~{g}': 'Craft<br><span class="resalte">{nombre}</span><br>and earn ~{g}',
  '{n} intentos · inviertes {inv} · margen {m}': '{n} attempts · you invest {inv} · margin {m}',
  'Mercado {estado}': 'Market {estado}',
  'Compra': 'Buy', 'Fabrica': 'Craft', 'Vende': 'Sell', 'Calculando la lista…': 'Calculating the list…',
  'Copiar lista': 'Copy list', 'Ver lista': 'View list', 'para {n} intentos': 'for {n} attempts', 'nv. {n}': 'lv. {n}',
  '{n} intentos · éxito {p}': '{n} attempts · success {p}', '{v} / intento': '{v} / attempt', 'margen {m}': 'margin {m}',
  'combo {p}': 'combo {p}', 'intermedio': 'intermediate', 'Ver receta y árbol': 'View recipe and tree',
  'a <span class="num">{p}</span> c/u': 'at <span class="num">{p}</span> each', 'precio objetivo': 'target price',
  'precio actual': 'current price', ' · ~{u} unidades': ' · ~{u} units', 'Ver detalle': 'View details', 'vender ya: {p} c/u': 'sell now: {p} each',
  'tienda NPC': 'NPC shop', 'mercado': 'market',
  'por debajo de <b>{p}</b> c/u · {o}': 'below <b>{p}</b> each · {o}', 'a ~<b>{p}</b> c/u · {o}': 'at ~<b>{p}</b> each · {o}',
  'y {n} más en la lista': 'and {n} more on the list', 'No hace falta comprar nada: lo tienes todo.': "Nothing to buy: you have it all.",
  'Antes fabrica: {lista}': 'Craft first: {lista}', 'De tu inventario: {lista}': 'From your inventory: {lista}',
  'Precios {h}': 'Prices {h}', 'invierte {inv}': 'invest {inv}', '{n} aviso': '{n} warning', '{n} avisos': '{n} warnings',
  'No hay más recetas rentables con estos filtros.': 'No more profitable recipes with these filters.',
  'Sin oportunidades todavía. Prueba a quitar filtros o a leer más precios del mercado.': 'No opportunities yet. Try removing filters or reading more market prices.',
  'Ver {n} más (de {total})': 'Show {n} more (of {total})',
  '<b>{n} de {total} precios</b> tienen más de 24 h. Los cálculos pueden estar desfasados.': '<b>{n} of {total} prices</b> are older than 24 h. The numbers may be out of date.',
  'mercado {estado}.': 'market {estado}.', '<b>{nombre}</b> deja solo un {m} de margen.': '<b>{nombre}</b> leaves only a {m} margin.',
  'Sin histórico suficiente en algunos productos: el precio objetivo usa el precio actual. Cada lectura del mercado lo mejora.':
    'Not enough history for some products: the target price uses the current price. Every market read improves it.',
  'Todo en orden: precios recientes y sin mercados saturados.': 'All good: recent prices and no saturated markets.',
  '{n} precio antiguo': '{n} old price', '{n} precios antiguos': '{n} old prices', 'Haz una lectura del mercado.': 'Do a market read.',
  'Precio objetivo: hace falta más histórico de este producto (al menos 3 lecturas). Por ahora se usa el precio actual.':
    'Target price: this product needs more history (at least 3 reads). For now the current price is used.',
  'Vender ya o esperar al precio objetivo': 'Sell now or wait for the target price',
  'Precio ya': 'Price now', 'Beneficio ya': 'Profit now', 'Precio objetivo · {estado}': 'Target price · {estado}',
  'Beneficio objetivo': 'Target profit', 'Tiempo de venta': 'Time to sell', '{n} d': '{n} d',
  'nivel {n}': 'level {n}', 'precios {h}': 'prices {h}', 'Benef. / intento': 'Profit / attempt', 'Intentos': 'Attempts',
  'Inversión': 'Investment', 'Benef. total': 'Total profit', 'Coste / intento': 'Cost / attempt', 'Precio de venta': 'Sale price',
  'Equilibrio': 'Break-even', 'Éxito': 'Success', 'Combo': 'Combo', 'Objetos / intento': 'Items / attempt',
  'Lista de la compra': 'Shopping list', 'Cerrar': 'Close',
  '{n} intento(s) · coste estimado <b class="num">{c}</b> Kinah': '{n} attempt(s) · estimated cost <b class="num">{c}</b> Kinah',
  'Recalcular': 'Recalculate', 'Copiar texto': 'Copy text', 'Comprar': 'Buy', 'Coste': 'Cost',
  ' · compra por debajo de <b>{p}</b>': ' · buy below <b>{p}</b>', '~<b>{p}</b> c/u': '~<b>{p}</b> each', 'Nada que comprar: lo tienes todo.': 'Nothing to buy: you have it all.',
  'Fabricar antes': 'Craft first', '{n} intento(s)': '{n} attempt(s)', 'Usar de tu inventario': 'Use from your inventory',
  'Texto para pegar': 'Text to paste', 'Lista copiada al portapapeles.': 'List copied to the clipboard.',
  'Lista de la compra — {nombre} × {n} intento(s)': 'Shopping list — {nombre} × {n} attempt(s)',
  'a ~{p}': 'at ~{p}', 'Del inventario': 'From inventory',

  // --- market
  'Buscar objeto': 'Search item', 'p. ej. Piedra espiritual': 'e.g. Spirit Stone', 'Últimas lecturas': 'Latest reads',
  'Filtrar por nombre…': 'Filter by name…', 'Filtrar lecturas por nombre': 'Filter reads by name', 'Objeto': 'Item',
  'Precio mín.': 'Min. price', 'En oferta': 'On offer', 'Anuncios': 'Listings', 'Fuente': 'Source', 'Antigüedad': 'Age',
  'Apuntar un precio': 'Log a price',
  'Lo que estás viendo en el juego, a mano. El libro de ofertas es opcional: una línea por anuncio con «precio cantidad».':
    'What you see in the game, by hand. The order book is optional: one line per listing with "price quantity".',
  'Objeto…': 'Item…', 'Nº anuncios': 'No. of listings', 'Libro de ofertas (opcional)': 'Order book (optional)', 'Guardar lectura': 'Save read',
  'Elige un perfil con servidor': 'Pick a profile with a server', 'Crea un perfil con servidor en Personaje.': 'Create a profile with a server in Character.',
  'Cada servidor tiene su propio mercado: crea un perfil con servidor en Personaje.': 'Each server has its own market: create a profile with a server in Character.',
  '{s} · {f} · {n} objetos con precio': '{s} · {f} · {n} items with a price',
  'Busca un objeto arriba o pulsa una fila de «Últimas lecturas» para ver su histórico, las ofertas y el precio objetivo.':
    'Search for an item above or click a row in "Latest reads" to see its history, the listings and the target price.',
  'Ningún objeto coincide.': 'No item matches.', 'Aún no hay lecturas en este servidor.': 'No reads on this server yet.',
  'vinculado': 'bound', 'comerciable': 'tradeable', 'se fabrica ({n} receta)': 'craftable ({n} recipe)', 'se fabrica ({n} recetas)': 'craftable ({n} recipes)',
  'Hace falta más histórico (al menos 3 lecturas) para calcular el precio objetivo.': 'More history is needed (at least 3 reads) to calculate the target price.',
  'p25 {p}': 'p25 {p}', 'objetivo {p}': 'target {p}', 'p75 {p}': 'p75 {p}', 'precio mínimo · {edad}': 'minimum price · {edad}', 'sin lecturas': 'no reads',
  'Volumen / día': 'Volume / day', 'Compra por debajo de': 'Buy below', 'Precio objetivo': 'Target price', 'Histórico': 'History',
  '{n} días': '{n} days', 'Apuntar precio': 'Log price', 'Ver su receta': 'View its recipe',
  'Histórico de precio y unidades en oferta': 'Price history and units on offer', 'Sin histórico en este periodo.': 'No history in this period.',
  'Ofertas ahora': 'Listings now', 'La última lectura no trae el libro de ofertas.': 'The latest read has no order book.',
  'Precio objetivo de venta': 'Target sale price', 'No se pudo cargar Chart.js (¿sin internet?).': 'Chart.js could not be loaded (no internet?).',
  'Precio mínimo': 'Minimum price', 'Unidades en oferta': 'Units on offer',
  'Elige un perfil con servidor.': 'Pick a profile with a server.', 'Elige el objeto de la lista de sugerencias.': 'Pick the item from the suggestion list.',
  'Guardado en la cola offline (se subirá al reconectar).': 'Saved to the offline queue (it will upload when reconnected).', 'Lectura guardada.': 'Read saved.',
  'grabación': 'recording', 'vídeo': 'video', 'captura': 'screenshot', 'manual': 'manual', 'excel': 'excel', 'catálogo': 'catalog',
  'normal': 'normal', 'precio hundido': 'sunk price', 'saturado': 'saturated', 'sin histórico': 'no history',
  'sin datos': 'no data', 'sin fecha': 'no date', 'hace {n} min': '{n} min ago', 'hace {n} h': '{n} h ago', 'hace {n} d': '{n} d ago', 'hace {n} días': '{n} days ago',

  // --- capture
  'Leer el mercado': 'Read the market', 'Tú navegas el mercado; la app mira la pantalla y apunta los precios.': 'You browse the market; the app watches the screen and logs the prices.',
  'Solo lee tu pantalla.': 'It only reads your screen.',
  'Nunca envía clics ni teclas al juego, ni toca su proceso, memoria o red (anticheat). Las imágenes se procesan en memoria y los archivos se borran en cuanto los datos están guardados y verificados.':
    'It never sends clicks or keys to the game, nor touches its process, memory or network (anti-cheat). Images are processed in memory and files are deleted as soon as the data is saved and verified.',
  'Grabar mientras navegas': 'Record while you browse',
  'Pulsa «Empezar», cambia al juego y recorre las pestañas y categorías del mercado a tu ritmo (deja cada pantalla quieta un instante). Vuelve y pulsa «Terminar».':
    'Press "Start", switch to the game and go through the market tabs and categories at your own pace (hold each screen still for a moment). Come back and press "Finish".',
  'Empezar lectura': 'Start reading', 'Terminar': 'Finish', 'Subir un vídeo o una captura': 'Upload a video or a screenshot',
  'OBS, Xbox Game Bar (Win+Alt+R), F12 de Steam o Impr Pant.': 'OBS, Xbox Game Bar (Win+Alt+R), Steam F12 or Print Screen.',
  'Arrastra aquí el archivo o pulsa para elegirlo': 'Drop the file here or click to choose it',
  'Sesiones de lectura': 'Read sessions', 'Revisa las filas dudosas antes de guardar.': 'Review the doubtful rows before saving.',
  'Fecha': 'Date', 'Origen': 'Source', 'Estado': 'Status', 'Filas': 'Rows', 'Dudosas': 'Doubtful', 'Resultado': 'Result',
  'Calibración de la zona de lectura': 'Read area calibration',
  'Una vez por resolución: abre el mercado en el juego, pulsa «Capturar pantalla» (tienes unos segundos para cambiar al juego) o carga una captura, y arrastra un rectángulo sobre la lista de objetos. Opcionalmente marca las columnas de nombre, precio y cantidad (mejora la lectura).':
    'Once per resolution: open the market in the game, press "Capture screen" (you get a few seconds to switch to the game) or load a screenshot, and drag a rectangle over the item list. Optionally mark the name, price and quantity columns (improves reading).',
  'Capturar pantalla (5 s)': 'Capture screen (5 s)', 'Cargar imagen…': 'Load image…', 'Estoy marcando': "I'm marking",
  'Zona de la lista': 'List area', 'Columna nombre': 'Name column', 'Columna precio': 'Price column', 'Columna cantidad': 'Quantity column',
  'Guardar calibración': 'Save calibration', 'Por revisar': 'To review', 'Guardada': 'Saved', 'Error': 'Error',
  'Leyendo…': 'Reading…', '{s} s · {p} pantallas distintas · {f} filas': '{s} s · {p} distinct screens · {f} rows',
  'Grabación': 'Recording', 'Vídeo': 'Video', 'Revisar': 'Review', 'Ver': 'View', 'Todavía no hay lecturas.': 'No reads yet.',
  'Elige un perfil con servidor: las lecturas van al mercado de ese servidor.': "Pick a profile with a server: reads go to that server's market.",
  'Lectura en marcha: cambia al juego y recorre el mercado.': 'Reading started: switch to the game and browse the market.',
  'Lectura terminada: {n} fila(s) para revisar.': 'Reading finished: {n} row(s) to review.', 'Lectura terminada.': 'Reading finished.',
  'Elige un perfil con servidor antes de subir.': 'Pick a profile with a server before uploading.', 'Subiendo {f}…': 'Uploading {f}…', '{f}: procesando…': '{f}: processing…',
  'dudosa': 'doubtful', 'ok': 'ok', 'corregida': 'corrected', 'descartada': 'discarded',
  'Revisión · {n} filas ({d} dudosas)': 'Review · {n} rows ({d} doubtful)', 'Mostrar también las correctas': 'Also show the correct ones',
  'Corrige el objeto, precio o cantidad y pulsa ✓; o descarta la fila con ✕. Al guardar, las filas que sigan pendientes se descartan.':
    'Fix the item, price or quantity and press ✓; or discard the row with ✕. When you save, rows still pending are discarded.',
  'Imagen / leído': 'Image / read', 'Precio': 'Price', 'Cantidad': 'Quantity', 'Motivo': 'Reason', 'Recorte de la fila leída': 'Crop of the read row',
  'Elige objeto…': 'Pick item…', 'Confirmar': 'Confirm', 'Descartar': 'Discard', 'No hay filas dudosas.': 'No doubtful rows.',
  'Guardar sesión ({n} correctas)': 'Save session ({n} correct)', 'Sesión guardada.': 'Session saved.',
  'Elige el objeto correcto de la lista de sugerencias.': 'Pick the right item from the suggestion list.',
  'calibrada': 'calibrated', 'sin calibrar': 'not calibrated', 'Zona de lectura: {z}.': 'Read area: {z}.',
  'Sin calibrar: se lee la pantalla completa (más lento y con más errores).': 'Not calibrated: the whole screen is read (slower and with more errors).',
  'Cambia al juego… {n}': 'Switch to the game… {n}', 'No se pudo capturar la pantalla': 'The screen could not be captured',
  'Imagen {w}×{h}. Arrastra para marcar la <b>zona de la lista</b>{ya}.': 'Image {w}×{h}. Drag to mark the <b>list area</b>{ya}.',
  ' (ya había una calibración para esta resolución)': ' (there was already a calibration for this resolution)',
  'Lista': 'List', 'nombre': 'name', 'precio': 'price', 'cantidad': 'quantity', 'Calibración guardada.': 'Calibration saved.',

  // --- recipes
  'Buscar': 'Search', 'Nombre del producto…': 'Product name…', 'Solo desbloqueadas': 'Unlocked only', 'Producto': 'Product', 'Nivel': 'Level',
  'Elige una receta para ver su coste, beneficio y el árbol de ingredientes.': 'Pick a recipe to see its cost, profit and ingredient tree.',
  '{n} recetas': '{n} recipes', ' de tu facción ({f})': ' from your faction ({f})', 'Mostrando {n} de {total}: afina la búsqueda.': 'Showing {n} of {total}: narrow the search.',
  'Desbloqueada': 'Unlocked', 'Ninguna receta coincide.': 'No recipe matches.', 'Todas': 'All',
  'ambas facciones': 'both factions', 'produce {n}': 'makes {n}', 'Ingreso / intento': 'Revenue / attempt', 'Benef. {n} intento(s)': 'Profit {n} attempt(s)',
  'Éxito (nv. {n})': 'Success (lv. {n})', 'Intentos rentables': 'Profitable attempts',
  'Precio objetivo de venta: <b class="num">{p}</b> ({estado}) → beneficio {b} frente a {ya} vendiendo ya a {pya}.':
    'Target sale price: <b class="num">{p}</b> ({estado}) → profit {b} versus {ya} selling now at {pya}.',
  'Ingredientes y mejor origen': 'Ingredients and best source', 'Desglose por intento': 'Breakdown per attempt', 'Ingrediente': 'Ingredient',
  'Cant.': 'Qty', 'Coste unit.': 'Unit cost', 'Tienes': 'You have', 'Faltan': 'Missing', 'Tienda NPC': 'NPC shop', 'Fabricar': 'Craft', 'Inventario': 'Inventory',
  'mercado {h}': 'market {h}', 'tienes {n}': 'you have {n}', 'sin precio': 'no price', 'fabricar': 'craft',

  // --- character
  'Cada perfil es un personaje en un servidor. La facción del servidor decide el tema de la app.': "Each profile is a character on a server. The server's faction sets the app theme.",
  'Perfiles': 'Profiles', 'Nombre del personaje': 'Character name', 'Servidor': 'Server', 'Guardar perfil': 'Save profile', 'Servidores': 'Servers',
  'Nombre': 'Name', 'p. ej. Ariel': 'e.g. Ariel', 'Facción': 'Faction', 'Comisión de registro (%)': 'Listing fee (%)', 'por defecto': 'default',
  'Impuesto de venta (%)': 'Sales tax (%)', 'Guardar servidor': 'Save server', 'Niveles de artesanía': 'Crafting levels', 'Guardar niveles': 'Save levels',
  'Inventario y almacén': 'Inventory and storage', 'Se descuenta de la lista de la compra si activas «Usar mi inventario» en el Panel.': 'Deducted from the shopping list if you turn on "Use my inventory" on the Dashboard.',
  'Añadir objeto…': 'Add item…', 'Ubicación': 'Location', 'Almacén': 'Storage', 'Guardar': 'Save', 'Pegar una lista de texto': 'Paste a text list',
  'Una línea por objeto: «Mineral de orichalcum: 120». Se empareja con el catálogo; revisa las dudosas antes de guardar.':
    'One line per item: "Orichalcum Ore: 120". It is matched against the catalog; review the doubtful ones before saving.',
  'Lista de inventario en texto': 'Inventory list as text', 'sin servidor': 'no server', ' · sin servidor': ' · no server', 'Crea un perfil': 'Create a profile',
  'Activo': 'Active', 'Usar': 'Use', 'Editar': 'Edit', 'Crea tu primer perfil: primero un servidor (Servidores) y luego tu personaje.': 'Create your first profile: first a server (Servers), then your character.',
  '— sin servidor —': '— no server —', 'comisión {p}': 'fee {p}', 'comisión por defecto': 'default fee', 'impuesto {p}': 'tax {p}', 'impuesto por defecto': 'default tax',
  'Aún no hay servidores.': 'No servers yet.', 'Crea un perfil para guardar sus niveles.': 'Create a profile to save its levels.',
  'Crea un perfil para guardar su inventario.': 'Create a profile to save its inventory.', 'Nivel de {p}': '{p} level', 'Nivel de {p} (deslizador)': '{p} level (slider)',
  'Especialista (51–100)': 'Specialist (51–100)', 'Principiante (1–50)': 'Beginner (1–50)', 'Perfil guardado.': 'Profile saved.', 'Servidor guardado.': 'Server saved.',
  'Crea un perfil primero.': 'Create a profile first.', 'Niveles guardados.': 'Levels saved.', 'Cantidad de {o}': 'Quantity of {o}', 'Quitar': 'Remove',
  'Inventario vacío.': 'Empty inventory.', 'Cantidad actualizada.': 'Quantity updated.', 'Inventario actualizado.': 'Inventory updated.',
  'No hay líneas que leer.': 'There are no lines to read.', 'Texto': 'Text', 'revisar': 'review', 'Guardar en': 'Save to',
  'Guardar las filas con objeto y cantidad': 'Save the rows with item and quantity', 'Ninguna fila tiene objeto y cantidad.': 'No row has an item and a quantity.',
  '{n} objeto(s) guardados.': '{n} item(s) saved.',

  // --- settings
  'Cálculo': 'Calculation', 'Guardar ajustes': 'Save settings', 'Se paga al listar y no se devuelve.': 'Paid when listing and not refunded.',
  'Se descuenta al vender. Cada servidor puede tener los suyos (Personaje).': 'Deducted when selling. Each server can have its own (Character).',
  'Rebaja al listar (Kinah)': 'Undercut when listing (Kinah)', 'Cuánto por debajo del más barato listas.': 'How far below the cheapest listing you list.',
  'Si el combo falla…': 'If the combo fails…', 'Qué obtienes cuando no sale el combo.': 'What you get when the combo does not trigger.',
  'se pierde todo': 'everything is lost', 'queda el producto normal': 'you keep the normal product', 'Valorar inventario': 'Value inventory',
  'Coste de oportunidad de lo que ya tienes.': 'Opportunity cost of what you already have.', 'a precio de mercado': 'at market price', 'a coste 0': 'at zero cost',
  'Precio antiguo a partir de (h)': 'Price is old after (h)', 'Horas para marcar un precio como antiguo.': 'Hours before a price is marked as old.',
  'Intentos recomendados máx.': 'Max. recommended attempts', 'Tope del plan de fabricación.': 'Cap for the crafting plan.',
  'Anuncios activos máx.': 'Max. active listings', 'Para avisar de mercado saturado.': 'Used to warn about a saturated market.',
  'Tope de temporales (MB)': 'Temporary files cap (MB)', 'Espacio máximo para capturas y vídeos pendientes.': 'Maximum space for pending screenshots and videos.',
  'Apariencia': 'Appearance', 'Por defecto el tema sigue la facción del servidor de tu perfil.': "By default the theme follows your profile server's faction.",
  'Forja nocturna': 'Night Forge', 'Atelier claro': 'Bright Atelier', 'Tema': 'Theme', 'Automático o forzar uno.': 'Automatic or force one.',
  'Automático (facción)': 'Automatic (faction)', 'Iconos oficiales del juego': 'Official game icons',
  'Opcional. Se descargan de metabot.gg solo en tu equipo (data/iconos) y nunca se suben a GitHub. Son propiedad de NCSOFT.':
    'Optional. They are downloaded from metabot.gg to your computer only (data/iconos) and never uploaded to GitHub. They are owned by NCSOFT.',
  'Descargar iconos': 'Download icons', 'Qué iconos usar': 'Which icons to use', 'Usar los oficiales': 'Use the official ones', 'Usar los propios': "Use the app's own",
  'Reintentar subir la cola': 'Retry uploading the queue', 'Créditos': 'Credits', 'Datos de recetas, objetos y curvas de éxito:': 'Recipe, item and success-curve data:',
  'Herramienta no oficial: no está afiliada a NCSOFT. AION y AION 2 son marcas de NCSOFT Corporation; los datos del juego son de su propiedad. La app no automatiza el juego: solo lee imágenes de tu pantalla. Úsala bajo tu responsabilidad.':
    'Unofficial tool: not affiliated with NCSOFT. AION and AION 2 are trademarks of NCSOFT Corporation; the game data is their property. The app does not automate the game: it only reads images of your screen. Use it at your own risk.',
  'Precios de tienda NPC': 'NPC shop prices',
  'Para ingredientes vinculados que se compran a un NPC. Los del catálogo vienen de metabot.gg; los que pongas aquí mandan.':
    'For bound ingredients bought from an NPC. Catalog prices come from metabot.gg; the ones you set here take priority.',
  'Precio (Kinah)': 'Price (Kinah)', 'Ajustes guardados.': 'Settings saved.', 'Descargando… {n} de {total}.': 'Downloading… {n} of {total}.',
  'Tienes {n} objetos con icono oficial.': 'You have {n} items with an official icon.', 'Iconos descargados.': 'Icons downloaded.',
  'Precio NPC de {o}': 'NPC price of {o}', 'tuyo': 'yours', 'Volver al precio del catálogo': 'Back to the catalog price', 'Sin precios NPC.': 'No NPC prices.',
  'Precio NPC guardado.': 'NPC price saved.', 'Catálogo': 'Catalog', 'Motor de cálculo': 'Calculation engine', 'OCR': 'OCR',
  'Lector de filas': 'Row reader', 'Modo grabación': 'Recording mode', 'Importar vídeo': 'Video import', 'Calibración': 'Calibration',
  'Limpieza de temporales': 'Temporary files cleanup', 'no disponible': 'not available', 'Supabase conectado.': 'Supabase connected.',
  'Base de datos local (SQLite).': 'Local database (SQLite).', 'Sin base de datos.': 'No database.', '{n} lote(s) en cola.': '{n} batch(es) queued.',
  'Temporales ({n} arch.)': 'Temporary files ({n})', 'Tope temporales': 'Temporary files cap', 'Catálogo del cliente {v}.': 'Game client catalog {v}.',
  'Para guardar el histórico en la nube, crea tu propio proyecto gratuito de Supabase, pon su URL y tu clave secreta en el archivo .env (guía: docs/supabase.md) y reinicia la app.':
    'To keep the history in the cloud, create your own free Supabase project, put its URL and your secret key in the .env file (guide: docs/supabase.md) and restart the app.',
  'Componentes': 'Components', 'Subidos {n} lote(s).': 'Uploaded {n} batch(es).',
  'Sin conexión con la app local': 'No connection to the local app', 'Local (SQLite)': 'Local (SQLite)', 'sin base de datos': 'no database',
  'Base de datos: {bd}': 'Database: {bd}', ' · {n} en cola': ' · {n} queued',
  'No hay conexión con la app local. ¿Sigue abierta la ventana de iniciar.bat?': 'No connection to the local app. Is the iniciar.bat window still open?',
  'Error {n}': 'Error {n}',
  'Herramienta local · los precios se leen de tu pantalla, nunca del juego ·': 'Local tool · prices are read from your screen, never from the game ·',
  'datos: MetaBot.GG': 'data: MetaBot.GG', '· no oficial, sin relación con NCSOFT': '· unofficial, not related to NCSOFT',
};

function t(es, vars) {
  let s = IDIOMA === 'en' && EN[es] != null ? EN[es] : es;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? vars[k] : m));
  return s;
}

// ------------------------------------------------------------------ API messages (they arrive in Spanish)
/* numbers formatted the Spanish way by the backend (2.600,5) → English (2,600.5) */
const numEN = s => String(s).replace(/[.,]/g, c => (c === '.' ? ',' : '.'));
const N = s => traducirNombre(s);
const COMPONENTES_EN = { 'El catálogo de recetas': 'The recipe catalog', 'La base de datos': 'The database' };
const PATRONES_API = [
  [/Receta bloqueada: requiere nivel (\d+) \(tienes (\d+)\)\./g, (m, a, b) => `Recipe locked: requires level ${a} (you have ${b}).`],
  [/Sin precio para (.+?) \(combo\): se valora como (.+?)\.(?=\s|$)/g, (m, a, b) => `No price for ${N(a)} (combo): valued as ${N(b)}.`],
  [/Sin precio para (.+?): no se puede calcular el coste\./g, (m, a) => `No price for ${N(a)}: the cost can't be calculated.`],
  [/No hay suficientes (.+?) en el mercado para (\d+) intentos \(faltan ([\d.,]+)\); se estiman al último precio visto\./g,
    (m, a, b, c) => `Not enough ${N(a)} on the market for ${b} attempts (${c} short); estimated at the last price seen.`],
  [/Sin precio de venta para (.+?)\.(?=\s|$)/g, (m, a) => `No sale price for ${N(a)}.`],
  [/Precio de (.+?) antiguo \((\d+) h\)\./g, (m, a, b) => `Old price for ${N(a)} (${b} h).`],
  [/Producto saturado: (\d+) anuncios activos de (.+?)\.(?=\s|$)/g, (m, a, b) => `Saturated product: ${a} active listings of ${N(b)}.`],
  [/Producto saturado: ([\d.,]+) en oferta y se venden ~([\d.,]+)\/día\./g, (m, a, b) => `Saturated product: ${a} on offer, selling ~${b}/day.`],
  [/Producirás ~([\d.,]+) unidades: necesitarás (\d+) anuncios y el máximo es (\d+) a la vez\./g,
    (m, a, b, c) => `You will make ~${a} units: you will need ${b} listings and the maximum is ${c} at a time.`],
  [/Puedes hacer (\d+) intento\(s\) ya con tu inventario\./g, (m, a) => `You can do ${a} attempt(s) right now with your inventory.`],
  [/Para (\d+) intento\(s\) te faltan: (.+?)(?: \(coste ([\d.,]+) Kinah\))?\.$/g, (m, a, partes, c) =>
    `For ${a} attempt(s) you are missing: ${partes.split(', ').map(p => p.replace(/^([\d.,]+)× (.+)$/, (x, q, n) => `${q}× ${N(n)}`)).join(', ')}${c ? ` (cost ${numEN(c)} Kinah)` : ''}.`],
  [/Mercado saturado: hay ([\d.,]+) unidades en oferta y se venden ~([\d.,]+)\/día \(≈([\d.,]+) días para vaciarlo\)\./g,
    (m, a, b, c) => `Saturated market: ${a} units on offer, selling ~${b}/day (≈${c} days to clear it).`],
  [/Mercado saturado: hay ([\d.,]+) unidades en oferta y no se ha detectado ninguna venta\./g, (m, a) => `Saturated market: ${a} units on offer and no sales detected.`],
  [/Precio hundido: el actual \(([\d.,]+)\) está por debajo de lo normal \(P25 ([\d.,]+)\)\. Mejor listar en torno a la mediana \(([\d.,]+)\) y esperar, o no fabricar todavía\./g,
    (m, a, b, c) => `Sunk price: the current one (${numEN(a)}) is below normal (P25 ${numEN(b)}). Better list around the median (${numEN(c)}) and wait, or don't craft yet.`],
  [/Precio más agresivo: ([\d.,]+)\./g, (m, a) => `More aggressive price: ${numEN(a)}.`],
  [/Buen momento para comprar: ([\d.,]+) ≤ ([\d.,]+)\./g, (m, a, b) => `Good time to buy: ${numEN(a)} ≤ ${numEN(b)}.`],
  [/(El catálogo de recetas|La base de datos) no está disponible todavía \((.+?)\)\./g,
    (m, a, b) => `${COMPONENTES_EN[a]} is not available yet (${b.replace(' o ', ' or ')}).`],
  [/Genera el catálogo con (.+?)\./g, (m, a) => `Build the catalog with ${a}.`],
  [/^Falta ([\w]+)\.$/g, (m, a) => `Missing ${a}.`],
  [/^([\w]+) no es un número válido: (.+)$/g, (m, a, b) => `${a} is not a valid number: ${b}`],
  [/^([\w]+) no puede ser menor que (.+?)\.$/g, (m, a, b) => `${a} can't be lower than ${b}.`],
  [/Valor no válido para (.+?): (.+)\.$/g, (m, a, b) => `Invalid value for ${a}: ${b}.`],
  [/Cada línea del libro de ofertas necesita «precio cantidad»: (.+)$/g, (m, a) => `Each order-book line needs "price quantity": ${a}`],
  [/Guardados (\d+) objeto\(s\) \((\d+) anuncios\)\./g, (m, a, b) => `Saved ${a} item(s) (${b} listings).`],
  [/Ruta de la API desconocida: (.+)$/g, (m, a) => `Unknown API route: ${a}`],
  [/Columna desconocida: (.+?) \(válidas: (.+)\)$/g, (m, a, b) => `Unknown column: ${a} (valid: ${b})`],
  [/La carpeta de temporales ocupa ([\d.]+) MB \(tope ([\d.]+) MB\)\. Hay (\d+) recortes sin revisar y archivos cuyas lecturas aún no se han podido verificar en la base de datos\. Revísalos o sube la cola pendiente; no se borra nada sin verificar\./g,
    (m, a, b, c) => `The temporary files folder takes ${a} MB (cap ${b} MB). There are ${c} unreviewed crops and files whose reads could not be verified in the database yet. Review them or upload the pending queue; nothing is deleted without verification.`],
  [/Descargados (\d+) iconos; (\d+) no se pudieron bajar\./g, (m, a, b) => `Downloaded ${a} icons; ${b} could not be fetched.`],
  [/Descargados (\d+) iconos\./g, (m, a) => `Downloaded ${a} icons.`],
  [/«(.+?)» existe en las dos facciones: indica la facción del servidor/g, (m, a) => `"${N(a)}" exists in both factions: set the server's faction`],
  [/Nombre ambiguo: «(.+?)» o «(.+?)»/g, (m, a, b) => `Ambiguous name: "${N(a)}" or "${N(b)}"`],
  [/Separadores de miles raros en (\w+): «(.+?)»/g, (m, a, b) => `Odd thousands separators in ${t(a)}: "${b}"`],
  [/Separadores de miles raros: «(.+?)»/g, (m, a) => `Odd thousands separators: "${a}"`],
  [/Nombre no reconocido \(¿«(.+?)»\?\)/g, (m, a) => `Name not recognised ("${N(a)}"?)`],
  [/Error en la base de datos local: /g, () => 'Local database error: '],
  [/Sin conexión con Supabase \((\w+)\)/g, (m, a) => `No connection to Supabase (${a})`],
  [/Supabase no disponible \(HTTP (\d+)\)/g, (m, a) => `Supabase not available (HTTP ${a})`],
];
/* fixed API texts; replaced anywhere in the message, longest first */
const FIJOS_API = Object.entries({
  'Curva de éxito desconocida en el catálogo: se asume 100%.': 'Unknown success curve in the catalog: assuming 100%.',
  'Histórico insuficiente: se usa el precio actual.': 'Not enough history: using the current price.',
  'Histórico insuficiente.': 'Not enough history.',
  'El precio actual está por encima de lo habitual: buen momento para vender.': 'The current price is above usual: good time to sell.',
  'Precio por encima de lo habitual.': 'Price above usual.',
  'Crea tu perfil (personaje y servidor) en la pestaña Personaje.': 'Create your profile (character and server) in the Character tab.',
  'Tu perfil no tiene servidor: asígnale uno en Personaje (cada servidor tiene su mercado).': 'Your profile has no server: assign one in Character (each server has its own market).',
  'Aún no hay precios de mercado para este servidor: lee el mercado en Captura, introduce precios a mano en Mercado o importa el Excel.':
    'No market prices for this server yet: read the market in Capture, enter prices by hand in Market or import the Excel file.',
  'El servidor necesita un nombre.': 'The server needs a name.',
  'La facción debe ser «elyos» o «asmodian».': 'The faction must be "elyos" or "asmodian".',
  'El perfil necesita un nombre (tu personaje).': 'The profile needs a name (your character).',
  'Ese servidor no existe: créalo primero.': 'That server does not exist: create it first.',
  'Ese perfil no existe.': 'That profile does not exist.',
  'El nivel máximo de artesanía es 100.': 'The maximum crafting level is 100.',
  'La ubicación debe ser «inventario» o «almacen».': 'The location must be "inventario" or "almacen".',
  'La comisión/impuesto parece demasiado alta.': 'The fee/tax looks too high.',
  'Elige un perfil con servidor para ver su mercado.': 'Pick a profile with a server to see its market.',
  'Falta el servidor: elige un perfil con servidor.': 'The server is missing: pick a profile with a server.',
  'Indica al menos el precio mínimo.': 'Enter at least the minimum price.',
  'Esa receta no existe en el catálogo.': 'That recipe is not in the catalog.',
  'El tipo debe ser «venta» o «compra».': 'The type must be "venta" or "compra".',
  'Esa sesión de lectura no existe.': 'That read session does not exist.',
  'Elige un perfil con servidor: las lecturas se guardan en el mercado de ese servidor.': "Pick a profile with a server: reads are saved to that server's market.",
  'Ese servidor no existe.': 'That server does not exist.',
  'Ya hay una lectura en marcha: termínala primero.': 'A read is already running: finish it first.',
  'Elige un perfil con servidor antes de empezar la lectura.': 'Pick a profile with a server before starting the read.',
  'No hay ninguna lectura en marcha.': 'No read is running.',
  'Formato no admitido: sube un vídeo (mp4, mkv, mov…) o una imagen (png, jpg…).': 'Unsupported format: upload a video (mp4, mkv, mov…) or an image (png, jpg…).',
  'Esta sesión ya no está en revisión.': 'This session is no longer under review.',
  'Esa fila no existe.': 'That row does not exist.',
  'Acción no válida (confirmar | descartar).': 'Invalid action (confirmar | descartar).',
  'Esta sesión ya está guardada o falló.': 'This session is already saved or failed.',
  'Quedan filas por revisar.': 'There are rows left to review.',
  'No hay imagen de esa fila.': 'There is no image for that row.',
  'Marca la zona de la lista del mercado (x, y, ancho, alto).': 'Mark the market list area (x, y, width, height).',
  'La app se cerró mientras se procesaba.': 'The app closed while it was processing.',
  'No se reconoció ninguna fila del mercado. Revisa la calibración.': 'No market row was recognised. Check the calibration.',
  'Sin conexión: quedan en la cola y se subirán al reconectar.': 'Offline: they stay in the queue and will upload when reconnected.',
  'Ese objeto no está en el catálogo.': 'That item is not in the catalog.',
  'El archivo es demasiado grande (máx. 8 GB).': 'The file is too big (max. 8 GB).',
  'El archivo está vacío.': 'The file is empty.',
  'Icono no descargado.': 'Icon not downloaded.',
  'La región debe tener ancho y alto positivos.': 'The region must have a positive width and height.',
  'La región queda fuera de la pantalla.': 'The region is outside the screen.',
  'Marca al menos la columna de nombre o las de precio y cantidad.': 'Mark at least the name column or the price and quantity columns.',
  'Ya tienes todos los iconos.': 'You already have all the icons.',
  'Se puede fabricar, pero no tienes la receta desbloqueada o faltan precios.': "It can be crafted, but you haven't unlocked the recipe or prices are missing.",
  'El precio no está en la columna habitual de esta pantalla': 'The price is not in the usual column for this screen',
  'Hay más números de los esperados en la fila': 'There are more numbers than expected in the row',
  'Precio × cantidad no cuadra con ningún total': 'Price × quantity matches no total',
  'Precio × cantidad no cuadra con el total': 'Price × quantity does not match the total',
  'No está claro cuál es el precio y cuál la cantidad': 'It is unclear which is the price and which the quantity',
  'Precio unitario calculado a partir del total': 'Unit price calculated from the total',
  'Nombre no reconocido': 'Name not recognised', 'Fila sin nombre': 'Row without a name', 'Falta el precio': 'Price missing',
  'Precio no válido': 'Invalid price', 'Falta la cantidad': 'Quantity missing', 'Cantidad no válida': 'Invalid quantity',
}).sort((a, b) => b[0].length - a[0].length);

function tApi(msg) {
  if (IDIOMA !== 'en' || !msg || typeof msg !== 'string') return msg;
  let s = msg;
  for (const [re, fn] of PATRONES_API) { re.lastIndex = 0; s = s.replace(re, fn); }
  for (const [es, en] of FIJOS_API) if (s.includes(es)) s = s.split(es).join(en);
  return s;
}
