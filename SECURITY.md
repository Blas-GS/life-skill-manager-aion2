# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub instead:
**Security** tab → **Report a vulnerability**
(<https://github.com/Blas-GS/life-skill-manager-aion2/security/advisories/new>).

Include what you found, how to reproduce it and what impact you expect. You will get an answer
as soon as possible; this is a personal project maintained in spare time, so please allow a few days.

## Scope

Life Skill Manager runs locally on your own machine and talks to **your own** Supabase project.
Things worth reporting include:

- Any way the Supabase secret key could leak (to the browser, logs, the repository, etc.).
- Ways a web page or another local process could make the app read or write data it should not.
- Unsafe handling of the screenshots, videos or files the app processes.

Out of scope: the game itself, metabot.gg, and Supabase's own platform.

## Supported versions

Only the latest version on the `main` branch is supported.
