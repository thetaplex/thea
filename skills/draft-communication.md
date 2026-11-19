---
name: draft-communication
description: Thea assistant skill. Drafts an email, memo, invitation, meeting agenda or status update as a Markdown file in docket/drafts/, with a clear subject, the purpose first, action items with owners and dates, and Docket keys. Use when the user asks to write, draft or prepare an email, memo, invite, agenda, announcement or status summary.
---
# Draft a communication

File: `docket/drafts/<slug>.md`. Use the path the user gives, if any. Length: 100 to 300 words.

## 1. Gather the facts

1. Run list_docket. Note the `[D#]` keys of the items this message is about.
2. Read the files the user names with read_file.
3. Need an outside fact (an address, opening hours, a price)? web_search, then fetch_url the official page. Use only what the page says.

## 2. Write the file

Create the file with write_file. edit_file cannot create a file. Use this shape:

```markdown
To: <people or team>
Date: <YYYY-MM-DD>
Subject: <specific subject, like "Architecture review on 2026-11-25 at 10:00">

<1 or 2 sentences: the purpose, the request or the decision.>

## Details
- <one fact per line, with its [D#] key>

## Action items
- <owner>: <what to do> by <YYYY-MM-DD> [D#]
```

For an agenda, put `## Agenda` with numbered items and times before Action items.

## 3. Check and report

1. Check that write_file returned "Wrote". If not, fix the error and call write_file again.
2. Reply with the path and the subject line.

## Rules

- This is a skill, not a tool. There is no draft_communication tool. Use write_file.
- Name every Docket item by its key, like [D1]. Use only keys that list_docket shows.
- Dates as YYYY-MM-DD. Times as HH:MM.
