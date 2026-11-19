---
name: deep-research
description: Thea research skill. The research loop behind a sourced document: split the question into sub-questions, search each one, register sources, write notes with source keys, then hand over to a writing skill. Use when the user asks for a paper, proposal, report, brief, essay or literature review, or any answer that needs several sources. For one quick fact, use research-method.
---
# Deep research

A round has about 30 steps. Spend about 12 on research and the rest on the draft. More rounds come later. The files are the memory.

## 1. Start the draft

Load the writing skill for the request and do only its step 1 (the skeleton):

- brief or one-pager: write-brief
- report or evaluation: write-report
- paper or literature review: write-research-paper
- proposal: write-research-proposal
- essay or op-ed: write-essay
- book chapter: write-book-chapter

## 2. Split the question

Write 3 sub-questions that together answer the request. Each one has its own answer.

If research/notes.md does not exist, use write_file to create it:

```markdown
# Notes
## Q1 <sub-question 1>
## Q2 <sub-question 2>
## Q3 <sub-question 3>
```

## 3. Research each sub-question

Do these steps for Q1, then Q2, then Q3:

1. web_search with one query in the words of the sub-question.
2. Pick the 2 best results: a paper, a standard, an official page or a dataset before a blog or news. For each one, call add_source with `url` (or `doi`), `title` from the result, and `relevance` 1 to 5.
3. fetch_url the best one. If it fails, fetch the second one.
4. Add 1 to 3 notes, one add_note call each. `heading` is the sub-question heading, like `Q1 <sub-question 1>`. `note` is `[S2] <one fact> (section or page)`.

A note is one fact with its key. It is not a summary of the page. Write it right after the fetch, because the page leaves your context at the end of the round.

## 4. Check the gaps

Read research/notes.md. A sub-question with no note gets one more search with other words. Then stop searching, even if some gaps stay open. Add each one with add_note under its heading: `note` is `Open: <what is missing>`.

## 5. Write the draft

Go back to the writing skill and do step 2 and the rest. Write from the notes.

## Rules

- Use only keys that add_source returned. Never invent a source or a key.
- If add_source fails, call it once more with `url` and `title`. If that fails too, take the next result. Never repeat a failed call unchanged.
- No evidence for a point: add an `Open:` note with add_note. Do not fill the gap from memory.
