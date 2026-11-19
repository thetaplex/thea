---
name: weekly-review
description: Thea assistant skill. Turns notes, inbox items and goals into Docket items and a written daily or weekly action plan in docket/plans/, ordered by priority, with dates and .ics invites. Use when the user asks to triage notes or an inbox, plan the week or the day, review open tasks, or build an action plan or to-do list.
---
# Weekly review and action plan

File: `docket/plans/<slug>.md`. Use the path the user gives, if any.

## 1. Collect

1. read_file each notes or inbox file the user names. If they name none, list_directory and read the notes files.
2. Run list_docket to see what is already there.

## 2. Triage each line into the Docket

Go through the notes one line at a time. Skip a line that list_docket already has.

| The line is | Call |
|---|---|
| Something to do | add_docket_item, `kind` `"task"`. `priority` 3 if urgent, else 2. `due` if it has a date. |
| A meeting or a deadline with a date | add_docket_item, `kind` `"event"`, then export_calendar with `title`, `start` and `end`. |
| A choice already made | add_docket_item, `kind` `"decision"`. |
| Done already | update_docket_item, `status` `"done"`. |

Note each key the tools return, like [D3].

## 3. Write the plan

Create the file with write_file. edit_file cannot create a file, and run_command must not write files. Use this shape:

```markdown
# Action plan, week of <YYYY-MM-DD>

## Top priorities
- [D#] <title>, due <YYYY-MM-DD>

## Schedule
- <YYYY-MM-DD HH:MM> [D#] <title>. Invite: docket/calendar/<file>.ics

## Open tasks
- [D#] <title>, due <YYYY-MM-DD>

## Decisions and notes
- [D#] <decision or note>
```

Top priorities holds the priority 3 items. Order each section by date, soonest first.

## 4. Check and report

1. Check that write_file returned "Wrote".
2. Reply with the path and the top priorities.

## Rules

- Use only keys that the Docket tools returned.
- Dates as YYYY-MM-DD.
