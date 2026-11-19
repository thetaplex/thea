---
name: write-book-chapter
description: Thea research skill. Drafts one book chapter, part by part, from that chapter's research file, in the author's voice, with source keys for every fact. Use when the user asks to write, draft or continue a chapter of their book, fiction or non-fiction. To research the book first, use book-research.
---
# Write a book chapter

Input: `research/book/brief.md` and `research/book/chapters/NN-slug.md`.
File: `research/drafts/NN-slug-chapter.md`. Length: the brief says it; else 3000 to 5000 words.

## 1. Read first

1. read_file the brief. Note the reader, the voice, and fiction or non-fiction.
2. read_file the chapter file. Its `## Learnings` lines are your facts.
3. If the author gave sample text, read it and match its voice.
4. If the chapter file has fewer than 5 learnings, stop. Tell the author to run book-research on this chapter first.

## 2. Write the skeleton

Plan 4 to 8 parts. A part is one scene (fiction) or one point (non-fiction). Use write_file:

```markdown
# NN Chapter title

TODO part 1: <one line: what happens or what the reader learns>. 500 to 800 words.

TODO part 2: <one line>. 500 to 800 words.

<one TODO line per part>

## Sources
TODO sources
```

## 3. Fill one part at a time

Use edit_file. `old_text` is one whole TODO line. `new_text` is the part. One part per edit, top to bottom.

After a reset: read_file the draft. Go on at the first TODO line.

- Non-fiction: put the key after each fact, like `... in 1861 [S4].`
- Fiction: no keys in the story. Facts of the period, the place and the people must come from the learnings.
- Never add a fact that is not in the learnings. If the story needs one, write `[CHECK: <what>]` and go on.

## 4. Fill the sources

Replace `TODO sources` with one line for each key you used: `- [S1] Authors (Year). Title. URL`. Copy the details from list_sources.

## 5. Check and report

1. Run check_citations. If it says FAIL, change each bad key to a key from list_sources, or cut the claim. Run it again.
2. Add each `[CHECK: ...]` item to the chapter file with add_note: `path` is the chapter file, `heading` is `Still open`.
3. Reply with the path, the word count, and the open `[CHECK]` items.

## Rules

- The author owns the voice. Write in the voice of the brief or the sample text, not in a technical style.
- Use only keys that list_sources shows.
