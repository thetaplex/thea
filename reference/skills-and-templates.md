# Bundled Skills and Project Templates

## Bundled Skills

Thea has 13 built-in skills. They are always available to `load_capability`, but the Skills pane does not list them. A global skill in `~/.thea/skills.json` or a project skill in `<project>/.thea/skills.json` with the same name overrides the built-in skill.

| Skill Name | Purpose |
|---|---|
| `manage-docket` | Add and update tasks, events, decisions, and notes with the Docket tools, and export `.ics` files. |
| `draft-communication` | Draft emails, memos, invitations, and agendas in `docket/drafts/<slug>.md`. |
| `weekly-review` | Triage notes into the Docket and write a prioritized action plan in `docket/plans/<slug>.md`. |
| `deep-research` | Split a request into 3 sub-questions, search each one, keep keyed notes in `research/notes.md`, then hand over to a writing skill. |
| `book-research` | Gather author intake in `research/book/brief.md` and build a multi-session research corpus in `research/book/chapters/`. |
| `research-method` | Answer one factual question from a primary source, with source keys. |
| `source-triage` | Score search results from 1 to 5, register keepers with `add_source`, and read the best first. |
| `write-research-paper` | Draft a paper in `research/drafts/<slug>-paper.md`: abstract, background, method, findings, discussion, limitations, references. |
| `write-research-proposal` | Draft a proposal in `research/drafts/<slug>-proposal.md`: summary, problem, prior work, aims, method, timeline, risks, references. |
| `write-report` | Draft a report in `research/drafts/<slug>-report.md`: executive summary, scope, findings, analysis, recommendations, limitations, references. |
| `write-brief` | Draft a 500 to 700 word brief in `research/drafts/<slug>-brief.md`: key message, findings, recommendation, evidence, references. |
| `write-essay` | Draft a sourced essay in `research/drafts/<slug>-essay.md`: thesis, arguments, objection, conclusion, references. |
| `write-book-chapter` | Draft one book chapter in `research/drafts/NN-slug-chapter.md` from its research file, part by part. |


## Bundled Project Templates

The **Personal Assistant** and the **Research Assistant** show only **Empty Project** and **Existing Folder**. A custom persona shows all the templates.

| Template ID | Name | Files Created |
|---|---|---|
| `empty` | Empty Project | None |
| `react-vite` | React + Vite + TypeScript | `package.json`, `index.html`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`, `src/App.tsx`, `src/styles.css` |
| `python-app` | Python Application | `README.md`, `pyproject.toml`, `src/main.py`, `tests/test_main.py` |
| `node-cli` | Node.js TypeScript CLI | `package.json`, `tsconfig.json`, `src/index.ts` |
| `static-html` | Interactive HTML / Canvas | `index.html`, `style.css`, `main.js` |
