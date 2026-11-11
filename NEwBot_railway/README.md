# LateProxyBot

A Telegram listings bot. Sellers list Discord / TikTok / Telegram items in DM, reviewers approve them, and the
bot posts approved listings to your channel, with real **custom emojis** when a Premium userbot is connected.

```
seller ──DM──▶ bot ──review──▶ approvers ──Yes──▶ Premium userbot ──posts──▶ channel
                                   │                        ▲
                                   └── No ──▶ seller told   └── bot keeps the post in sync (edit / sold / delist)
```

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in BOT_TOKEN and ADMIN_USERNAME at least
python main.py
```

Open the bot as the admin and send `/start`, so it can message you reviews. That's all you need to run it.
Everything else (channel, userbot, Discord lookup) is optional and switched on by settings; see
[docs/SETUP.md](docs/SETUP.md).

## How posts get out (it picks the best one available)

| Mode | When | Result |
|---|---|---|
| `userbot` | `CHANNEL_ID` + the userbot variables are set | A Premium account posts it: custom emojis work |
| `saved` | `CHANNEL_ID=me` + the userbot variables | The Premium account posts to its own Saved Messages (no channel needed) |
| `bot` | `CHANNEL_ID` is set, no userbot | The bot posts it: custom emojis fall back to plain ones |
| `dm` | no `CHANNEL_ID` | The finished post is DM'd to the reviewer, who posts it |

## Discord profile cards

For Discord listings the seller gives the account's **ID**. The creation date is worked out from the ID itself;
with a `DISCORD_TOKEN` the username, display name, avatar (blurred) and public badges are fetched from Discord too.
Sellers still pick Nitro / boost badges and send a private proof screenshot that only reviewers see.

## Commands

Sellers just use `/start`. Approvers also get `/pending /info /search /stats /health /marksold /removelisting
/updatebin /updateco /ban /unban` (`/help` lists them).

## Project layout

```
main.py                 entry point
lateproxy/
  config.py             settings, read from environment variables
  context.py            the service container + who is admin / approver
  app.py                builds the bot and wires everything together
  db/                   SQLite: connection + migrations, models, repositories
  listing/              what a listing is: flows (the questions), post text, summary, importer
  services/             userbot, publisher, Discord lookup, profile card, entities, backups, notifier
  ui/                   buttons, rich messages, shared screens
  handlers/             Telegram handlers: start, wizard, stock, approval, admin, importing, guard, errors
assets/                 fonts, badge images, example image, custom emoji IDs (icons.json)
scripts/                list_emojis.py · userbot_login.py · find_chat_ids.py
tests/                  pytest suite (no network needed)
docs/                   SETUP.md · ARCHITECTURE.md
data/                   the database (created at runtime, never committed)
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m pyflakes lateproxy tests main.py
```

Deploying to Railway: [docs/SETUP.md](docs/SETUP.md#railway). Before going live: [docs/RELEASE.md](docs/RELEASE.md).
