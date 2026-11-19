---
name: write-research-proposal
description: Thea research skill. Drafts a research proposal of 1500 to 2500 words (problem, prior work, aims, method, timeline, risks), every fact with a source key. Use when the user asks for a research proposal, a grant proposal, a project proposal, a study plan or a thesis proposal. For finished work, use write-research-paper or write-report.
---
# Write a research proposal

File: `research/drafts/<slug>-proposal.md`. Length: 1500 to 2500 words.

## 1. Write the skeleton now

Use write_file with this text. Change only the title.

```markdown
# <Title>

## Summary
TODO summary: 3 to 5 sentences. The problem, the aims, the method.

## Problem
TODO problem: 300 to 500 words. What is unknown or broken, and why it matters. Each fact has a key.

## Prior work
TODO prior work: 400 to 600 words. What others did, with keys. The gap that is left.

## Aims
TODO aims: 2 to 4 numbered aims. One sentence each.

## Method
TODO method: 550 to 850 words. For each aim: the work, the data or tools, and how you know it worked.

## Timeline
TODO timeline: a table with the columns Phase, Months, Output.

## Risks
TODO risks: 2 to 4 bullets. What can fail, and what you will do then.

## References
TODO references
```

## 2. Check the sources

Run list_sources. If it shows fewer than 4 sources, load deep-research and get more. Then come back to step 3.

## 3. Fill one section at a time

Use edit_file. `old_text` is one whole TODO line. `new_text` is the section text. Do one section per edit, in this order: problem, prior work, aims, method, timeline, risks, summary.

Write only facts from research/notes.md or from pages you read with fetch_url. The aims, method, timeline and risks are your plan, so they need no keys.

After a reset: read_file the draft. Go on at the first TODO line.

## 4. Fill the references

Replace `TODO references` with one line for each key you cited: `- [S1] Authors (Year). Title. URL`. Copy the details from list_sources.

## 5. Check and report

1. Run check_citations. If it says FAIL, change each bad key to a key from list_sources, or cut the claim. Run it again.
2. Reply with the path, the aims, and the result of check_citations.

## Rules

- A key is what add_source returned, like [S3]. Put it after the fact: `... in 2024 [S3].`
- Never write a key that list_sources does not show.
- A fact without a key: cut it, or write it as an open question.
