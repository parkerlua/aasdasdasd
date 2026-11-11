# Before you release

Work down this list. Test on a **private test channel** first, then switch to the real one.

## 1. The userbot (custom emojis in the channel)

- [ ] A **separate** Telegram account with **Premium** (not your main account).
- [ ] `api_id` + `api_hash` from <https://my.telegram.org> -> *API development tools*, logged in as that account.
- [ ] `python scripts/userbot_login.py`: enter the phone number and the login code. Copy the `USERBOT_SESSION=...` line.
- [ ] Put `USERBOT_API_ID`, `USERBOT_API_HASH`, `USERBOT_SESSION` in `.env`.
- [ ] `python scripts/userbot_check.py`: it should print `Premium: True`, then send a test message to that account's
      Saved Messages. Open it: the stars must be **custom emojis**, not plain ⭐.

## 2. Chats

- [ ] **No channel yet?** Set `CHANNEL_ID=me`: the userbot posts approved listings to its own **Saved Messages**.
      Same custom emojis, edits and sold/delist updates, and no channel to create. Switch to a real channel later.

- [ ] A test channel. Add the **bot** and the **userbot account** as admins (post, edit and delete messages).
- [ ] `CHANNEL_ID` set to it (`python scripts/find_chat_ids.py` shows IDs; stop the bot while you run it).
- [ ] Optional private chats: `APPROVAL_CHAT_ID` (reviews), `LOGS_CHAT_ID`, `ALERTS_CHAT_ID`, `BACKUP_CHAT_ID`.
- [ ] Other approvers in `APPROVER_USERNAMES` / `APPROVER_IDS`.

## 3. Turn test mode off

- [ ] Delete `SELECTION_ONLY` and `TEST_FLOWS` from `.env` (or set `SELECTION_ONLY=0`).
- [ ] Restart. The log should say `Posting mode: userbot`, and `/health` should show the userbot connected.

## 4. One full run on the test channel

- [ ] As a seller: make a listing in every category you plan to offer.
- [ ] As an approver: tap Yes. The post must appear in the channel with the custom emojis.
- [ ] Edit the BIN from My Stock: the channel post updates. Mark it sold: it changes to the sold text. Delist another: it's removed.
- [ ] Discord listing: the profile card shows, and the proof screenshot only reaches the reviewers.

## 5. Go live

- [ ] Point `CHANNEL_ID` at the real channel (bot + userbot added as admins there).
- [ ] Railway: variables set, a **volume** mounted with `DB_PATH=/data/listings.db`, and only one copy of the bot running.
- [ ] Upload the existing `listings.db` into the volume once if you want to keep old listings.
- [ ] `.env` and the session string never go into git (`.gitignore` already excludes `.env`).
- [ ] Revoke the token of any old bot you no longer use (@BotFather -> `/revoke`).

## Good to know

- Posting from your own account is allowed, but Telegram can limit accounts that look like spam. A listings channel's
  volume is fine; don't use the userbot account for anything else.
- If the userbot ever goes down, the bot falls back to posting plain-emoji posts itself (or DMs you, with no channel set),
  so listings never get stuck.
- Keep `/health` handy: it shows the database version, the userbot, and whether each chat is reachable.
