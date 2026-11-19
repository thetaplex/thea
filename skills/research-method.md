---
name: research-method
description: Thea research skill. Answers one factual question from sources: frame it, search, read a primary source, register it and answer with source keys. Use when the user asks a factual question, wants something looked up, checked or compared, or asks "what does the evidence say" about one point. For a full paper, report or proposal, use deep-research.
---
# Research method

## 1. Frame the question

Write one sentence: what you want to know. Write one more: what evidence would settle it (a number, a date, a rule, a study result).

## 2. Search

1. web_search with 1 broad query.
2. If the results show better terms (a name, a standard, a study title), web_search once more with those terms.
3. Stop after 3 searches in a row that add nothing new.

## 3. Pick and read

Prefer, in this order: the paper, the standard, the official page or documentation, the dataset. Use news or a blog only to find the primary source.

- A DOI, an arXiv id or a paper title: lookup_paper first.
- A web page or a PDF: fetch_url.

Register each source you will use with add_source: `url` (or `doi` or `arxiv_id`), `title`, and `relevance` 1 to 5 (5 = a primary source that answers the question).

## 4. Note what you learned

Right after each fetch, add 1 to 3 notes to research/notes.md, one fact per line: `- [S2] <one fact> (section or page)`.

Use add_note for each fact. `heading` is your question. `note` is `[S2] <one fact> (section or page)`. The first note makes the file and the heading.

## 5. Answer

- A factual answer needs 2 sources that agree, or 1 primary source.
- Give the answer in 1 to 5 sentences, each fact with its key, like [S2].
- If the sources disagree, give both claims with both keys.
- If you found no evidence, say so. Do not answer from memory.

## Rules

- Use only keys that add_source returned. Never invent a reference.
- If fetch_url or add_source fails, try the next result. Never repeat a failed call unchanged.
