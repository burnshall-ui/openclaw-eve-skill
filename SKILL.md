---
name: eve-esi
description: "Query and manage EVE Online characters via the ESI (EVE Swagger Interface) REST API. Performs OAuth2/PKCE browser login and stores plus auto-refreshes long-lived OAuth tokens locally in ~/.openclaw/eve-tokens.json. Read-only by default and can reach any ESI endpoint, including non-character public data; state-changing writes (mail, fittings, market orders, planetary interaction) happen only when explicitly invoked with --allow-write. Use when the user asks about EVE Online character data, wallet balance, ISK transactions, assets, skill queue, skill points, clone locations, implants, fittings, contracts, market orders, mail, industry jobs, killmails, planetary interaction, loyalty points, or any other EVE account management task."
type: scripts
includes:
  - scripts/auth_flow.py
  - scripts/get_token.py
  - scripts/esi_query.py
  - scripts/validate_config.py
  - config/schema.json
  - config/example-config.json
  - config/esi_endpoints.json
  - references/authentication.md
  - references/endpoints.md
auth:
  method: oauth2_pkce
  provider: EVE SSO (login.eveonline.com)
  credential_storage: "~/.openclaw/eve-tokens.json"
  setup: "Run scripts/auth_flow.py once per character with a valid EVE Client ID. Tokens are stored locally and auto-refreshed by scripts/get_token.py."
  required_for: "All authenticated ESI endpoints (wallet, assets, skills, PI, industry, etc.). Public endpoints work without auth."
env:
  - name: EVE_CLIENT_ID
    description: "EVE Developer Application Client ID (from https://developers.eveonline.com/applications). Not needed at runtime — pass directly to auth_flow.py via --client-id. Only set as env var if using $ENV: references in your dashboard config."
    required: false
    sensitive: false
  - name: EVE_TOKEN_MAIN
    description: "ESI OAuth2 access token for the main character. Not needed at runtime — scripts auto-manage tokens via ~/.openclaw/eve-tokens.json (created by auth_flow.py). Only set as env var if using $ENV: references in your dashboard config."
    required: false
    sensitive: true
  - name: EVE_REFRESH_MAIN
    description: "ESI OAuth2 refresh token for automatic access token renewal. Not needed at runtime — scripts auto-manage tokens via ~/.openclaw/eve-tokens.json. Only set as env var if using $ENV: references in your dashboard config."
    required: false
    sensitive: true
  - name: TELEGRAM_BOT_TOKEN
    description: "Telegram Bot API token for sending alerts and reports. Only needed if Telegram notifications are configured."
    required: false
    sensitive: true
  - name: TELEGRAM_CHAT_ID
    description: "Telegram chat ID where notifications are sent. Only needed if Telegram notifications are configured."
    required: false
    sensitive: false
  - name: DISCORD_WEBHOOK_URL
    description: "Discord webhook URL for sending alerts and reports. Only needed if Discord notifications are configured."
    required: false
    sensitive: true
---

# Data Handling

This skill communicates with the following external services. Every outbound
call is either a public/unauthenticated CCP endpoint, an OAuth2 flow against
the official EVE SSO, or an optional, user-configured notification sink.

- **EVE Online ESI API** (`esi.evetech.net`) — official EVE Online REST API
  (operated by CCP Games) for all character and universe data queries.
  Includes bulk lookup endpoints such as `POST /latest/characters/affiliation/`
  and `POST /latest/universe/names/`, which resolve public numeric IDs
  (character/corp/alliance/type IDs) to public data. These POST bodies never
  contain tokens, credentials, or private account data — only IDs that are
  already public in-game. Authenticated endpoints (wallet, assets, skills,
  etc.) send the OAuth2 bearer token only to this same host, per ESI's own
  API contract.
- **EVE SSO** (`login.eveonline.com`) — official OAuth2/PKCE authorization
  server for EVE Online. Used only for the login/token-refresh flow described
  in `references/authentication.md`.
- **EVE Developer Portal** (`developers.eveonline.com/applications`) —
  official CCP portal where the *user* registers their own EVE application
  and obtains a Client ID. This skill never calls this URL programmatically;
  it is referenced in documentation only, as the one-time manual step a user
  performs before running `scripts/auth_flow.py --client-id <...>`.
- **zKillboard API** (`zkillboard.com/api/`) — optional, public, unauthenticated.
  Only used for PVP threat-assessment features; disabled unless threat/route
  scripts are invoked.
- **Telegram Bot API** — optional, only contacted if the user sets
  `TELEGRAM_BOT_TOKEN` and configures alerts.
- **Discord Webhooks** — optional, only contacted if the user sets
  `DISCORD_WEBHOOK_URL` and configures alerts.

No character data, tokens, or credentials are sent to any third-party server
beyond the above. Telegram/Discord only receive the specific alert text the
user has configured — never raw account data or tokens.

# What this skill can access, and what it will not do

**Read-only by default.** GET requests and the documented bulk-lookup POST
endpoints run normally. Any other POST, plus PUT and DELETE, is refused unless
you pass `--allow-write` explicitly. Without that flag this skill cannot send
mail, change contacts, alter contracts, open in-game windows, or modify your
account in any way.

**Sensitive data.** The scopes you grant during `auth_flow.py` decide what the
skill can read. Several are genuinely private: wallet balance and full ISK
transaction history, complete asset lists, mail contents, contracts, clone and
implant locations, and current in-space location. Grant only the scopes your
use case needs — the skill works fine with a narrow scope set, and public
endpoints need no scopes at all.

**Token handling.** Access tokens are bearer credentials: anyone holding one can
read your account until it expires (~20 min). Refresh tokens are long-lived and
rotate on each use.

- Prefer `esi_query.py --char <name>`, which refreshes the token in-process. The
  token never enters argv.
- Avoid `--token "$TOKEN"` and `curl -H "Authorization: Bearer $TOKEN"`: command
  lines are visible to any local user via `ps`, and land in your shell history.
  Use `--token-stdin` when a token must come from outside.
- Never paste a token into a config file, a bug report, a log, or a chat message.

**Alert transmission.** If you configure Telegram or Discord, the alert text you
define is sent to those services in plaintext over their APIs. Do not template
raw wallet figures or asset inventories into alerts you would not want stored on
a third-party server.

# EVE Online ESI

The ESI (EVE Swagger Interface) is the official REST API for EVE Online third-party development.

- Base URL: `https://esi.evetech.net/latest`
- Spec: `https://esi.evetech.net/latest/swagger.json`
- API Explorer: <https://developers.eveonline.com/api-explorer>

## Skill Location

All scripts live at: `~/.openclaw/workspace/skills/eve-esi/scripts/`

Always use full paths when calling scripts:
```bash
SKILL=~/.openclaw/workspace/skills/eve-esi
```

## Authentication

Tokens are stored in `~/.openclaw/eve-tokens.json` (created by auth_flow.py, chmod 600).
All scripts (`get_token.py`, `esi_query.py`) read from this file directly — **no env vars are required for normal operation.**

**First-time setup** (once per character):
```bash
# 1. Set up SSH tunnel on your local PC:
#    ssh -L 8080:127.0.0.1:8080 user@your-server -N
# 2. Run auth flow on server (pass Client ID directly):
python3 ~/.openclaw/workspace/skills/eve-esi/scripts/auth_flow.py --client-id <YOUR_CLIENT_ID> --char-name main
# 3. Open the shown URL in browser, log in with EVE account
```

**Preferred: let the query script handle the token.** `--char <name>` resolves and
refreshes the token in-process, so it never appears on a command line, in shell
history, or in your logs:
```bash
python3 ~/.openclaw/workspace/skills/eve-esi/scripts/esi_query.py --char main \
  --endpoint "/characters/<CHAR_ID>/wallet/" --pretty
```

Only if you genuinely need the raw token elsewhere (it expires after ~20 min,
refresh is automatic):
```bash
python3 ~/.openclaw/workspace/skills/eve-esi/scripts/get_token.py --char main
```
Do not capture it into a shell variable and pass it as `--token "$TOKEN"` —
that exposes it via `ps` and shell history. Use `--token-stdin` if a token must
be handed over.

**List authenticated characters:**
```bash
python3 ~/.openclaw/workspace/skills/eve-esi/scripts/get_token.py --list
```

For full OAuth2/PKCE details: see `references/authentication.md`.

## Public endpoints (no auth)

```bash
# Character public info
curl -s "https://esi.evetech.net/latest/characters/2114794365/" | python -m json.tool

# Portrait URLs
curl -s "https://esi.evetech.net/latest/characters/2114794365/portrait/"

# Corporation history
curl -s "https://esi.evetech.net/latest/characters/2114794365/corporationhistory/"

# Bulk affiliation lookup
curl -s -X POST "https://esi.evetech.net/latest/characters/affiliation/" \
  -H "Content-Type: application/json" \
  -d '[2114794365, 95538921]'
```

## Character info (authenticated)

> The `curl` examples below are shown for reference against the raw ESI API.
> They put the token on a command line, where `ps` and shell history expose it.
> For day-to-day use prefer `esi_query.py --char <name>` (see
> [Using the query script](#using-the-query-script)).

```bash
TOKEN="<your_access_token>"
CHAR_ID="<your_character_id>"

# Online status (scope: esi-location.read_online.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/online/"
```

## Wallet

```bash
# Balance (scope: esi-wallet.read_character_wallet.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/wallet/"

# Journal (paginated)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/wallet/journal/?page=1"

# Transactions
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/wallet/transactions/"
```

## Assets

```bash
# All assets (paginated; scope: esi-assets.read_assets.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/assets/?page=1"

# Resolve item locations
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[1234567890, 9876543210]' \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/assets/locations/"

# Resolve item names
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[1234567890]' \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/assets/names/"
```

## Skills

```bash
# All trained skills + total SP (scope: esi-skills.read_skills.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/skills/"

# Skill queue (scope: esi-skills.read_skillqueue.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/skillqueue/"

# Attributes (intelligence, memory, etc.)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/attributes/"
```

## Location and ship

```bash
# Current location (scope: esi-location.read_location.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/location/"

# Current ship (scope: esi-location.read_ship_type.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/ship/"
```

## Clones and implants

```bash
# Jump clones + home station (scope: esi-clones.read_clones.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/clones/"

# Active implants (scope: esi-clones.read_implants.v1)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/implants/"
```

## More endpoints

For contracts, fittings, mail, industry, killmails, market orders, mining, planetary interaction, loyalty points, notifications, blueprints, standings, and all other character endpoints, see [references/endpoints.md](references/endpoints.md).

## Dashboard Config

The skill supports a modular dashboard config for alerts, reports, and market tracking. Each user defines what they need in a JSON config file.

- **Schema**: [config/schema.json](config/schema.json) — full JSON Schema with all fields, types, and defaults
- **Example**: [config/example-config.json](config/example-config.json) — ready-to-use template

### Features

| Module | Description |
|--------|-------------|
| **Alerts** | Real-time polling for war decs, structure attacks, skill completions, wallet changes, industry jobs, PI extractors, killmails, contracts, clone jumps, mail |
| **Reports** | Cron-scheduled summaries: net worth, skill queue, industry, market orders, wallet, assets |
| **Market** | Price tracking with absolute thresholds and trend detection |

### Security

Do **not** write tokens into the dashboard config file. There are two supported
places for credentials, and they do not conflict:

| Location | What lives there | Who writes it |
|----------|------------------|---------------|
| `~/.openclaw/eve-tokens.json` | The canonical token store: refresh tokens + client IDs, one entry per character. Created `chmod 600`, rewritten atomically, lock-protected. | `auth_flow.py` / `get_token.py` |
| Dashboard config JSON | No secrets. Reference env vars if a value is unavoidable. | You |

The scripts read the token store directly, so a normal setup needs **no**
credentials in the config file and no env vars at all. Only use `$ENV:`
references if you drive the dashboard from a system that cannot reach the
token store:

```json
{
  "token": "$ENV:EVE_TOKEN_MAIN",
  "refresh_token": "$ENV:EVE_REFRESH_MAIN"
}
```

The config file should live outside the workspace (e.g. `~/.openclaw/eve-dashboard-config.json`).

### Validate a config

```bash
python scripts/validate_config.py path/to/config.json

# Show example config
python scripts/validate_config.py --example

# Show JSON schema
python scripts/validate_config.py --schema
```

## Using the query script

Pass `--char <name>` and the script refreshes the stored token itself. The token
never appears on a command line, so `ps` and shell history cannot leak it.

```bash
SKILL=~/.openclaw/workspace/skills/eve-esi
# Replace 'main' with your --char-name if you authenticated under a different name.
CHAR_ID=$(python3 $SKILL/scripts/get_token.py --char main --char-id)

# Simple query
python3 $SKILL/scripts/esi_query.py --char main --endpoint "/characters/$CHAR_ID/wallet/" --pretty

# Fetch all pages of assets
python3 $SKILL/scripts/esi_query.py --char main --endpoint "/characters/$CHAR_ID/assets/" --pages --pretty

# Bulk lookup POST (asset names) — a read-only lookup, no --allow-write needed
python3 $SKILL/scripts/esi_query.py --char main --endpoint "/characters/$CHAR_ID/assets/names/" \
  --method POST --body '[1234567890]' --pretty
```

If you must supply a token from elsewhere, pipe it in rather than passing `--token`:

```bash
printf '%s\n' "$TOKEN" | python3 $SKILL/scripts/esi_query.py --token-stdin --endpoint /characters/$CHAR_ID/wallet/
```

## Best practices

- **Caching**: respect the `Expires` header; do not poll before it expires.
- **Error limits**: monitor `X-ESI-Error-Limit-Remain`; back off when low.
- **User-Agent**: always set a descriptive User-Agent with contact info.
- **Rate limits**: some endpoints (mail, contracts) have internal rate limits returning HTTP 520.
- **Pagination**: check the `X-Pages` response header; iterate with `?page=N`.
- **Versioning**: use `/latest/` for current stable routes. `/dev/` may change without notice.

## Threat Assessment & Route Planning

The skill provides threat intelligence for PI systems in low/null-sec space. Data sources: ESI (kills, jumps, FW, incursions) and zKillboard (PVP activity).

### ESI Threat Endpoints

```bash
SKILL=~/.openclaw/workspace/skills/eve-esi

# System kills (last hour) — all or filtered
python3 $SKILL/scripts/esi_query.py --action system_kills --pretty
python3 $SKILL/scripts/esi_query.py --action system_kills --system-ids 30002537,30045337 --pretty

# System jump traffic (last hour)
python3 $SKILL/scripts/esi_query.py --action system_jumps --system-ids 30045337 --pretty

# System info (name, security status)
python3 $SKILL/scripts/esi_query.py --action system_info --system-id 30002537 --pretty

# Route planning (flags: secure, shortest, insecure)
python3 $SKILL/scripts/esi_query.py --action route_plan --origin 30000142 --destination 30002537 --route-flag secure --pretty

# Character location (requires auth)
python3 $SKILL/scripts/esi_query.py --action character_location --char main --character-id $CHAR_ID --pretty

# Faction warfare systems
python3 $SKILL/scripts/esi_query.py --action fw_systems --pretty

# Active incursions
python3 $SKILL/scripts/esi_query.py --action incursions --pretty
```

### Threat Assessment Scripts (Workspace)

> **Hinweis:** Die Workspace-Skripte (`threat_query.py`, `cache_threat_data.py`, `cache_market_prices.py`) sind Referenz-Beschreibungen und müssen erst im Agent-Workspace erstellt werden, bevor sie genutzt werden können.

These scripts live in `~/.openclaw/workspace/scripts/` (not in the skill repo):

```bash
# Threat level for specific systems
python3 ~/.openclaw/workspace/scripts/threat_query.py --action threat_assessment --system-ids 30002537,30045337

# Threat for all PI systems across all characters
python3 ~/.openclaw/workspace/scripts/threat_query.py --action threat_assessment_pi

# Route with per-system threat annotation
python3 ~/.openclaw/workspace/scripts/threat_query.py --action route_annotated --origin 30000142 --destination 30002537

# Route from character's current location
python3 ~/.openclaw/workspace/scripts/threat_query.py --action route_annotated --character main --destination 30045337

# Full PI + Threat morning briefing
python3 ~/.openclaw/workspace/scripts/threat_query.py --action pi_briefing
```

### Threat Levels

| Level | Score | Meaning |
|-------|-------|---------|
| `low` | 0-15 | Normaler PI-Betrieb |
| `medium` | 15-40 | Schnell rein, schnell raus |
| `high` | 40-80 | Nur mit Scout/Cloak |
| `critical` | 80+ | NICHT reinfliegen |

### Threat Cache

Threat data is cached in Redis (30min TTL for ESI, 1h for zKillboard). The cache is updated every 30 minutes via cron:

```bash
# Update cache manually
python3 ~/.openclaw/workspace/scripts/cache_threat_data.py

# Show cached threat data
python3 ~/.openclaw/workspace/scripts/cache_threat_data.py --check
```

## Resolving type IDs

ESI returns numeric type IDs (e.g. for ships, items, skills). Resolve names via:

```bash
# Single type
curl -s "https://esi.evetech.net/latest/universe/types/587/"

# Bulk names (up to 1000 IDs)
curl -s -X POST "https://esi.evetech.net/latest/universe/names/" \
  -H "Content-Type: application/json" \
  -d '[587, 638, 11393]'
```
