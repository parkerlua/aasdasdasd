# Setup

## 1. The basics (5 minutes)

1. Create a bot with **@BotFather** (`/newbot`) and copy its token.
2. Copy `.env.example` to `.env`; set `BOT_TOKEN` and `ADMIN_USERNAME` (your Telegram username).
3. `pip install -r requirements.txt` then `python main.py`.
4. Open your bot as the admin and send `/start`. From now on approvals arrive in your DMs.

Use **Python 3.12** on the server (Railway reads `.python-version`).

## 2. A channel + a review chat (optional)

- Create the public channel, add the bot as **admin** (post / edit / delete messages), put its id in `CHANNEL_ID`.
- Create a **private** group or channel for reviews, add the bot as admin, put its id in `APPROVAL_CHAT_ID`.
  Everyone in `APPROVER_USERNAMES` / `APPROVER_IDS` (plus the admin) can then tap Yes / No there.
- Not sure of an id? Stop the bot and run `python scripts/find_chat_ids.py`, then add the bot to the chat.
- Optional private chats for `LOGS_CHAT_ID`, `ALERTS_CHAT_ID` (errors) and `BACKUP_CHAT_ID` (a daily database zip).

> **No channel? Use Saved Messages.** Set `CHANNEL_ID=me` (needs the userbot from step 3): approved listings are posted
> by the userbot to its own Saved Messages instead. Handy for testing before you make a channel.

## 3. The Premium userbot (custom emojis in the channel)

A bot can't send custom emojis into a channel (unless it owns a Fragment username), but a Premium *user* account
can. The userbot is that account; the bot still does everything else.

1. Use a **separate Telegram account** with **Premium** (not your main one).
2. At <https://my.telegram.org> -> *API development tools*, create an app and note the `api_id` and `api_hash`.
3. Run `python scripts/userbot_login.py`, enter the phone number and the login code. It prints `USERBOT_SESSION=...`.
4. Set `USERBOT_API_ID`, `USERBOT_API_HASH`, `USERBOT_SESSION` in `.env` / Railway.
5. Add the userbot account to the channel as **admin** (post + edit + delete messages). Restart the bot.
6. Send `/health`: it should show the userbot as connected, and the log says `Posting mode: userbot`.

The session string is a **login for that account**. Keep it in a variable, never in the repo.

Custom emoji IDs live in `assets/icons.json`. `python scripts/list_emojis.py <PackName>` lists a pack's IDs.

## 4. Discord lookup (optional)

Create an application at <https://discord.com/developers/applications>, add a **Bot**, copy its token into
`DISCORD_TOKEN`. The bot never joins any server; the token is only used to read public profile info by ID.
Without it, sellers are asked for the username / display name and the avatar is a grey placeholder.

## Railway

1. Deploy the repo. The `Procfile` runs `python main.py` as a **worker** (no port needed).
2. Variables: everything from `.env` that you use (at least `BOT_TOKEN`, `ADMIN_USERNAME`).
3. Add a **volume** mounted at `/data` and set `DB_PATH=/data/listings.db`. Without it the database resets on every deploy.
4. Only one copy of the bot may run per token: stop it on your PC while it runs on Railway.
5. To move your existing listings, upload `data/listings.db` into the volume once. Newer versions upgrade it automatically.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Config error: ...` | The message names the variable. Values may contain a stray newline; they are stripped automatically. |
| `Conflict: terminated by other getUpdates request` | Another copy of the bot is running (your PC, Railway, or an old terminal). |
| Reviews don't arrive | The admin must open the bot and send `/start` once (or set `ADMIN_ID`). Then `/pending` resends. |
| `Userbot ... can't see the channel` | Add the userbot account to the channel as admin and restart. |
| Posts show a plain emoji, not the custom one | Posting mode isn't `userbot` (see `/health`), or the userbot account has no Premium. |
| Buttons have no custom icon | Telegram only allows that for Premium owners / Fragment bots; the plain emoji is used. |
