# Configurar Supabase (base de datos personal)

**Cada usuario conecta la app a su propio proyecto de Supabase, en su propia cuenta.** El repositorio no trae ninguna URL ni clave, y no hay una base de datos compartida: si descargas este proyecto, sigue estos pasos con tu cuenta y tus datos solo serán tuyos.

La app funciona sin Supabase: si `.env` no tiene datos, guarda todo en `data/aion2.db` (en tu PC). Supabase sirve para tener el histórico de precios en la nube, sobrevivir a un cambio de PC y, más adelante, consultar el panel desde el móvil.

## 1. Crear el proyecto (gratis)
1. Entra en <https://supabase.com> y crea una cuenta (puedes usar GitHub o tu correo).
2. **New project**. Elige un nombre (p.ej. `aion2`), una contraseña de base de datos (guárdala en tu gestor de contraseñas; la app no la necesita) y la región **Central EU (Frankfurt)** o la más cercana.
3. Deja activada la opción **Data API** si aparece. Espera un par de minutos a que el proyecto esté listo.

## 2. Crear las tablas
1. En el menú izquierdo, abre **SQL Editor** → **New query**.
2. Abre el archivo `supabase/esquema.sql` de este proyecto, copia todo su contenido, pégalo y pulsa **Run**.
3. Debe terminar con "Success. No rows returned". Puedes volver a ejecutarlo cuando haya cambios: no borra datos.

## 3. Copiar la URL y la clave a `.env`
1. Abre el archivo `.env` de la carpeta del proyecto. `iniciar.bat` lo crea la primera vez copiando `.env.example`; si no existe, cópialo tú.
2. En Supabase, pulsa **Connect** (arriba) o ve a **Project Settings → Data API** y copia la **Project URL** (`https://xxxx.supabase.co`) en `SUPABASE_URL=`.
3. Ve a **Project Settings → API Keys** y copia la clave **secreta** (`sb_secret_...`; en proyectos antiguos se llama `service_role`) en `SUPABASE_KEY=`.
4. Guarda el archivo. La próxima vez que arranques la app usará Supabase.

> Pega la clave solo en `.env`. No la pegues en el chat, en capturas, en el navegador ni en ningún otro archivo.

## Seguridad: por qué la clave secreta
- Es una base de datos de **un solo usuario**. El esquema activa RLS (seguridad por filas) en todas las tablas **sin ninguna política** y retira los permisos a los roles públicos. Resultado: la clave pública (`sb_publishable_...` / `anon`) **no puede leer ni escribir nada**, aunque alguien la consiga.
- La app usa la clave secreta, que se salta el RLS, **solo desde el backend local** (Python, en tu PC). El panel web habla con `localhost`, nunca con Supabase, así que la clave no llega al navegador.
- La app solo envía la clave por `https://`.
- Si crees que la clave se ha filtrado: **Project Settings → API Keys** → crea una nueva clave secreta, borra la antigua y actualiza `.env`.
- En Supabase solo se guardan números y nombres de objetos, nunca imágenes.

## Sin conexión
Si no hay internet o Supabase no responde, las lecturas del mercado se guardan en `data/pendientes.jsonl` y se suben solas en el siguiente guardado con conexión (o desde el panel). Las capturas y vídeos temporales **no se borran** hasta que sus datos están confirmados en Supabase.

## Aviso: el plan gratuito se pausa
Supabase **pausa los proyectos gratuitos tras ~1 semana sin actividad**. Mientras está pausado, la app sigue funcionando y guarda las lecturas en la cola local. Para reactivarlo: entra en supabase.com, abre el proyecto y pulsa **Restore project** (tarda unos minutos); después la cola se sube sola. Los datos no se pierden al pausar.

## Comprobar que funciona
En **Table Editor** deberías ver las tablas `servidores`, `perfiles`, `lecturas_mercado`, `ofertas`, etc. Tras guardar una lectura desde la app, aparecerá una fila en `lecturas_mercado`. Las vistas `precio_diario` (mínimo, media, p25, mediana y p75 por día) y `ultima_lectura` se consultan igual desde el SQL Editor, p.ej. `select * from precio_diario order by dia desc limit 20;`.
