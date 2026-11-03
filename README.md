# Life Skill Manager - Aion 2

**Open Source project** (MIT license). Pull requests that fix bugs or improve the code are welcome and are merged subject to the author's approval. If you want to add a new feature or change how something behaves, **open an issue first** to discuss it before writing code. See [Contributing](#contributing).

A local tool that tells you **which AION 2 crafting recipes are worth making right now**, buying the ingredients on your server's market and selling the product. It takes into account your levels in the 5 professions, your inventory and warehouse, the listing fee and sales tax, the success and combo chances, market depth and price history.

Tabs: **Dashboard** (best opportunities, shopping list), **Market** (prices, history, target price, manual entry), **Capture** (passive OCR reading of the market), **Recipes** (ingredient tree, buy or craft), **Character** (profiles, servers, levels, inventory) and **Settings**.

The interface uses the official item names of the Spanish game client; an ES/EN language switch is in progress.

## Getting started

Double-click **`iniciar.bat`**. The first time, it creates the Python environment (`.venv`, Python 3.14) and installs the dependencies; then it starts the app and opens `http://localhost:8000`.

Manually:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

First steps:
1. **Character** → create your server (name and faction) and your profile; enter your levels.
2. Seed prices: read the market (**Capture**), type them in (**Market**) or import an Excel sheet:

```bash
.\.venv\Scripts\python.exe tools\importar_excel.py --servidor <server_id>
```

   (`--simular` shows the report without saving.)
3. **Dashboard** → recipes sorted by profit.

The recipe catalog (`data/catalogo.json`) **is not included in the repository**: `iniciar.bat` builds it the first time with `tools\importar_metabot.py`, which downloads it from metabot.gg at a slow pace (one request every 2 s, cached so nothing is fetched twice). It takes a few minutes.

## Database: your own Supabase (or local)

**Everyone uses their own database.** This repository does not include or share any database, URL or key: your prices, inventory and history go to **your** Supabase account, and nobody else can see them.

- **With no setup**, everything is stored on your PC in `data/aion2.db` (SQLite). It works the same, but the history stays on that machine.
- **With Supabase** (free), the history lives in the cloud and survives a change of PC. One-time setup:
  1. Create an account at [supabase.com](https://supabase.com) and a new project (**Free** plan, region **Central EU (Frankfurt)** or the closest one).
  2. In your project: **SQL Editor → New query**, paste the whole [`supabase/esquema.sql`](supabase/esquema.sql) and click **Run**. It creates the tables with access blocked for public keys.
  3. `iniciar.bat` creates a `.env` file from [`.env.example`](.env.example). Open it and fill in:
     - `SUPABASE_URL=` your project's **Project URL** (`https://<your-project>.supabase.co`).
     - `SUPABASE_KEY=` your **secret** key (`sb_secret_...`, under **Project Settings → API Keys**).
  4. Restart the app. **Settings** should show "Database: Supabase".

Detailed guide, security notes and what to do if the project gets paused: [docs/supabase.md](docs/supabase.md).

> `.env` is listed in `.gitignore`: **never** upload it to GitHub or share your secret key. Only the program on your PC uses it; it never reaches the browser.

When offline, market readings are stored in a local queue (`data/pendientes.jsonl`) and uploaded automatically once the connection is back.

## Reading the market without risking a ban

AION 2 has an anti-cheat (NCGuard) and NCSOFT forbids automation. That is why **the app never touches the game**: it does not send clicks or keystrokes, read its memory, modify the client or capture its network traffic. It only looks at the screen, just like a video recording:

- **Recording mode**: click *Start reading*, browse the market yourself with mouse and keyboard, then click *Finish*. Frames are processed in memory.
- **Video**: record with OBS or the Xbox Game Bar (Win+Alt+R) and drop the file into *Capture*.
- **Single screenshot**: Steam's F12 or Print Screen, then upload it.

Calibrate the list area once (*Capture* tab) and review uncertain rows before saving. Videos and screenshots are deleted automatically once their data has been saved and verified.

## Tests

```bash
.\.venv\Scripts\python.exe -m pytest
```

## Legal notice

- **Unofficial tool.** It is not affiliated with, sponsored or endorsed by NCSOFT. AION and AION 2 are trademarks of NCSOFT Corporation; they are mentioned only to indicate which game this tool works with.
- **It does not automate the game.** It sends no input, does not read or modify the client's memory or files, does not intercept its network traffic and does not bypass the anti-cheat. It only processes images of your own screen, produced by you browsing the market by hand.
- **Use it at your own risk.** NCSOFT's rules on third-party programs may change and no list of allowed tools is published. Check their terms before using it; the author is not responsible for any penalty on your account.
- **No warranty.** Profitability figures are estimates; see [LICENSE](LICENSE).
- **Personal, non-profit use.** It does not sell data or services, and it does not involve real-money trading.
- **Game data.** Item names, recipes and probabilities belong to NCSOFT. This repository does not redistribute them: each user builds their catalog locally.

## Attribution

Recipe, item and success-curve data: [MetaBot.GG — AION 2 Crafting](https://metabot.gg/es_ES/aion-2/crafting), following their [attribution requirement](https://metabot.gg/en/ai). The metabot.gg [Terms of Service](https://metabot.gg/en/legal/terms-of-service) allow personal, non-commercial use.

## Contributing

This is an open-source project and contributions are welcome:

- **Bug fixes and code improvements** (performance, cleanup, tests, documentation, OCR accuracy): open a PR directly. It is reviewed and merged only with the author's approval.
- **New features or behaviour changes** (new screens, changes to the profitability calculation, new data sources…): **open an issue first** to discuss it with the author before writing code. That way nobody wastes time on a PR that does not fit the project's direction.

Rules and steps in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Code released under the [MIT](LICENSE) license. The license does not cover game data or metabot.gg data.
