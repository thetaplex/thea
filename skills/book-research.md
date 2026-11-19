---
name: book-research
description: Thea research skill. Researches a book over many sessions. The first session asks the author intake questions and sets up one file per chapter. Later sessions answer 2 to 4 questions for one chapter into a research corpus. Use when the user is writing a book, fiction or non-fiction, and wants research, fact-checking or background for it. To write the chapter text, use write-book-chapter.
---
# Book research

The corpus lives in `research/book/`. Breadth comes from many sessions, not from one.

## First session: intake

If `research/book/brief.md` does not exist, do not search yet. Call ask_user with these questions, reply with them in one message, then stop. Do not guess the answers or write the brief before the author answers:

1. Fiction or non-fiction? For fiction: the period, the place, and what must feel true to a reader who knows it.
2. The premise or argument in 2 sentences, and who the reader is.
3. The chapter list, or the best guess now.
4. What research exists already: files, sources to start from, people to interview.
5. Any source to avoid.

When the author answers:

1. write_file `research/book/brief.md` with the answers.
2. For each chapter, write_file `research/book/chapters/NN-slug.md` with this text:

```markdown
# NN Chapter title
## Questions
- <3 to 6 questions this chapter must answer>
## Learnings
## Still open
```

3. Ask the author to correct the questions. Stop.

## Every later session

1. Read brief.md and `research/book/open-questions.md` if it exists. Take the chapter the author names. Else take the one with the most open questions.
2. Write TASK.md with 2 to 4 of that chapter's questions.
3. For each question: web_search, add_source for the 2 best results, fetch_url the best one.
4. Right after each fetch, add each fact with add_note. `path` is the chapter file, `heading` is `Learnings`, and `note` is `[S2] <one fact> (page, section or timestamp)`.
5. Facts used by several chapters go once into `research/book/timeline.md`, `people.md`, `places.md` or `terms.md`, with add_note. `heading` is the file name without `.md`, like `Timeline`. Each note has its key.
6. Two sources disagree: add_note both claims with both keys in one note, under `Still open`. The author decides.
7. Prefer primary sources: records, letters, datasets, the original study. A secondary source gets a lower relevance.
8. Rewrite `research/book/open-questions.md`: every open question, with its chapter.
9. Reply in at most 5 lines: what the chapter has now, and what it still lacks.

## Rules

- Use only keys that add_source returned. Never invent a source.
- The ledger is shared by the whole book. A source registered for one chapter is ready for the next.
