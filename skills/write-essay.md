---
name: write-essay
description: Thea research skill. Drafts an argued essay of 800 to 1200 words (thesis, arguments, the strongest objection, conclusion), every fact with a source key. Use when the user asks for an essay, an op-ed, an opinion piece, an argument, a position piece or a long-form article. For neutral findings, use write-report.
---
# Write an essay

File: `research/drafts/<slug>-essay.md`. Length: the request says it; else 800 to 1200 words for a general reader.

## 1. Write the skeleton now

Use write_file with this text. Change only the title. The TODO lines become paragraphs. The essay has no headings except the title and References.

```markdown
# <Title>

TODO opening: 1 paragraph, 100 to 150 words. The question, then the thesis in 1 sentence.

TODO argument 1: 1 paragraph, 160 to 220 words. Claim first, then evidence with keys, then what it shows.

TODO argument 2: 1 paragraph, 160 to 220 words. Same shape.

TODO argument 3: 1 paragraph, 160 to 220 words. Same shape.

TODO objection: 1 or 2 paragraphs, 150 to 230 words. The strongest case against the thesis, with its key, then your answer.

TODO conclusion: 1 paragraph, 100 to 150 words. What follows if the thesis holds. No new claims.

## References
TODO references
```

## 2. Check the sources

Run list_sources. If it shows fewer than 4 sources, load deep-research and get more. Then come back to step 3.

## 3. Fill one paragraph at a time

Use edit_file. `old_text` is one whole TODO line. `new_text` is the paragraph. Do one paragraph per edit, top to bottom. Use 2 arguments if you have evidence for only 2, and delete the third TODO line.

Write only facts from research/notes.md or from pages you read with fetch_url.

After a reset: read_file the draft. Go on at the first TODO line.

## 4. Fill the references

Replace `TODO references` with one line for each key you cited: `- [S1] Authors (Year). Title. URL`. Copy the details from list_sources.

## 5. Check and report

1. Run check_citations. If it says FAIL, change each bad key to a key from list_sources, or cut the claim. Run it again.
2. Reply with the path, the thesis, and the result of check_citations.

## Rules

- A key is what add_source returned, like [S3]. Put it after the fact: `... in 2024 [S3].`
- Never write a key that list_sources does not show.
- A claim without a key is your opinion. Say so ("I think"), or cut it.
