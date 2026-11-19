---
name: source-triage
description: Thea research skill. Judges search results before reading them: score each result 1 to 5, register the keepers with add_source, and read the best first. Use when a web_search returned many results, when deciding which sources to trust, read or cite, or when list_sources holds more sources than you can read.
---
# Source triage

## 1. Score each result from 1 to 5

| Score | The result is |
|---|---|
| 5 | A primary source that answers the question: the paper, the dataset, the standard, the official report. |
| 4 | A primary source on part of the question, or a review or textbook that cites primary sources. |
| 3 | Useful background from a named author or organization. |
| 2 | Off to the side, or a weak site on a relevant point. |
| 1 | Off topic, opinion, advertising, or no author. Skip it. |

Quick signs:

- Strong site: a university, a publisher, a standards body, a government, the project's own site.
- Weak site: a content farm, an unknown blog, a page that only sells something.
- Date: is it recent enough for the question? An old source is fine for history.
- Opinion never supports a factual claim.

## 2. Register the keepers

Call add_source for each result with score 2 or more. Give `url` (or `doi`, or `arxiv_id`), `title` from the search result, and `relevance` (the score). Registering is cheap. Do it before you fetch.

If add_source says the page blocks bots, call it once more with `url` and `title`. If it fails again, drop the result.

## 3. Read the best first

1. Run list_sources. It lists the highest relevance first.
2. Read 5s and 4s first, then 3s.
   - A paper, a DOI or an arXiv id: lookup_paper.
   - A web page or a PDF: fetch_url with the default length. Ask for more only if the first part is relevant.
3. Right after each read, add the facts to research/notes.md, one per line: `- [S2] <one fact> (section or page)`. Use add_note for each fact. `heading` is the question, like `Q1 ...`.

## 4. Cite from the top

When you write the draft, cite the highest scores first. Use a source with score under 3 only when it is the only support for a claim.
