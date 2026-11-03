-- =====================================================================
-- Esquema de la base de datos personal de AION 2 (Supabase / Postgres)
--
-- Cómo aplicarlo: Supabase → SQL Editor → New query → pegar este archivo
-- entero → Run. Se puede ejecutar varias veces sin romper nada
-- (usa "if not exists" / "create or replace").
--
-- Seguridad: es una base de datos de un solo usuario. Todas las tablas
-- tienen RLS activado y NINGUNA política, y se retiran los permisos a los
-- roles públicos (anon, authenticated). Así, la clave pública
-- (publishable / anon) no puede leer ni escribir nada. Solo la clave
-- secreta (secret / service_role), que vive en el .env del PC y la usa
-- únicamente el backend local, tiene acceso. Ver docs/supabase.md.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Servidores, perfiles y personaje
-- ---------------------------------------------------------------------
create table if not exists public.servidores (
    id                text primary key,
    nombre            text not null,
    faccion           text not null check (faccion in ('elyos', 'asmodian')),
    region            text,
    comision_registro double precision,      -- null = usar ajuste global
    impuesto_venta    double precision,      -- null = usar ajuste global
    creado            timestamptz not null default now()
);

create table if not exists public.perfiles (
    id          text primary key,
    nombre      text not null,
    servidor_id text references public.servidores (id) on update cascade on delete set null,
    creado      timestamptz not null default now()
);

create table if not exists public.niveles (
    perfil_id   text not null references public.perfiles (id) on update cascade on delete cascade,
    profesion   text not null,
    nivel       integer not null check (nivel >= 0),
    actualizado timestamptz not null default now(),
    primary key (perfil_id, profesion)
);

create table if not exists public.inventario (
    perfil_id   text not null references public.perfiles (id) on update cascade on delete cascade,
    objeto_id   bigint not null,
    ubicacion   text not null default 'inventario',   -- inventario | almacen | ...
    cantidad    integer not null check (cantidad >= 0),
    actualizado timestamptz not null default now(),
    primary key (perfil_id, objeto_id, ubicacion)
);

-- ---------------------------------------------------------------------
-- Copia del catálogo (opcional; la app funciona con data/catalogo.json)
-- Sin claves foráneas hacia objetos: el catálogo puede estar incompleto.
-- ---------------------------------------------------------------------
create table if not exists public.objetos (
    id          bigint primary key,
    nombre      text not null,
    nombre_en   text,
    grado       text,
    icono       text,
    comerciable boolean,
    vinculado   boolean,
    precio_npc  double precision,
    slug        text
);

create table if not exists public.curvas (
    id      text primary key,
    valores jsonb not null                -- lista de % de éxito
);

create table if not exists public.recetas (
    id             bigint primary key,
    faccion        text not null,         -- elyos | asmodian | ambas
    profesion      text not null,
    nivel          integer not null,
    producto       bigint not null,
    cantidad       integer not null default 1,
    curva          text,
    combo_pct      double precision not null default 0,
    curva_combo    text,
    producto_combo bigint,
    cantidad_combo integer
);

create table if not exists public.receta_ingredientes (
    receta_id bigint not null references public.recetas (id) on delete cascade,
    posicion  integer not null,
    objeto_id bigint not null,
    cantidad  integer not null,
    primary key (receta_id, posicion)
);

-- ---------------------------------------------------------------------
-- Mercado
-- ---------------------------------------------------------------------
create table if not exists public.lecturas_mercado (
    id             uuid primary key default gen_random_uuid(),  -- lo genera la app
    servidor_id    text not null references public.servidores (id) on update cascade,
    objeto_id      bigint not null,
    fecha          timestamptz not null,
    precio_min     double precision,
    cantidad_total integer,               -- unidades en oferta
    num_anuncios   integer,               -- anuncios que muestra el juego
    n_ofertas      integer not null default 0,  -- filas guardadas en "ofertas" (para verificar)
    fuente         text not null check (fuente in ('grabacion', 'video', 'captura', 'manual', 'excel')),
    sesion_id      text,
    creado         timestamptz not null default now()
);

create index if not exists lecturas_servidor_objeto_fecha
    on public.lecturas_mercado (servidor_id, objeto_id, fecha desc);
create index if not exists lecturas_sesion
    on public.lecturas_mercado (sesion_id);

create table if not exists public.ofertas (
    lectura_id uuid not null references public.lecturas_mercado (id) on delete cascade,
    posicion   integer not null,          -- 0 = más barata
    precio     double precision not null,
    cantidad   integer not null,
    primary key (lectura_id, posicion)
);

create table if not exists public.precios_npc (
    objeto_id   bigint primary key,
    precio      double precision not null,
    actualizado timestamptz not null default now()
);

-- Ventas y compras propias (pestaña de liquidación). precio = por unidad.
create table if not exists public.operaciones (
    id        uuid primary key default gen_random_uuid(),
    perfil_id text references public.perfiles (id) on update cascade on delete set null,
    tipo      text not null check (tipo in ('venta', 'compra')),
    objeto_id bigint not null,
    cantidad  integer not null,
    precio    double precision not null,
    fecha     timestamptz not null,
    creado    timestamptz not null default now()
);

create index if not exists operaciones_perfil_fecha
    on public.operaciones (perfil_id, fecha desc);

create table if not exists public.ajustes (
    clave       text primary key,
    valor       jsonb,
    actualizado timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Vistas (security_invoker: respetan el RLS de quien consulta)
-- ---------------------------------------------------------------------

-- Resumen diario por servidor y objeto (día en UTC).
create or replace view public.precio_diario
with (security_invoker = true) as
select
    servidor_id,
    objeto_id,
    (fecha at time zone 'utc')::date                                   as dia,
    min(precio_min)                                                    as precio_min,
    avg(precio_min)                                                    as precio_medio,
    percentile_cont(0.25) within group (order by precio_min)           as p25,
    percentile_cont(0.50) within group (order by precio_min)           as mediana,
    percentile_cont(0.75) within group (order by precio_min)           as p75,
    avg(cantidad_total)                                                as cantidad_media,
    count(*)                                                           as num_lecturas
from public.lecturas_mercado
where precio_min is not null
group by servidor_id, objeto_id, (fecha at time zone 'utc')::date;

-- La lectura más reciente por servidor y objeto.
create or replace view public.ultima_lectura
with (security_invoker = true) as
select distinct on (servidor_id, objeto_id) *
from public.lecturas_mercado
order by servidor_id, objeto_id, fecha desc;

-- ---------------------------------------------------------------------
-- RLS y permisos
-- ---------------------------------------------------------------------
alter table public.servidores          enable row level security;
alter table public.perfiles            enable row level security;
alter table public.niveles             enable row level security;
alter table public.inventario          enable row level security;
alter table public.objetos             enable row level security;
alter table public.curvas              enable row level security;
alter table public.recetas             enable row level security;
alter table public.receta_ingredientes enable row level security;
alter table public.lecturas_mercado    enable row level security;
alter table public.ofertas             enable row level security;
alter table public.precios_npc         enable row level security;
alter table public.operaciones         enable row level security;
alter table public.ajustes             enable row level security;

-- Las claves públicas no tocan nada (defensa en profundidad además del RLS).
revoke all on
    public.servidores, public.perfiles, public.niveles, public.inventario,
    public.objetos, public.curvas, public.recetas, public.receta_ingredientes,
    public.lecturas_mercado, public.ofertas, public.precios_npc,
    public.operaciones, public.ajustes,
    public.precio_diario, public.ultima_lectura
from anon, authenticated;

-- La clave secreta (rol service_role, ignora RLS) necesita los permisos
-- por si el proyecto se creó sin "exponer tablas nuevas automáticamente".
grant select, insert, update, delete on
    public.servidores, public.perfiles, public.niveles, public.inventario,
    public.objetos, public.curvas, public.recetas, public.receta_ingredientes,
    public.lecturas_mercado, public.ofertas, public.precios_npc,
    public.operaciones, public.ajustes
to service_role;
grant select on public.precio_diario, public.ultima_lectura to service_role;
grant usage on schema public to service_role;
