# Run the Headless Evaluation

`promptfoo` runs the cases of a suite against a local `Ollama` model. For each case, the agent does one turn. Then it does 8 checks on the result of the turn. The research suite is in `evals/research/`. The Personal Assistant suite is in `evals/assistant/`.

Each check looks at what the user gets:

| Check | Passes when |
|---|---|
| `no_error` | The turn ends without an error. |
| `complete` | The turn has no open `TASK.md` items at the end. |
| `deliverable` | The file of the case exists, has no `TODO` line, and has a word count in the range of the case. |
| `citations` | Each key in the drafts is a registered source or a `Docket` item. |
| `sources` | The drafts cite at least `min_sources` different keys. |
| `honest_report` | The last reply names the file. If `check_citations` failed, the reply says `FAIL`. |
| `event` | The `.ics` file has the start, end, and location of the case. |


The evaluation reads the persona of each case from the database of the app, `~/.thea/thea.sqlite3` (or `$THEA_HOME/thea.sqlite3`). Thus it tests the personas that the app uses, and your own personas too. Thea writes the built-in personas to the database when it starts. After you change `default_personas()` in `src-tauri/src/db.rs`, start the app once with `just run`. The result of each case records `persona_updated_at`, the time when the persona was last written.

1. Start `Ollama` and `SearXNG`:
   ```bash
   OLLAMA_CONTEXT_LENGTH=32768 ollama serve
   just searxng
   ```
2. Run the research suite with the default model (`gemma4:e4b`):
   ```bash
   just eval
   ```
3. Run the research suite with another `Ollama` model tag:
   ```bash
   just eval qwen3:8b
   ```
4. Run the Personal Assistant suite:
   ```bash
   just eval gemma4:e4b assistant
   ```
5. Run 1 case. Give its identifier to `--filter-pattern`:
   ```bash
   just eval gemma4:e4b research --filter-pattern reflexion
   ```
6. Run all of the cases 3 times:
   ```bash
   just eval gemma4:e4b research --repeat 3
   ```
7. Open the viewer to see and compare the runs:
   ```bash
   npx promptfoo@0.125.1 view
   ```
8. Open `evals/results/promptfoo/<suite>-<model>-<date>.json` to see the full report. The folder `evals/results/promptfoo/<suite>-<model>-<date>/` has 1 transcript file and 1 first-prompt file for each case.
