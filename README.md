# EVE ESI Skill

An [OpenClaw](https://github.com/openclaw/openclaw) skill for interacting with the [EVE Online ESI API](https://developers.eveonline.com/api-explorer) (EVE Swagger Interface).

## What does it do?

- Query character info, wallet, assets, skills, clones, location, contracts, mail and more via the ESI API
- Guide for the EVE SSO OAuth2 authentication flow
- Reusable Python script for ESI queries with pagination and error handling

## Structure

```
eve-esi/
├── SKILL.md                        # Skill instructions + curl examples
├── references/
│   ├── authentication.md           # EVE SSO OAuth2 flow + scopes
│   └── endpoints.md                # All character endpoints
└── scripts/
    └── esi_query.py                # ESI query helper (Python 3.8+)
```

## Installation

Copy the `eve-esi/` folder into your OpenClaw skills directory.

## Quick Start

```bash
# Query wallet balance
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/wallet/"

# Or use the bundled script
python eve-esi/scripts/esi_query.py --token "$TOKEN" \
  --endpoint "/characters/$CHAR_ID/wallet/" --pretty
```
