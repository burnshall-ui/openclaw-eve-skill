# EVE ESI Skill for OpenClaw

> Ask your agent what New Eden is up to — wallet, skills, industry, and what
> your planets are doing while you are docked somewhere else entirely.

An [OpenClaw](https://openclaw.ai) skill for the
[EVE Online ESI API](https://developers.eveonline.com/api-explorer)
(EVE Swagger Interface). Read-only by default, no pip dependencies, tokens
stay on your machine.

## Contents

- [What it does](#what-it-does) · [Install](#install) · [Authenticate](#authenticate) · [Quick start](#quick-start)
- [Planetary Interaction](#planetary-interaction) · [Market prices](#market-prices) · [Threat assessment](#threat-assessment-and-route-planning) · [Dashboard config](#dashboard-config)
- [Security](#security) · [Reference](#reference) · [Links](#links)

---

## What it does

| | |
|---|---|
| **Authentication** | EVE SSO OAuth2 with PKCE, no client secret. Tokens auto-refresh and rotate. |
| **Multi-character** | Unlimited characters under named keys — `main`, `alt1`, whatever you call them. |
| **Planetary Interaction** | Extractor timers, storage fill, factory routing, and a parsed "needs attention" verdict per planet. |
| **Market** | Global adjusted/average prices, plus live Jita buy/sell for a single type. |
| **Threat assessment** | System scoring from ESI kills and jumps combined with zKillboard PVP data. |
| **Route planning** | Routes annotated with a per-system threat level. |
| **ESI queries** | Generic helper with pagination, rate-limit handling and error recovery. |
| **Dashboard config** | Alerts, scheduled reports and price tracking, validated against a JSON Schema. |

## Install

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/burnshall-ui/openclaw-eve-skill eve-esi
```

Python 3.8+, standard library only for everything in this repo.

## Authenticate

**Before you start**, register an application at
[developers.eveonline.com](https://developers.eveonline.com/applications):

1. Callback URL: `http://127.0.0.1:8080/callback`
2. Select your scopes — Planetary Interaction needs `esi-planets.manage_planets.v1`
3. Note the **Client ID** (with PKCE there is no client secret to keep)

Then authenticate once per character:

```bash
# On a remote server, tunnel the callback port to your browser first:
ssh -L 8080:127.0.0.1:8080 user@your-server -N

python3 scripts/auth_flow.py --client-id <YOUR_CLIENT_ID> --char-name main
# Open the printed URL and log in with your EVE account
```

Tokens land in `~/.openclaw/eve-tokens.json` (`chmod 600`) and rotate on every
use. Repeat with a different `--char-name` for each alt:

```bash
python3 scripts/auth_flow.py --client-id <CLIENT_ID> --char-name alt1
python3 scripts/get_token.py --list      # who is authenticated?
```

## Quick start

`--char <name>` resolves and refreshes the token **in-process**, so it never
touches a command line, your shell history, or a log file. Prefer it over
passing `--token`.

```bash
SKILL=~/.openclaw/workspace/skills/eve-esi
CHAR_ID=<your_character_id>

# Wallet balance
python3 $SKILL/scripts/esi_query.py --char main \
  --endpoint "/characters/$CHAR_ID/wallet/" --pretty

# Skill queue
python3 $SKILL/scripts/esi_query.py --char main \
  --endpoint "/characters/$CHAR_ID/skillqueue/" --pretty

# Every asset you own, following pagination
python3 $SKILL/scripts/esi_query.py --char main \
  --endpoint "/characters/$CHAR_ID/assets/" --pages --pretty

# Planets, and what needs attention on them
python3 $SKILL/scripts/esi_query.py --action pi_planets --char main --character-id $CHAR_ID --pretty
python3 $SKILL/scripts/esi_query.py --action pi_status  --char main --character-id $CHAR_ID --pretty

# Market — public data, no authentication needed
python3 $SKILL/scripts/esi_query.py --action jita_price --type-id 2393 --pretty
python3 $SKILL/scripts/esi_query.py --action market_price_bulk --pretty
```

## Planetary Interaction

High-level actions that turn raw ESI output into something you can act on.

```bash
# All planets for a character
python3 $SKILL/scripts/esi_query.py --action pi_planets \
  --char main --character-id $CHAR_ID --pretty

# Extractor timers, storage fill, attention flags
python3 $SKILL/scripts/esi_query.py --action pi_status \
  --char main --character-id $CHAR_ID --pretty

# One planet in detail
python3 $SKILL/scripts/esi_query.py --action pi_planet_detail \
  --char main --character-id $CHAR_ID --planet-id <PLANET_ID> --pretty
```

`pi_status` returns per planet:

| Field | Description |
|---|---|
| `planet_name` | Resolved planet name (e.g. "Ikoskio VII") |
| `extractors` | Product, expiry time, hours remaining, status |
| `storage_fill_pct` | Estimated launchpad/storage fill |
| `factories` | Input/output product routing |
| `needs_attention` | `true` when an extractor runs dry in < 6 h or storage exceeds 80 % |
| `action_required` | Plain-language description of what to do |

**A limit worth knowing up front:** ESI exposes PI as **read-only**. This skill
will tell you that an extractor expires in four hours and that your launchpad
is nearly full — it cannot restart the extractor, reroute a product, or touch
the layout. That part still happens in the client.

## Market prices

```bash
# Adjusted and average prices for every type in the game
python3 $SKILL/scripts/esi_query.py --action market_price_bulk --pretty

# Live Jita book for one type (9832 = Coolant)
python3 $SKILL/scripts/esi_query.py --action jita_price --type-id 9832 --pretty
```

`jita_price` reports lowest sell, highest buy, the spread and order counts for
The Forge.

## Threat assessment and route planning

Intended for deciding whether that low-sec PI run is worth it right now.

```bash
python3 $SKILL/scripts/esi_query.py --action system_kills --system-ids 30002537 --pretty
python3 $SKILL/scripts/esi_query.py --action system_jumps --system-ids 30002537 --pretty
python3 $SKILL/scripts/esi_query.py --action system_info  --system-id 30002537 --pretty

python3 $SKILL/scripts/esi_query.py --action route_plan \
  --origin 30000142 --destination 30002537 --route-flag secure --pretty

python3 $SKILL/scripts/esi_query.py --action character_location \
  --char main --character-id $CHAR_ID --pretty

python3 $SKILL/scripts/esi_query.py --action fw_systems --pretty
python3 $SKILL/scripts/esi_query.py --action incursions --pretty
```

**Threat levels**

| Level | Score | Read as |
|---|---|---|
| `low` | 0–15 | Normal operations |
| `medium` | 15–40 | Quick in, quick out |
| `high` | 40–80 | Scout or cloak only |
| `critical` | 80+ | Do not enter |

**Data sources** — all public, none require authentication:

| Source | Data |
|---|---|
| ESI `/universe/system_kills/` | Ship, pod and NPC kills, last hour |
| ESI `/universe/system_jumps/` | Jump traffic, last hour |
| ESI `/route/{origin}/{destination}/` | Route planning |
| ESI `/fw/systems/` | Faction Warfare contested systems |
| ESI `/incursions/` | Active NPC incursions |
| zKillboard API | PVP kills with value, last 24 h |

The scoring logic and its cache live in the agent workspace
(`~/.openclaw/workspace/scripts/`), not in this repo — see `SKILL.md`.

## Dashboard config

Automated alerts, scheduled reports and price tracking:

```bash
cp config/example-config.json ~/.openclaw/eve-dashboard-config.json
# edit it — use $ENV:VARIABLE_NAME for anything secret, never inline a token
python3 scripts/validate_config.py ~/.openclaw/eve-dashboard-config.json
```

Full schema in [config/schema.json](config/schema.json), endpoint presets in
[config/esi_endpoints.json](config/esi_endpoints.json).

| Alerts | | Reports | |
|---|---|---|---|
| `war_declared` | New war declaration | `net_worth` | ISK across wallet and assets |
| `structure_under_attack` | Structure attacked | `skill_queue` | Current training status |
| `skill_complete` | Skill finished training | `industry_jobs` | Active manufacturing and research |
| `wallet_large_deposit` | Deposit above a threshold | `market_orders` | Open buy and sell orders |
| `industry_job_complete` | Job done | `wallet_summary` | Recent transactions |
| `pi_extractor_expired` | Extraction head expired | `assets_summary` | Top asset locations by value |
| `killmail` | New killmail | | |
| `contract_expired` | Contract expired | | |

## Security

This skill holds credentials to your account. What that means concretely:

- Tokens live in `~/.openclaw/eve-tokens.json` with `chmod 600`. Refresh tokens
  rotate on every use, as EVE SSO intends.
- PKCE means there is no client secret to leak in the first place.
- **Access tokens expire in about 20 minutes. Refresh tokens do not.** Anything
  that prints a refresh token — logs, transcripts, CI output — hands over
  lasting access. `get_token.py --json` redacts it unless you explicitly pass
  `--include-refresh-token`.
- Prefer `--char`; it keeps the token out of `ps` output and shell history.
  Use `--token-stdin` when a token genuinely has to be handed over.
- `.gitignore` blocks `eve-tokens.json`, anything matching `*credentials*`, and
  the dashboard config. **Never commit real tokens.**
- Writes to your account are refused unless you pass `--allow-write`.

Access can be revoked at any time at
[EVE Third Party Applications](https://community.eveonline.com/support/third-party/).

## Reference

### Scopes requested by default

| Scope | Purpose |
|---|---|
| `esi-wallet.read_character_wallet.v1` | ISK balance, journal, transactions |
| `esi-assets.read_assets.v1` | Item inventory |
| `esi-skills.read_skills.v1` | Trained skills, SP |
| `esi-skills.read_skillqueue.v1` | Skill queue |
| `esi-clones.read_clones.v1` | Jump clones, home station |
| `esi-clones.read_implants.v1` | Active implants |
| `esi-location.read_location.v1` | Current system and station |
| `esi-location.read_ship_type.v1` | Current ship |
| `esi-location.read_online.v1` | Online status |
| `esi-planets.manage_planets.v1` | PI colonies and extractors |
| `esi-industry.read_character_jobs.v1` | Industry jobs |
| `esi-markets.read_character_orders.v1` | Market orders |
| `esi-contracts.read_character_contracts.v1` | Contracts |
| `esi-killmails.read_killmails.v1` | Killmails |
| `esi-characters.read_notifications.v1` | Notifications |
| `esi-characters.read_fatigue.v1` | Jump fatigue |
| `esi-mail.read_mail.v1` | EVE mail |

Request only what you actually need — edit `SCOPES` in `auth_flow.py`. Scopes
are granted once at login and persist until the token is revoked.

### Action parameters

- `--action` accepts `pi_planets`, `pi_planet_detail`, `pi_status`,
  `market_price_bulk`, `jita_price`, `system_kills`, `system_jumps`,
  `system_info`, `route_plan`, `character_location`, `fw_systems`, `incursions`
- `--character-id` — required for PI actions and `character_location`
- `--planet-id` — required for `pi_planet_detail`
- `--type-id` — required for `jita_price`
- `--system-id` / `--system-ids` — threat actions
- `--origin`, `--destination`, `--route-flag` — `route_plan`

### Repository layout

```
eve-esi/
├── SKILL.md                  # instructions the agent loads
├── scripts/
│   ├── auth_flow.py          # one-time EVE SSO OAuth2 PKCE login
│   ├── get_token.py          # token refresh helper
│   ├── esi_query.py          # ESI queries + high-level PI/market actions
│   ├── token_store.py        # locked read/write of the token file
│   └── validate_config.py    # dashboard config validator
├── config/
│   ├── schema.json           # JSON Schema for the dashboard config
│   ├── example-config.json   # template
│   └── esi_endpoints.json    # PI and market endpoint presets
├── references/
│   ├── authentication.md     # EVE SSO OAuth2 + PKCE in detail
│   └── endpoints.md          # endpoint index with data-sensitivity notes
└── tests/
    └── test_regressions.py
```

### Requirements

- Python 3.8+ — standard library only for core ESI queries
- OpenClaw gateway, for agent integration
- Redis and the `redis` package — **optional**, only for PI price caching

<details>
<summary>Optional: Redis price cache</summary>

Caches PI market prices with a one-hour TTL. Without it, prices are fetched
live from ESI on every request.

```bash
sudo apt install redis-server
sudo systemctl enable redis-server
pip3 install redis
redis-cli ping   # → PONG
```

The companion script `cache_market_prices.py` lives in the agent workspace, not
in this repo. It caches under the key schema `eve:market:price:{type_id}`.

</details>

## Links

- [EVE ESI API Explorer](https://developers.eveonline.com/api-explorer)
- [EVE Developer Portal](https://developers.eveonline.com/applications)
- [Revoke third-party access](https://community.eveonline.com/support/third-party/)
- [OpenClaw Docs](https://docs.openclaw.ai)

---

MIT licensed — see [LICENSE](LICENSE). Not affiliated with or endorsed by CCP hf.

Fly safe. o7
