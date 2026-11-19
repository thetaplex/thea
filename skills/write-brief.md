---
name: write-brief
description: Thea research skill. Drafts a brief of 500 to 700 words that gives a busy reader one key message, three findings and a recommendation, every fact with a source key. Use when the user asks for a brief, a policy brief, an executive brief or a one-pager for a decision. For any report, even a short one, use write-report.
---
# Write a brief

File: `research/drafts/<slug>-brief.md`. Length: 500 to 700 words.

## 1. Write the skeleton now

Use write_file with this text. Change only the title.

```markdown
# <Title>

## Key message
TODO key message: 1 sentence. The answer the reader needs.

## Findings
TODO findings: 3 bullets, 40 to 60 words each. Each bullet has a key.

## Recommendation
TODO recommendation: 80 to 120 words. What to do, and why.

## Evidence
TODO evidence: 280 to 380 words. The facts behind the findings.

## References
TODO references
```

## 2. Check the sources

Run list_sources. If it shows fewer than 3 sources, load deep-research and get more. Then come back to step 3.

## 3. Fill one section at a time

Use edit_file. `old_text` is one whole TODO line. `new_text` is the section text. Do one section per edit, in this order: evidence, findings, recommendation, key message.

Write only facts from research/notes.md or from pages you read with fetch_url.

After a reset: read_file the draft. Go on at the first TODO line.

## 4. Fill the references

Replace `TODO references` with one line for each key you cited: `- [S1] Authors (Year). Title. URL`. Copy the details from list_sources.

## 5. Check and report

1. Run check_citations. If it says FAIL, change each bad key to a key from list_sources, or cut the claim. Run it again.
2. Reply with the path, the key message, and the result of check_citations.

## Rules

- A key is what add_source returned, like [S3]. Put it after the fact: `... in 2024 [S3].`
- Never write a key that list_sources does not show.
- A fact without a key: cut it, or write it as an open question.
