# Bundled Skills and Project Templates

## Bundled Skills

Thea has 10 built-in skills. They are always available to `load_skill`, but the Skills pane does not list them. A global skill in `~/.thea/skills.json` or a project skill in `<project>/.thea/skills.json` with the same name overrides the built-in skill.

| Skill Name | Purpose |
|---|---|
| `task-checklist` | Write and update `TASK.md` in the project root so the agent loop runs until every `- [ ]` item is done. |
| `deep-research` | Run the 7-step loop for papers, proposals, essays, and reviews: decompose, breadth, depth, gap check, outline, and draft. |
| `book-research` | Gather author intake in `research/book/brief.md` and build a multi-session research corpus in `research/book/chapters/`. |
| `research-method` | Frame a question, plan in at most 5 `sequentialthinking` thoughts, prefer primary sources, and record notes in `research/notes.md`. |
| `source-triage` | Judge search results by domain, date, author, and type, score relevance from 1 to 5, and register keepers with `add_source`. |
| `write-research-paper` | Draft a paper in `research/drafts/<slug>.md` with abstract, background, method, findings, limitations, and references. |
| `write-research-proposal` | Draft a proposal in `research/drafts/<slug>-proposal.md` with problem, prior work, aims, method, timeline, risks, and references. |
| `write-essay` | Draft a sourced essay in `research/drafts/<slug>-essay.md` with thesis, argument paragraphs, objection, conclusion, and references. |
| `write-ste` | Apply `ASD-STE100` Simplified Technical English rules and fix `check_style` violations. |
| `think-in-steps` | Plan and check gaps with the `sequentialthinking` tool in thoughts under 60 words. |

## Bundled Project Templates

| Template ID | Name | Files Created |
|---|---|---|
| `empty` | Empty Project | None |
| `react-vite` | React + Vite + TypeScript | `package.json`, `index.html`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`, `src/App.tsx`, `src/styles.css` |
| `python-app` | Python Application | `README.md`, `pyproject.toml`, `src/main.py`, `tests/test_main.py` |
| `node-cli` | Node.js TypeScript CLI | `package.json`, `tsconfig.json`, `src/index.ts` |
| `static-html` | Interactive HTML / Canvas | `index.html`, `style.css`, `main.js` |
