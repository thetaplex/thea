---
name: manage-docket
description: Thea assistant skill. Records and updates tasks, events, decisions and notes on the project Docket with add_docket_item, update_docket_item and list_docket, and exports events as .ics calendar files with export_calendar. Use when the user asks to add a task, set a reminder or deadline, schedule a meeting, log a decision, mark something done, or make a calendar invite.
---
# Manage the Docket

The Docket holds every task, event, decision and note. It lives in `docket/docket.json`, and the tools keep `docket/DOCKET.md` up to date. Change it only with the tools.

## 1. Look first

Run list_docket. If an item already exists, update it. Do not add it twice.

## 2. Add each new item

Call add_docket_item once per item:

| Argument | Value |
|---|---|
| `kind` | `"task"`, `"event"`, `"decision"` or `"note"` |
| `title` | A short phrase, like "Renew the TLS certificate" |
| `priority` | A number: `3` urgent or high, `2` normal, `1` low |
| `due` | `"2026-11-24"` or `"2026-11-25T10:00"` |
| `detail` | The owner, the context, or the reason for a decision |

The tool returns the key, like `[D1]`. Note it. You need it later.

## 3. Change an item

Call update_docket_item with `key` (like `"[D1]"`) and only the fields that change: `status` (`"open"`, `"done"`, `"cancelled"`), `priority`, `due`, `title` or `detail`.

## 4. Export an event

export_calendar does not add the event to the Docket. First call add_docket_item with `kind` `"event"`. Then, for each event with a date or a time, call export_calendar:

- `title`, and `start` like `"2026-11-25T10:00"`
- `end`: for "1 hour from 10:00", give `"2026-11-25T11:00"`
- `location` and `description` if you have them

It writes a `.ics` file in `docket/calendar/` that Apple Calendar, Outlook and Google Calendar open.

## 5. Report

Reply with each key and its title, and the path of each `.ics` file.

## Rules

- Never write `docket/docket.json` or `docket/DOCKET.md` with write_file or edit_file.
- `priority` is a number, not a word.
- Name Docket items by key, like [D1], in every plan, memo and reply.
