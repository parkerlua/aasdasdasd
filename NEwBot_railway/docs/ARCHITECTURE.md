# Architecture

## Layers (dependencies point down)

```
handlers/     Telegram updates in, screens out. Thin: they call services and repositories.
   │
services/     work with the outside world: userbot, publisher, discord, profile card, entities, backup, notifier
   │
listing/      pure logic: flows (the questions), post text, summary, importer. No Telegram, no database.
   │
db/           sqlite: Database (+ migrations), models, repositories. The only place with SQL.
config.py     Settings, from environment variables.
```

`context.py` holds the `Services` container built in `app.py` and handed to every handler through
`svc(context)`. Nothing is a global, which is what makes the tests possible: they build a `Services` out of fakes.

## A listing's life

1. **Wizard** (`handlers/wizard.py`): walks `listing/flows.py` step by step. State lives in `context.user_data["flow"]`.
   A step with a `hook` runs an action after it's answered: the Discord ID step looks the account up and skips
   the questions it already answered.
2. **Submit**: the listing is saved as `pending` and `approval.notify_approvers` sends it to the approval chat
   (or the admin's DM) with Yes / No.
3. **Approve** (`handlers/approval.py`): `ListingRepo.transition("pending" -> "active")` is atomic, so two approvers
   can't both publish. Then `Publisher.publish` posts it. If posting fails the listing goes back to `pending`.
4. **Publisher** (`services/publisher.py`) chooses `userbot` > `bot` > `dm`. The post is Telegram HTML built by
   `listing/post.py`; for the userbot `services/entities.py` converts it into raw entities (custom emojis included).
5. **Stock** (`handlers/stock.py`): edits re-render and edit the channel post; "sold" replaces it with `SOLD_TEXT`;
   "delist" deletes it.

## Why a userbot and a bot

- Custom emojis in channel posts need a Premium *user* account (or a Fragment-username bot).
- Inline buttons are bot-only, even on a userbot's post. `Publisher._attach_button` therefore uses the bot, and
  re-attaches after every userbot edit (Telethon edits clear the keyboard).

## Database

`db/database.py` runs ordered migrations tracked with `PRAGMA user_version`. Each migration checks what exists
first, so a database from the very first version of the bot (no version at all) upgrades in place.
To change the schema: add a function to `MIGRATIONS`. Never edit an old one.

## Tests

`pytest` needs no network. `tests/fakes.py` has a `FakeBot` (records calls) and `FakeUserbot`; `make_services()`
builds a full `Services` on an in-memory database. Discord is tested with `httpx.MockTransport`.
