# Contributing

Thanks for wanting to improve the project! It is Open Source ([MIT](LICENSE) license) and maintained by its author, who reviews and approves every change before merging it.

## Kinds of contribution

| Kind | How |
|---|---|
| Bug fixes | Open a PR directly. If the bug is not obvious, describe how to reproduce it. |
| Code improvements that do not change behaviour (performance, cleanup, tests, documentation, OCR accuracy) | Open a PR directly. |
| New features or behaviour changes (new screens, changes to the profitability or target-price calculation, new data sources, database changes) | **Open an issue first** and discuss it with the author. Start coding once the idea has been agreed. |

Every PR is merged **only with the author's approval**; the author may ask for changes or decline PRs that do not fit the project.

## Non-negotiable rules

- **Never automate the game.** No simulated clicks or keystrokes, no reading or writing process memory, no client modification, no network traffic capture, nothing that interacts with the game process or its anti-cheat. The app only reads screen images that the user produces by browsing manually. This protects users' accounts from bans.
- **No third-party data or assets in the repository.** Do not commit icons, images or game data (they belong to NCSOFT), nor the metabot.gg catalog or cache. They are generated locally with `tools/importar_metabot.py`.
- **No secrets.** Never commit a `.env` file, Supabase keys or personal data (databases, screenshots, inventories).
- **Respect metabot.gg's terms.** Keep the attribution and the importer's slow download pace.

## Steps

1. Fork the repository and create a branch with a descriptive name (`fix-ocr-prices`, `improve-offline-queue`…).
2. Set up the environment: `iniciar.bat` creates `.venv` and installs the dependencies (Windows, Python 3.14).
3. Make your changes. Code comments, commit messages and PRs are written in **English**. Code identifiers are in Spanish; keep the existing naming. The interface uses the official Spanish client names, with an ES/EN language switch.
4. Run the tests and add tests that cover your change:
   ```bash
   .\.venv\Scripts\python.exe -m pytest
   ```
5. Open the PR against `main`, explaining what changes and why, and link the issue if there is one.

## Questions

Open an issue. For anything other than a fix or a small improvement, discuss it in an issue first.
