---
name: write-research-paper
description: Thea research skill. Drafts a research paper of 3000 to 5000 words (abstract, background, method, findings, discussion, limitations), every fact with a source key. Use when the user asks for a research paper, an academic paper, a literature review, a survey or a short paper. For a plan of future work, use write-research-proposal. For a report to a decision maker, use write-report.
---
# Write a research paper

File: `research/drafts/<slug>-paper.md`. Length: 3000 to 5000 words. A "short paper" is 1500 to 2500.

## 1. Write the skeleton now

Use write_file with this text. Change only the title.

```markdown
# <Title>

## Abstract
TODO abstract: 4 to 6 sentences. The question, the method, the findings.

## Background
TODO background: 450 to 750 words. What is known. Each fact has a key.

## Method
TODO method: 250 to 350 words. How you searched, what you kept and why.

## Findings
### Finding 1
TODO Finding 1: 500 to 800 words. Each fact has a key.
### Finding 2
TODO Finding 2: 500 to 800 words. Each fact has a key.
### Finding 3
TODO Finding 3: 500 to 800 words. Each fact has a key.

## Discussion
TODO discussion: 500 to 900 words. What the findings mean. Where sources disagree.

## Limitations
TODO limitations: 200 to 300 words. What you could not check, and what is missing.

## References
TODO references
```

## 2. Check the sources

Run list_sources. If it shows fewer than 5 sources, load deep-research and get more. Then come back to step 3.

## 3. Fill one section at a time

Use edit_file. `old_text` is one whole TODO line. `new_text` is the section text. Do one section per edit. Each finding is a section. For a fourth or fifth finding, add its heading and text in the edit of the finding before it.

Order: background, method, findings, discussion, limitations, abstract.

Write only facts from research/notes.md or from pages you read with fetch_url.

After a reset: read_file the draft. Go on at the first TODO line.

## 4. Fill the references

Replace `TODO references` with one line for each key you cited: `- [S1] Authors (Year). Title. URL`. Copy the details from list_sources.

## 5. Check and report

1. Run check_citations. If it says FAIL, change each bad key to a key from list_sources, or cut the claim. Run it again.
2. Reply with the path, the findings in one line each, and the result of check_citations.

## Rules

- A key is what add_source returned, like [S3]. Put it after the fact: `... in 2024 [S3].` Two keys: `[S1][S4]`.
- Never write a key that list_sources does not show.
- A fact without a key: cut it, or write it as an open question.
