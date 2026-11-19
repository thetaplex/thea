---
name: write-report
description: Thea research skill. Drafts a research report of 2000 to 4000 words with an executive summary, scope, findings, analysis and recommendations, every fact with a source key. Use when the user asks for a report of any length, a short or technical report, a research report, an evaluation, a review of options or a state-of-the-art summary. For 1 or 2 pages, use write-brief. For an academic paper, use write-research-paper.
---
# Write a report

File: `research/drafts/<slug>-report.md`. Length: 2000 to 4000 words.

## 1. Write the skeleton now

Use write_file with this text. Change only the title.

```markdown
# <Title>

## Executive summary
TODO summary: 150 to 250 words. The question, the main findings, the main recommendation.

## Scope
TODO scope: 150 to 250 words. What the report covers, what it leaves out, how the sources were found.

## Findings
### Finding 1
TODO Finding 1: 400 to 800 words. Each fact has a key.
### Finding 2
TODO Finding 2: 400 to 800 words. Each fact has a key.
### Finding 3
TODO Finding 3: 400 to 800 words. Each fact has a key.

## Analysis
TODO analysis: 400 to 700 words. What the findings mean together. Where the sources agree and disagree.

## Recommendations
TODO recommendations: 3 to 5 numbered items. Each item says who does what.

## Limitations
TODO limitations: 100 to 200 words. What you could not check, and what is missing.

## References
TODO references
```

## 2. Check the sources

Run list_sources. If it shows fewer than 5 sources, load deep-research and get more. Then come back to step 3.

## 3. Fill one section at a time

Use edit_file. `old_text` is one whole TODO line. `new_text` is the section text. Do one section per edit. Each finding is a section. For a fourth or fifth finding, add its heading and text in the edit of the finding before it.

Order: scope, findings, analysis, recommendations, limitations, executive summary.

Write only facts from research/notes.md or from pages you read with fetch_url.

After a reset: read_file the draft. Go on at the first TODO line.

## 4. Fill the references

Replace `TODO references` with one line for each key you cited: `- [S1] Authors (Year). Title. URL`. Copy the details from list_sources.

## 5. Check and report

1. Run check_citations. If it says FAIL, change each bad key to a key from list_sources, or cut the claim. Run it again.
2. Reply with the path, the findings in one line each, and the result of check_citations.

## Rules

- A key is what add_source returned, like [S3]. Put it after the fact: `... in 2024 [S3].`
- Never write a key that list_sources does not show.
- A fact without a key: cut it, or write it as an open question.
