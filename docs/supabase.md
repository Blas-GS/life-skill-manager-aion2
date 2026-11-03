# Setting up Supabase (personal database)

**Each user connects the app to their own Supabase project, in their own account.** The repository ships with no URL or key, and there is no shared database: if you download this project, follow these steps with your account and your data will be yours alone.

The app works without Supabase: if `.env` is empty, everything is stored in `data/aion2.db` (on your PC). Supabase keeps your price history in the cloud, survives a change of PC and, later on, will let you check the dashboard from your phone.

## 1. Create the project (free)
1. Go to <https://supabase.com> and create an account (you can use GitHub or your email).
2. **New project**. Choose a name (e.g. `life-skill-manager`), a database password (keep it in your password manager; the app does not need it) and the **Central EU (Frankfurt)** region or the closest one.
3. Leave the **Data API** option enabled if it appears. Wait a couple of minutes for the project to be ready.

## 2. Create the tables
1. In the left menu, open **SQL Editor** → **New query**.
2. Open this project's `supabase/esquema.sql` file, copy its whole content, paste it and click **Run**.
3. It should finish with "Success. No rows returned". You can run it again whenever it changes: it does not delete data.

## 3. Copy the URL and key into `.env`
1. Open the `.env` file in the project folder. `iniciar.bat` creates it the first time by copying `.env.example`; if it does not exist, copy it yourself.
2. In Supabase, click **Connect** (top) or go to **Project Settings → Data API** and copy the **Project URL** (`https://xxxx.supabase.co`) into `SUPABASE_URL=`.
3. Go to **Project Settings → API Keys** and copy the **secret** key (`sb_secret_...`; called `service_role` in older projects) into `SUPABASE_KEY=`.
4. Save the file. The next time you start the app it will use Supabase.

> Paste the key only into `.env`. Do not paste it into chats, screenshots, the browser or any other file.

## Security: why the secret key
- It is a **single-user** database. The schema enables RLS (row level security) on every table **with no policies** and revokes permissions from the public roles. As a result, the public key (`sb_publishable_...` / `anon`) **cannot read or write anything**, even if someone gets hold of it.
- The app uses the secret key, which bypasses RLS, **only from the local backend** (Python, on your PC). The web dashboard talks to `localhost`, never to Supabase, so the key never reaches the browser.
- The app only sends the key over `https://`.
- If you think the key has leaked: **Project Settings → API Keys** → create a new secret key, delete the old one and update `.env`.
- Only numbers and item names are stored in Supabase, never images.

## Offline
If there is no internet or Supabase does not respond, market readings are stored in `data/pendientes.jsonl` and uploaded automatically on the next save with a connection (or from the dashboard). Temporary screenshots and videos **are not deleted** until their data is confirmed in Supabase.

## Note: free projects get paused
Supabase **pauses free projects after ~1 week of inactivity**. While paused, the app keeps working and stores readings in the local queue. To reactivate it: go to supabase.com, open the project and click **Restore project** (it takes a few minutes); the queue is then uploaded automatically. No data is lost while paused.

## Checking that it works
In **Table Editor** you should see the tables `servidores`, `perfiles`, `lecturas_mercado`, `ofertas`, etc. After saving a reading from the app, a row appears in `lecturas_mercado`. The views `precio_diario` (minimum, mean, p25, median and p75 per day) and `ultima_lectura` can be queried the same way from the SQL Editor, e.g. `select * from precio_diario order by dia desc limit 20;`.
