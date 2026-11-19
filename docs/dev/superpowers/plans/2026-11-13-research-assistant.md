# Research Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Research Assistant persona produce research papers and proposals on `gemma4:e4b` where every citation resolves to a fetched or looked-up source, with ASD-STE100 style checking, tool-based thinking, and Reflexion-style lessons from real signals.

**Architecture:** New Rust tools (`web_search`, `fetch_url`, `lookup_paper`, `add_source`, `list_sources`, `check_style`, `check_citations`) plug into the existing `execute_single_tool` dispatch and approval gate. A per-project `research/sources.json` ledger is the only route into a bibliography. Personas gain `tool_ids`, `native_thinking` and `max_steps`; Ollama requests gain `num_ctx` and `think`, and tool support comes from `/api/show` capabilities. Bundled skills compile in with `include_dir!`. An event-sink seam replaces the direct `AppHandle` dependency so a headless `eval` binary can run the same agent loop.

**Tech Stack:** Rust (Tauri 2, tokio, reqwest, regex, serde, rusqlite, include_dir, which), new crate `pdf-extract`; React 19 + TypeScript + Zustand; pnpm, Biome, Vitest, clippy.

**Spec:** `docs/superpowers/specs/2026-11-13-research-assistant-design.md`

## Global Constraints

- Rust toolchain: `export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"` before any cargo command on this machine.
- `just check` (biome, tsc, clippy `-D warnings`, vitest, cargo test) must be green at every commit. `cargo fmt` and `pnpm fmt` before committing.
- Conventional Commits. Work on branch `feat/research-assistant`.
- No API keys on the default path. No new secrets. `.env*` stays unreadable by tools.
- `research/sources.json` is written only by `add_source`. `write_file` and `edit_file` refuse it.
- Read-only tools are auto-approved. `add_source` uses the `write` approval category. Shell stays approval-gated with no Always Allow.
- External HTTP timeouts: 15 s for `web_search`, `fetch_url`, `lookup_paper`. `fetch_url` rejects non-http(s), loopback, private, link-local and `localhost` targets, on every redirect hop.
- Tool result caps: `fetch_url` default 6000 chars, cap 20000. `web_search` default 5 results, cap 10. Skill bodies under 400 words. Persona prompt under 200 words.
- Settings defaults: `context_tokens` 32768 (clamped to the model's reported `context_length`), `max_agent_steps` 15 globally, 30 for the Research Assistant.
- Lessons: `~/.thea/lessons/<persona-id>.md`, cap 20, FIFO, never written without a signal, never shared across personas.
- Frontend copy and Markdown the agent writes follow ASD-STE100 where practical: short sentences, active voice, no contractions.

## Review Focus

Inputs the spec implies but no feature test would exercise, each pinned to a test in the owning task:

1. `fetch_url` given a public URL that redirects to `http://169.254.169.254/` or `http://localhost:11434/`: the redirect must be refused, not followed. Task 4, test `rejects_private_and_loopback_targets` covers the predicate used on every hop.
2. A draft whose code block contains `[S9]` and whose prose cites `[S10]`: the code block key is ignored, `S10` is parsed as 10 not 1. Task 3, tests `ignores_keys_inside_code_fences` and `parses_multi_digit_keys`.
3. The model sends `{"thoughtNumber": "1", "nextThoughtNeeded": "false"}` to the sequential-thinking server: arguments are coerced to integer and boolean before dispatch. Task 11, test `coerces_string_numbers_and_bools`.
4. `research/sources.json` hand-edited into invalid JSON: `add_source` and `check_citations` return an error naming the file, no panic, no overwrite. Task 3, test `corrupt_ledger_is_an_error_not_a_reset`.
5. Ollama older than the `capabilities` field, or a model not pulled: `show_model` returns a capabilities struct with `supports_tools` from the heuristic and `context_length: None`, so `num_ctx` is sent unclamped and the run proceeds. Task 1, test `show_response_without_capabilities_falls_back`.

---

## File structure

Create:
- `src-tauri/src/tools/research.rs`: `web_search`, `fetch_url`, `lookup_paper` (network, parsers as pure fns)
- `src-tauri/src/tools/ledger.rs`: `Source`, ledger read/write, `add_source`, `list_sources`, `check_citations`
- `src-tauri/src/tools/ste.rs`: `check_style` and the unapproved-word table
- `src-tauri/src/lessons.rs`: lesson storage and prompt formatting
- `src-tauri/src/agent/reflection.rs`: signals, trajectory summary, the reflection call
- `src-tauri/src/agent/sink.rs`: `EventSink` trait, `AppHandle` impl, `NullSink`
- `src-tauri/src/bin/eval.rs`: headless eval
- `skills/*.md`: six bundled skills
- `evals/research/*.json`: five cases
- `docs/superpowers/plans/2026-11-13-research-assistant.md` (this file)

Modify:
- `src-tauri/src/providers/mod.rs` (`ChatOptions`), `providers/ollama.rs` (`show_model`, options)
- `src-tauri/src/db.rs` (settings fields, persona fields and columns, reseed, MCP presets, `THEA_HOME`)
- `src-tauri/src/agent/mod.rs` (tool filtering, options, budget, sink, reflection hook)
- `src-tauri/src/tools/mod.rs` (definitions), `tools/fs.rs` (ledger guard, read range)
- `src-tauri/src/mcp.rs` (`coerce_arguments`), `src-tauri/src/skills.rs` (builtins)
- `src-tauri/src/lib.rs` (commands), `src-tauri/Cargo.toml`, `justfile`
- `src/lib/ipc.ts`, `src/components/SettingsModal.tsx`, `src/components/ChatView.tsx`, `src/components/SkillsPane.tsx`

---

### Task 0: Branch and commit the design

**Files:**
- Commit: `docs/superpowers/specs/2026-11-13-research-assistant-design.md`, `docs/superpowers/plans/2026-11-13-research-assistant.md`

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feat/research-assistant
```

- [ ] **Step 2: Commit the docs**

```bash
git add docs/superpowers
git commit -m "docs: research assistant design and plan"
```

---

### Task 1: Ollama capabilities, `num_ctx`, `think`, and `THEA_HOME`

**Files:**
- Modify: `src-tauri/src/providers/mod.rs`
- Modify: `src-tauri/src/providers/ollama.rs`
- Modify: `src-tauri/src/providers/openai_compat.rs` (signature only)
- Modify: `src-tauri/src/db.rs:119` (`thea_home_dir`), `AppSettings` and its `Default`
- Modify: `src-tauri/src/agent/mod.rs` (call sites)
- Modify: `src-tauri/src/lib.rs` (new command `get_model_capabilities`)
- Modify: `src/lib/ipc.ts`, `src/components/SettingsModal.tsx`

**Interfaces:**
- Produces in `providers/mod.rs`:
  ```rust
  #[derive(Debug, Clone, Default, Serialize, Deserialize)]
  pub struct ChatOptions { pub num_ctx: Option<u64>, pub think: Option<bool> }
  #[derive(Debug, Clone, Serialize, Deserialize)]
  pub struct ModelCapabilities { pub supports_tools: bool, pub supports_thinking: bool, pub context_length: Option<u64>, pub parameter_size: Option<String> }
  impl ModelCapabilities { pub fn is_small(&self) -> bool } // parameter_size parses to < 8.0 B; None => false
  ```
- Produces in `providers/ollama.rs`:
  ```rust
  pub fn parse_show_response(model: &str, body: &serde_json::Value) -> ModelCapabilities
  pub async fn show_model(base_url: &str, model: &str) -> ModelCapabilities // cached per (base_url, model) in a static Mutex<HashMap>; on HTTP error returns parse_show_response(model, &json!({}))
  pub async fn stream_chat(base_url, model, messages, tools, use_native_tools, options: &ChatOptions, cancel, on_delta) -> Result<AssistantTurn>
  ```
  Body: `"options": {"num_ctx": n}` when `num_ctx` is Some; `"think": b` when `think` is Some.
- Produces in `db.rs`: `AppSettings.context_tokens: u64` (serde default 32768), `AppSettings.small_model: Option<bool>` (serde default None). `thea_home_dir()` returns `$THEA_HOME` when that env var is set and non-empty.
- Produces in `lib.rs`: `#[tauri::command] async fn get_model_capabilities(state, model: String) -> CmdResult<ModelCapabilities>` using the active Ollama base URL.
- `openai_compat::stream_chat` gains the same `options: &ChatOptions` parameter and ignores it.

- [ ] **Step 1: Write failing tests in `providers/ollama.rs`**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_capabilities_and_context_length() {
        let body = json!({
            "capabilities": ["completion", "tools", "thinking"],
            "details": {"parameter_size": "7.5B"},
            "model_info": {"gemma4.context_length": 131072}
        });
        let c = parse_show_response("gemma4:e4b", &body);
        assert!(c.supports_tools && c.supports_thinking);
        assert_eq!(c.context_length, Some(131072));
        assert!(c.is_small());
    }

    #[test]
    fn show_response_without_capabilities_falls_back() {
        let c = parse_show_response("qwen3:8b", &json!({}));
        assert!(c.supports_tools); // heuristic
        assert_eq!(c.context_length, None);
        assert!(!c.is_small());
    }

    #[test]
    fn parameter_size_over_8b_is_not_small() {
        let c = parse_show_response("x", &json!({"details": {"parameter_size": "14B"}}));
        assert!(!c.is_small());
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --manifest-path src-tauri/Cargo.toml parses_capabilities`
Expected: compile error, `parse_show_response` not found.

- [ ] **Step 3: Implement `ChatOptions`, `ModelCapabilities`, `parse_show_response`, `show_model`, and the `options` parameter**

`parse_show_response`: `supports_tools` = capabilities contains `"tools"`, else `guess_supports_tools(model)`. `context_length` = first `model_info` key ending in `.context_length`. `is_small`: strip trailing `B`/`b`, parse f64, `< 8.0`.

- [ ] **Step 4: Add settings fields, `THEA_HOME`, and thread `ChatOptions` through `agent/mod.rs`**

In the step loop, for protocol `ollama`: `let caps = ollama::show_model(&base_url, &active_model).await; let native_tools = caps.supports_tools; let num_ctx = caps.context_length.map_or(settings.context_tokens, |m| settings.context_tokens.min(m));` and pass `ChatOptions { num_ctx: Some(num_ctx), think: None }`. For other protocols keep `guess_supports_tools`. (`think` is set per persona in Task 2.)

- [ ] **Step 5: Frontend: `context_tokens` field in Settings**

In `src/lib/ipc.ts` add `context_tokens: number; small_model?: boolean | null;` to `AppSettings`, and `getModelCapabilities: (model: string) => invoke<ModelCapabilities>("get_model_capabilities", { model })` with a matching `ModelCapabilities` interface. In `SettingsModal.tsx` providers tab, under the model picker, add a number input bound to `form.context_tokens` (min 2048, step 1024) with helper text: "Context window in tokens. Larger values use more RAM and make each step slower." When a model is selected and capabilities load, append "This model supports up to N." using `context_length`.

- [ ] **Step 6: Run checks**

Run: `just check`
Expected: all green, including the three new tests.

- [ ] **Step 7: Commit**

```bash
git add -A src-tauri/src src/lib/ipc.ts src/components/SettingsModal.tsx
git commit -m "feat(ollama): model capabilities, num_ctx and think options, context_tokens setting"
```

---

### Task 2: Persona fields, migration, re-seed, and the new prompt

**Files:**
- Modify: `src-tauri/src/db.rs` (`Persona`, schema, migrations near line 624, `query_personas_rows`, `list_personas`, `save_custom_persona`, `default_personas`)
- Modify: `src-tauri/src/lib.rs` (setup calls `db.reseed_builtin_personas()`)
- Modify: `src-tauri/src/agent/mod.rs` (tool filtering, `think`, per-persona steps)
- Modify: `src/lib/ipc.ts` (`Persona` fields)

**Interfaces:**
- Produces on `Persona`:
  ```rust
  #[serde(default)] pub tool_ids: Vec<String>,          // empty = all built-in tools
  #[serde(default = "default_true")] pub native_thinking: bool,
  #[serde(default)] pub max_steps: usize,               // 0 = use settings.max_agent_steps
  ```
  Columns: `tool_ids_json TEXT NOT NULL DEFAULT '[]'`, `native_thinking INTEGER NOT NULL DEFAULT 1`, `max_steps INTEGER NOT NULL DEFAULT 0`, added with `ALTER TABLE ... ADD COLUMN` guarded like the existing `persona_id` migrations.
- Produces: `pub fn builtin_persona_ids() -> Vec<String>` (ids of `default_personas()`), `impl Database { pub fn reseed_builtin_personas(&self) -> Result<()> }` which upserts every `default_personas()` row (all columns), and `pub fn is_builtin_persona(id: &str) -> bool`.
- `save_custom_persona` and `delete_custom_persona` bail with `"Built-in personas cannot be modified"` for builtin ids.
- Research Assistant seed: `id: "research-assistant"`, `tool_ids: ["list_dir","read_file","write_file","edit_file","search","load_skill","web_search","fetch_url","lookup_paper","add_source","list_sources","check_style","check_citations"]`, `mcp_server_ids: ["sequential-thinking"]`, `skill_ids: []`, `native_thinking: false`, `max_steps: 30`. Other two personas: `tool_ids: ["list_dir","read_file","write_file","edit_file","search","run_command","load_skill"]`, `native_thinking: true`, `max_steps: 0`.
- Research Assistant `system_prompt` (exact copy):

```
You are Thea in Research Assistant mode. You work like a careful researcher.

Method:
1. Load the research-method skill. Plan with the sequentialthinking tool. Then start.
2. Search with web_search. Judge each result before you read it (source-triage skill).
3. Read with fetch_url or lookup_paper. Register every source you will use with add_source. Write what you learned to research/notes.md, tagged with the source key.
4. Write drafts in research/drafts/ from your notes only. Follow the write-research-paper or write-research-proposal skill and the write-ste style.
5. Before you finish, run check_style, then check_citations. Fix every failure. Report the result.

Rules:
- Cite only keys that add_source returned, in the form [S1]. Never invent a reference.
- If you cannot find a source for a claim, say so. Remove the claim or mark it as an open question.
- Give tool arguments in the exact type the schema asks for. Use integers where it asks for integers.
- Write short, plain sentences in the active voice.
```

- [ ] **Step 1: Write failing tests in `db.rs`**

```rust
#[cfg(test)]
mod persona_tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn reseed_overwrites_builtin_prompt_and_keeps_custom() {
        let dir = tempdir().unwrap();
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        db.list_personas().unwrap();
        db.save_custom_persona(Some("mine"), "Mine", "t", "p", &[], &[], &[]).unwrap();
        {
            let conn = db.conn.lock().unwrap();
            conn.execute("UPDATE personas SET system_prompt='old' WHERE id='research-assistant'", []).unwrap();
        }
        db.reseed_builtin_personas().unwrap();
        let ra = db.get_persona("research-assistant").unwrap();
        assert!(ra.system_prompt.starts_with("You are Thea in Research Assistant mode."));
        assert!(!ra.native_thinking);
        assert_eq!(ra.max_steps, 30);
        assert!(ra.tool_ids.contains(&"add_source".to_string()));
        assert!(db.get_persona("mine").unwrap().id == "mine");
    }

    #[test]
    fn builtin_personas_reject_edit_and_delete() {
        let dir = tempdir().unwrap();
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        assert!(db.save_custom_persona(Some("research-assistant"), "x", "x", "x", &[], &[], &[]).is_err());
        assert!(db.delete_custom_persona("research-assistant").is_err());
    }

    #[test]
    fn prompt_is_under_200_words() {
        let ra = default_personas().into_iter().find(|p| p.id == "research-assistant").unwrap();
        assert!(ra.system_prompt.split_whitespace().count() < 200);
    }
}
```

Note: `Database::open` must not touch `~/.thea` in tests. Set `THEA_HOME` to the tempdir at the top of each test (`std::env::set_var("THEA_HOME", dir.path())`) so settings and personas files land there.

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --manifest-path src-tauri/Cargo.toml persona_tests`
Expected: FAIL, `reseed_builtin_personas` not found.

- [ ] **Step 3: Implement fields, migration, reseed, builtin guards, and seed data**

`reseed_builtin_personas` reuses the `INSERT ... ON CONFLICT(id) DO UPDATE` statement from `save_custom_persona`, extended with the three new columns. Call it from `lib.rs` setup right after `db.list_personas()`.

- [ ] **Step 4: Apply `tool_ids`, `native_thinking`, `max_steps` in `agent/mod.rs`**

After building `tool_defs` from `builtin_tool_definitions()`: `if !persona.tool_ids.is_empty() { tool_defs.retain(|t| persona.tool_ids.contains(&t.name)); }` (before MCP tools are appended). `max_steps = if persona.max_steps > 0 { persona.max_steps } else { settings.max_agent_steps }.max(1)`. `ChatOptions.think = if caps.supports_thinking { Some(persona.native_thinking) } else { None }`.

- [ ] **Step 5: Frontend types**

Add `tool_ids: string[]; native_thinking: boolean; max_steps: number;` to `Persona` in `src/lib/ipc.ts`. No editor UI.

- [ ] **Step 6: Run checks and commit**

Run: `just check` → green.

```bash
git add -A src-tauri/src src/lib/ipc.ts
git commit -m "feat(personas): tool_ids, native_thinking, max_steps; reseed builtins; new research prompt"
```

---

### Task 3: Source ledger and `check_citations`

**Files:**
- Create: `src-tauri/src/tools/ledger.rs`
- Modify: `src-tauri/src/tools/mod.rs` (`pub mod ledger;`)
- Modify: `src-tauri/src/tools/fs.rs` (`write_workspace_file` refuses the ledger path)

**Interfaces:**
```rust
pub const LEDGER_PATH: &str = "research/sources.json";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Source {
    pub key: String,                 // "S1"
    pub kind: String,                // "paper" | "web"
    pub title: String,
    #[serde(default)] pub authors: Vec<String>,
    pub year: Option<i32>,
    pub venue: Option<String>,
    pub doi: Option<String>,
    pub url: String,
    #[serde(rename = "abstract")] pub summary: Option<String>,
    pub note: Option<String>,
    pub added_at: String,            // RFC 3339
}

pub fn load_ledger(project_root: &Path) -> Result<Vec<Source>>   // missing file => Ok(vec![]); invalid JSON => Err("research/sources.json is not valid JSON: ...")
pub fn save_ledger(project_root: &Path, sources: &[Source]) -> Result<()>  // creates research/, pretty JSON
pub fn next_key(sources: &[Source]) -> String                    // "S{max+1}"
pub fn find_duplicate<'a>(sources: &'a [Source], doi: Option<&str>, url: &str) -> Option<&'a Source>  // doi match (case-insensitive) or exact url
pub fn format_ledger(sources: &[Source]) -> String               // one line per source: "[S1] Title (Authors, Year) url"
pub fn is_ledger_path(user_path: &str) -> bool                   // normalizes "./", "\\" and leading "/"

#[derive(Debug, Serialize)]
pub struct CitationReport { pub cited: Vec<String>, pub missing: Vec<String>, pub orphans: Vec<String>, pub bad_references: Vec<String>, pub pass: bool }
pub fn check_citations(draft: &str, ledger: &[Source]) -> CitationReport
pub fn format_citation_report(r: &CitationReport) -> String       // "PASS" or "FAIL" first line, then sections
```
`check_citations`: cited keys are every `[S<digits>]` outside fenced code blocks (``` ... ```) and inline code. `missing` = cited not in ledger. `bad_references` = lines under a `## References` heading of the form `- [Sn] ...` whose key is not in the ledger. `orphans` = ledger keys never cited (reported, not a failure). `pass = missing.is_empty() && bad_references.is_empty()`.

- [ ] **Step 1: Write failing tests in `ledger.rs`**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    fn src(key: &str) -> Source { Source { key: key.into(), kind: "web".into(), title: "T".into(), authors: vec![], year: None, venue: None, doi: None, url: format!("https://x/{key}"), summary: None, note: None, added_at: String::new() } }

    #[test]
    fn passes_when_every_citation_is_in_ledger() {
        let r = check_citations("Claim [S1]. Other [S2].\n\n## References\n- [S1] a\n- [S2] b\n", &[src("S1"), src("S2")]);
        assert!(r.pass); assert!(r.missing.is_empty());
    }
    #[test]
    fn fails_on_unknown_key_and_bad_reference() {
        let r = check_citations("Claim [S3].\n\n## References\n- [S4] ghost\n", &[src("S1")]);
        assert!(!r.pass); assert_eq!(r.missing, vec!["S3"]); assert_eq!(r.bad_references, vec!["S4"]); assert_eq!(r.orphans, vec!["S1"]);
    }
    #[test]
    fn ignores_keys_inside_code_fences() {
        let r = check_citations("```\n[S9]\n```\nText `[S8]` here [S1].", &[src("S1")]);
        assert_eq!(r.cited, vec!["S1"]); assert!(r.pass);
    }
    #[test]
    fn parses_multi_digit_keys() {
        let r = check_citations("See [S10].", &[src("S1")]);
        assert_eq!(r.missing, vec!["S10"]);
    }
    #[test]
    fn next_key_increments_max() {
        assert_eq!(next_key(&[]), "S1");
        assert_eq!(next_key(&[src("S2"), src("S7")]), "S8");
    }
    #[test]
    fn corrupt_ledger_is_an_error_not_a_reset() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("research")).unwrap();
        std::fs::write(dir.path().join(LEDGER_PATH), "{not json").unwrap();
        let err = load_ledger(dir.path()).unwrap_err().to_string();
        assert!(err.contains("sources.json"));
        assert_eq!(std::fs::read_to_string(dir.path().join(LEDGER_PATH)).unwrap(), "{not json");
    }
    #[test]
    fn ledger_path_variants_are_detected() {
        for p in ["research/sources.json", "./research/sources.json", "research\\sources.json", "/research/sources.json"] { assert!(is_ledger_path(p), "{p}"); }
        assert!(!is_ledger_path("research/notes.md"));
    }
}
```

Add to `fs.rs` tests:
```rust
#[test]
fn write_file_refuses_the_ledger() {
    let dir = tempdir().unwrap();
    let err = write_workspace_file(dir.path(), "research/sources.json", "[]").unwrap_err().to_string();
    assert!(err.contains("add_source"));
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --manifest-path src-tauri/Cargo.toml ledger`
Expected: compile error, module missing.

- [ ] **Step 3: Implement `ledger.rs` and the guard**

In `write_workspace_file`, before resolving: `if ledger::is_ledger_path(user_path) { bail!("'{}' is managed by the add_source tool and cannot be written directly", user_path); }`. `preview_edit_workspace_file` calls through `read_workspace_file` then the write arm calls `write_workspace_file`, so the single guard covers both tools.

- [ ] **Step 4: Run tests, then commit**

Run: `cargo test --manifest-path src-tauri/Cargo.toml` → all pass.

```bash
git add src-tauri/src/tools
git commit -m "feat(research): source ledger and check_citations"
```

---

### Task 4: `fetch_url` with SSRF guard, HTML to text, PDF to text

**Files:**
- Create: `src-tauri/src/tools/research.rs`
- Modify: `src-tauri/src/tools/mod.rs` (`pub mod research;`)
- Modify: `src-tauri/Cargo.toml` (add `pdf-extract = "0.7"`)

**Interfaces:**
```rust
pub const FETCH_DEFAULT_CHARS: usize = 6000;
pub const FETCH_MAX_CHARS: usize = 20000;
pub const HTTP_TIMEOUT: Duration = Duration::from_secs(15);
pub const USER_AGENT: &str = "Thea/0.1 (+https://github.com/thetaplex/thea)";

pub fn is_public_http_url(url: &reqwest::Url) -> bool
// scheme http/https; host present; host not "localhost", not ending ".local" or ".internal"; if host is an IP literal: not loopback, private, link-local, unspecified, multicast, or IPv6 unique-local (fc00::/7)
pub async fn resolves_public(url: &reqwest::Url) -> bool // is_public_http_url && every address from tokio::net::lookup_host(host:port) passes the same IP checks
pub fn html_to_text(html: &str) -> (Option<String>, String) // (title, text): drop <script> <style> <nav> <header> <footer> <aside> <noscript> blocks; <br> <p> <div> <li> <h1-6> <tr> become newlines; strip remaining tags; decode &amp; &lt; &gt; &quot; &#39; &nbsp; and numeric entities; collapse runs of blank lines to one
pub fn truncate_marked(text: &str, max_chars: usize) -> String // appends "\n[truncated at N chars; ask with a larger max_chars or a narrower question]" when cut

#[derive(Debug, Serialize)]
pub struct Fetched { pub title: Option<String>, pub url: String, pub fetched_at: String, pub text: String, pub content_type: String }
pub async fn fetch_url(url: &str, max_chars: usize) -> Result<Fetched>
pub fn format_fetched(f: &Fetched) -> String // "Title: ...\nURL: ...\nFetched: ...\n\n<text>"
```
`fetch_url`: parse URL, `resolves_public` or bail `"fetch_url refuses non-public or non-http(s) URLs"`. Client: `redirect(Policy::custom(|a| if a.previous().len() > 5 { a.error("too many redirects") } else if is_public_http_url(a.url()) { a.follow() } else { a.error("redirect to a non-public address refused") }))`, timeout, user agent. Read at most 5 MB. If `Content-Type` contains `pdf` (or body starts with `%PDF`): `pdf_extract::extract_text_from_mem`. Else `html_to_text`. Then `truncate_marked(text, max_chars.clamp(500, FETCH_MAX_CHARS))`.

- [ ] **Step 1: Write failing tests**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_private_and_loopback_targets() {
        for u in ["http://127.0.0.1:11434/", "http://localhost/x", "http://169.254.169.254/latest", "http://10.0.0.5/", "http://192.168.1.1/", "http://[::1]/", "http://[fd00::1]/", "ftp://example.com/", "file:///etc/passwd", "http://host.internal/"] {
            assert!(!is_public_http_url(&reqwest::Url::parse(u).unwrap()), "{u}");
        }
        assert!(is_public_http_url(&reqwest::Url::parse("https://arxiv.org/abs/2303.11366").unwrap()));
    }
    #[test]
    fn html_to_text_strips_boilerplate_and_keeps_title() {
        let (title, text) = html_to_text("<html><head><title>Hi &amp; bye</title><script>x()</script></head><body><nav>menu</nav><p>One</p><p>Two &lt;3</p></body></html>");
        assert_eq!(title.as_deref(), Some("Hi & bye"));
        assert!(!text.contains("menu") && !text.contains("x()"));
        assert!(text.contains("One\n") && text.contains("Two <3"));
    }
    #[test]
    fn truncation_adds_marker() {
        let t = truncate_marked(&"a".repeat(100), 10);
        assert!(t.starts_with("aaaaaaaaaa") && t.contains("[truncated at 10 chars"));
        assert_eq!(truncate_marked("short", 10), "short");
    }
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cargo test --manifest-path src-tauri/Cargo.toml research::`
Expected: compile error.

- [ ] **Step 3: Implement**

Regex-based HTML stripping (regex is already a dependency; no HTML parser crate). Mark the entity decoder with `// ponytail: named entities limited to the common six; add a table if pages show raw &entity; text`.

- [ ] **Step 4: Run tests, clippy, commit**

Run: `cargo test --manifest-path src-tauri/Cargo.toml && cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings`

```bash
git add src-tauri/Cargo.toml src-tauri/Cargo.lock src-tauri/src/tools
git commit -m "feat(research): fetch_url with SSRF guard, HTML and PDF extraction"
```

---

### Task 5: `web_search` via DuckDuckGo HTML

**Files:**
- Modify: `src-tauri/src/tools/research.rs`

**Interfaces:**
```rust
pub const SEARCH_DEFAULT: usize = 5;
pub const SEARCH_MAX: usize = 10;
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SearchHit { pub title: String, pub url: String, pub snippet: String }

pub enum SearchProvider { DuckDuckGo } // one variant today; Brave or Tavily is one more arm, no trait
pub fn percent_decode(s: &str) -> String
pub fn parse_duckduckgo_html(html: &str, max: usize) -> Vec<SearchHit>
pub async fn web_search(provider: SearchProvider, query: &str, max_results: usize) -> Result<Vec<SearchHit>>
pub fn format_hits(hits: &[SearchHit]) -> String // "1. Title\n   URL\n   snippet\n"
```
`web_search`: GET `https://html.duckduckgo.com/html/` with `.query(&[("q", query)])`, timeout, user agent. `parse_duckduckgo_html`: for each `<a ... class="result__a" ... href="HREF" ...>TITLE</a>`, take the `uddg=` query parameter from HREF (after `&amp;` → `&`), percent-decode it; the next `class="result__snippet"` anchor's inner text is the snippet; strip tags and decode entities with `html_to_text` helpers; skip hits whose decoded URL fails `is_public_http_url`. Cap at `max.clamp(1, SEARCH_MAX)`. Empty result is `Ok(vec![])`, formatted as `"No results."`.

`SearchProvider` is an enum with one variant now, so Brave or Tavily later is one more arm and a key. No trait.

- [ ] **Step 1: Write failing tests**

```rust
#[test]
fn parses_duckduckgo_results() {
    let html = r#"<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Farxiv.org%2Fabs%2F2303.11366&amp;rut=abc">Reflexion: Language Agents</a>
    <a class="result__snippet" href="x">Verbal <b>reinforcement</b> learning</a>
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fevil">Local</a><a class="result__snippet">bad</a>"#;
    let hits = parse_duckduckgo_html(html, 5);
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].url, "https://arxiv.org/abs/2303.11366");
    assert_eq!(hits[0].title, "Reflexion: Language Agents");
    assert_eq!(hits[0].snippet, "Verbal reinforcement learning");
}
#[test]
fn percent_decode_handles_utf8_and_plus() {
    assert_eq!(percent_decode("a%20b%2Fc+d"), "a b/c+d");
    assert_eq!(percent_decode("%E2%9C%93"), "✓");
}
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: Implement**, then **Step 4: Run tests and commit**

```bash
git commit -am "feat(research): web_search over DuckDuckGo HTML"
```

---

### Task 6: `lookup_paper` via OpenAlex, Crossref, arXiv

**Files:**
- Modify: `src-tauri/src/tools/research.rs`

**Interfaces:**
```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PaperRecord { pub title: String, pub authors: Vec<String>, pub year: Option<i32>, pub venue: Option<String>, pub doi: Option<String>, pub url: String, pub summary: Option<String> } // summary truncated to 800 chars
pub enum PaperQuery { Doi(String), Title(String), Arxiv(String) }
pub fn parse_paper_query(doi: Option<&str>, title: Option<&str>, arxiv_id: Option<&str>) -> Result<PaperQuery> // doi "10.x/..." (strip "https://doi.org/" prefix); "arxiv:2303.11366" in doi or arxiv_id → Arxiv; else title; none → Err
pub fn parse_openalex_work(v: &serde_json::Value) -> Option<PaperRecord>
pub fn parse_crossref_work(v: &serde_json::Value) -> Option<PaperRecord>
pub fn parse_arxiv_atom(xml: &str) -> Option<PaperRecord>
pub fn title_similarity(a: &str, b: &str) -> f32 // Jaccard over lowercase alphanumeric tokens
pub async fn lookup_paper(q: &PaperQuery) -> Result<Option<PaperRecord>> // Ok(None) = not found
pub fn format_paper(p: &PaperRecord) -> String
```
Endpoints: OpenAlex `https://api.openalex.org/works/https://doi.org/{doi}` and `https://api.openalex.org/works?search={title}&per-page=1`; Crossref `https://api.crossref.org/works/{doi}` and `https://api.crossref.org/works?query.bibliographic={title}&rows=1`; arXiv `https://export.arxiv.org/api/query?id_list={id}`. Order: OpenAlex, then Crossref on error or None; Arxiv query goes straight to arXiv. Title results count only when `title_similarity(query, result.title) >= 0.6`, otherwise `None`. OpenAlex abstract is `abstract_inverted_index` (rebuild by position); Crossref abstract is JATS XML (strip tags).

- [ ] **Step 1: Write failing tests** (fixtures as inline JSON/XML strings)

```rust
#[test]
fn parses_openalex_work_and_abstract() {
    let v = serde_json::json!({"title":"Reflexion","publication_year":2023,"doi":"https://doi.org/10.48550/arxiv.2303.11366","primary_location":{"source":{"display_name":"arXiv"}},"authorships":[{"author":{"display_name":"Noah Shinn"}}],"abstract_inverted_index":{"Large":[0],"language":[1],"agents":[2]}});
    let p = parse_openalex_work(&v).unwrap();
    assert_eq!(p.year, Some(2023)); assert_eq!(p.doi.as_deref(), Some("10.48550/arxiv.2303.11366")); assert_eq!(p.authors, vec!["Noah Shinn"]); assert_eq!(p.summary.as_deref(), Some("Large language agents"));
}
#[test]
fn parses_crossref_message() {
    let v = serde_json::json!({"message":{"title":["A Paper"],"author":[{"given":"A","family":"B"}],"issued":{"date-parts":[[2021,5]]},"container-title":["Journal"],"DOI":"10.1/x","URL":"https://doi.org/10.1/x"}});
    let p = parse_crossref_work(&v).unwrap();
    assert_eq!(p.title, "A Paper"); assert_eq!(p.authors, vec!["A B"]); assert_eq!(p.year, Some(2021)); assert_eq!(p.venue.as_deref(), Some("Journal"));
}
#[test]
fn parses_arxiv_atom() {
    let xml = r#"<feed><entry><id>http://arxiv.org/abs/2303.11366v4</id><title>Reflexion: Language Agents</title><published>2023-03-20T00:00:00Z</published><author><name>Noah Shinn</name></author><summary>Abs.</summary></entry></feed>"#;
    let p = parse_arxiv_atom(xml).unwrap();
    assert_eq!(p.title, "Reflexion: Language Agents"); assert_eq!(p.year, Some(2023)); assert_eq!(p.url, "http://arxiv.org/abs/2303.11366v4");
}
#[test]
fn title_similarity_gate() {
    assert!(title_similarity("Reflexion: language agents with verbal reinforcement learning", "Reflexion: Language Agents with Verbal Reinforcement Learning") > 0.9);
    assert!(title_similarity("Reflexion language agents", "Attention is all you need") < 0.2);
}
#[test]
fn query_parsing() {
    assert!(matches!(parse_paper_query(Some("https://doi.org/10.1/x"), None, None).unwrap(), PaperQuery::Doi(d) if d == "10.1/x"));
    assert!(matches!(parse_paper_query(Some("arxiv:2303.11366"), None, None).unwrap(), PaperQuery::Arxiv(_)));
    assert!(parse_paper_query(None, None, None).is_err());
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement**, **Step 4: Tests pass, commit**

```bash
git commit -am "feat(research): lookup_paper via OpenAlex, Crossref and arXiv"
```

---

### Task 7: Tool definitions and dispatch for the seven research tools

**Files:**
- Modify: `src-tauri/src/tools/mod.rs` (seven new `ToolDefinition`s)
- Modify: `src-tauri/src/tools/ledger.rs` (`add_source` orchestration)
- Modify: `src-tauri/src/agent/mod.rs` (`execute_single_tool` arms)

**Interfaces:**
- Produces in `ledger.rs`:
  ```rust
  pub enum AddSourceInput { Doi(String), Url(String), Arxiv(String) }
  pub fn parse_add_source_args(args: &serde_json::Value) -> Result<(AddSourceInput, Option<String>)> // exactly one of doi/url/arxiv_id, optional note
  pub async fn resolve_source(input: &AddSourceInput, key: String, note: Option<String>) -> Result<Source> // Doi/Arxiv → research::lookup_paper, kind "paper"; Url → research::fetch_url(url, 1500) for title, kind "web"; bail "Could not resolve ... ; not added" on None/Err
  pub fn add_resolved(project_root: &Path, src: Source) -> Result<(Source, bool)> // (record, was_new); dedupe via find_duplicate
  ```
- Tool definitions (names and schemas exactly as the spec table): `web_search{query:string, max_results?:integer}`, `fetch_url{url:string, max_chars?:integer}`, `lookup_paper{doi?:string, title?:string, arxiv_id?:string}`, `add_source{doi?:string, url?:string, arxiv_id?:string, note?:string}`, `list_sources{}`, `check_style{path:string}`, `check_citations{path:string}`. Descriptions are one sentence each and say when to use the tool, for example `add_source`: "Register a source you will cite. Returns its key like [S3]. Only keys from this tool may be cited."
- Dispatch in `execute_single_tool`: `web_search`, `fetch_url`, `lookup_paper` run without a project (they need no root); the other four need `proj`. `add_source`: parse args, `load_ledger`, dedupe early if the input is a DOI or URL already present (return existing key with "already registered"), else `resolve_source`, then `request_approval_if_needed(..., "write", "add_source", format!("Add source {}: {}", key, title), url, None)`, then `add_resolved`, output `format!("{}\n{}", key, format_paper_or_source)`. `check_citations`: `read_workspace_file` then `check_citations` then `format_citation_report`. `check_style`: wired in Task 9; until then return `"error", "check_style not available yet"`.
- Numeric args from the model may arrive as strings: use a helper `fn arg_usize(args, name, default) -> usize` that accepts both `1` and `"1"`.

- [ ] **Step 1: Write failing tests**

In `ledger.rs`:
```rust
#[test]
fn add_source_args_require_exactly_one_identifier() {
    assert!(parse_add_source_args(&serde_json::json!({})).is_err());
    assert!(parse_add_source_args(&serde_json::json!({"doi":"10.1/x","url":"https://a"})).is_err());
    let (i, n) = parse_add_source_args(&serde_json::json!({"url":"https://a","note":"n"})).unwrap();
    assert!(matches!(i, AddSourceInput::Url(_))); assert_eq!(n.as_deref(), Some("n"));
}
#[test]
fn add_resolved_dedupes_by_doi() {
    let dir = tempfile::tempdir().unwrap();
    let mut s = src("S1"); s.doi = Some("10.1/X".into());
    let (a, new_a) = add_resolved(dir.path(), s.clone()).unwrap();
    let mut t = src("S2"); t.doi = Some("10.1/x".into());
    let (b, new_b) = add_resolved(dir.path(), t).unwrap();
    assert!(new_a && !new_b); assert_eq!(a.key, "S1"); assert_eq!(b.key, "S1");
    assert_eq!(load_ledger(dir.path()).unwrap().len(), 1);
}
```
In `tools/mod.rs`:
```rust
#[test]
fn research_tools_are_defined_with_required_args() {
    let defs = builtin_tool_definitions();
    for n in ["web_search","fetch_url","lookup_paper","add_source","list_sources","check_style","check_citations"] { assert!(defs.iter().any(|d| d.name == n), "{n}"); }
    let f = defs.iter().find(|d| d.name == "fetch_url").unwrap();
    assert_eq!(f.parameters["required"], serde_json::json!(["url"]));
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement definitions, `add_source` helpers, dispatch arms**

- [ ] **Step 4: Manual smoke (optional, needs network)**

Run: `cargo test --manifest-path src-tauri/Cargo.toml -- --ignored` after adding one `#[ignore]` test `live_lookup_reflexion_doi` that calls `lookup_paper(&PaperQuery::Arxiv("2303.11366".into()))` and asserts the title contains "Reflexion".

- [ ] **Step 5: `just check`, commit**

```bash
git commit -am "feat(research): tool definitions and dispatch for search, fetch, lookup, ledger, citations"
```

---

### Task 8: Small-model context budget and `read_file` ranges

**Files:**
- Modify: `src-tauri/src/agent/mod.rs` (`build_system_prompt` signature, truncation after tool execution, prompt-size event)
- Modify: `src-tauri/src/tools/fs.rs` (`read_workspace_file_range`)
- Modify: `src-tauri/src/tools/mod.rs` (`read_file` schema gains `start_line?`, `end_line?`)

**Interfaces:**
```rust
// agent/mod.rs
pub struct PromptBudget { pub tree_entries: usize, pub knowledge_chars: usize, pub tool_output_chars: usize }
impl PromptBudget { pub fn for_model(small: bool) -> Self } // small: 30 / 2000 / 6000; else 60 / 6000 / 20000
pub fn build_system_prompt(persona, project, knowledge_files, enabled_skills, tools, include_fallback_tool_instructions, budget: &PromptBudget, lessons: &str) -> String // `lessons` appended as "## Lessons from earlier sessions\n..." when non-empty (filled in Task 13; pass "" until then)
pub fn cap_tool_output(output: String, max_chars: usize) -> String // appends "\n[output truncated at N chars. Use read_file with start_line and end_line to read a part.]"
// fs.rs
pub fn read_workspace_file_range(project_root: &Path, user_path: &str, start_line: Option<usize>, end_line: Option<usize>) -> Result<String> // 1-based inclusive; None = whole file via read_workspace_file
```
Small-model decision per step: `settings.small_model.unwrap_or(caps.is_small())` for Ollama; `settings.small_model.unwrap_or(false)` otherwise. Emit `agent:prompt-size` `{chat_id, chars}` with the total chars of `chat_messages` each step (the eval reads it; the UI ignores it).

- [ ] **Step 1: Write failing tests**

```rust
// agent/mod.rs tests
#[test]
fn cap_tool_output_marks_truncation() {
    let out = cap_tool_output("x".repeat(50), 10);
    assert!(out.starts_with("xxxxxxxxxx") && out.contains("read_file with start_line"));
    assert_eq!(cap_tool_output("ok".into(), 10), "ok");
}
#[test]
fn small_budget_is_smaller() {
    let s = PromptBudget::for_model(true); let l = PromptBudget::for_model(false);
    assert_eq!((s.tree_entries, s.knowledge_chars, s.tool_output_chars), (30, 2000, 6000));
    assert!(l.tree_entries > s.tree_entries && l.tool_output_chars > s.tool_output_chars);
}
// fs.rs tests
#[test]
fn read_range_is_one_based_inclusive() {
    let dir = tempdir().unwrap();
    std::fs::write(dir.path().join("a.txt"), "l1\nl2\nl3\nl4\n").unwrap();
    assert_eq!(read_workspace_file_range(dir.path(), "a.txt", Some(2), Some(3)).unwrap(), "l2\nl3");
    assert_eq!(read_workspace_file_range(dir.path(), "a.txt", Some(4), Some(99)).unwrap(), "l4");
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement** (apply `cap_tool_output(output, budget.tool_output_chars)` to every tool result before `db.add_message`), **Step 4: `just check`, commit**

```bash
git commit -am "feat(agent): small-model prompt budget, tool output cap, read_file ranges"
```

---

### Task 9: `check_style` (ASD-STE100 measurable rules)

**Files:**
- Create: `src-tauri/src/tools/ste.rs`
- Modify: `src-tauri/src/tools/mod.rs` (`pub mod ste;`), `src-tauri/src/agent/mod.rs` (`check_style` arm)

**Interfaces:**
```rust
pub const UNAPPROVED_WORDS: &[(&str, &str)]; // at least 150 (unapproved, approved) pairs, lowercase
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Violation { pub line: usize, pub rule: String, pub text: String, pub hint: String }
#[derive(Debug, Serialize)]
pub struct StyleReport { pub sentences: usize, pub violations: Vec<Violation>, pub pass: bool }
pub fn split_sentences(paragraph: &str) -> Vec<String>  // split on . ! ? followed by whitespace or end; keep "e.g." and "i.e." together; ignore decimals like 3.5
pub fn check_style(markdown: &str) -> StyleReport
pub fn format_style_report(r: &StyleReport) -> String // "PASS (N sentences)" or "FAIL: K violations" then "line L [rule] text → hint"
```
Rules (rule ids in brackets): `[length]` sentence over 25 words, or over 20 words when the line is a list item (`- `, `* `, `1. `); `[paragraph]` paragraph over 6 sentences; `[passive]` regex `\b(is|are|was|were|be|been|being)\s+(\w+ed|\w+en|built|done|made|shown|given|taken|written|found|held|kept|known|left|sent|set)\b`; `[contraction]` `\b\w+'(t|re|ve|ll|d|m)\b` (possessive `'s` is not flagged); `[semicolon]` any `;`; `[noun-cluster]` 4 or more consecutive words that are not in a function-word list (articles, prepositions, conjunctions, pronouns, auxiliaries, "not") and do not end in `-ly`, `-ing`, `-ed`; `[word]` an entry from `UNAPPROVED_WORDS` with its approved alternative as the hint. Skipped: headings, fenced code, inline code, blockquotes, lines under `## References`, lines matching `^- \[S\d+\]`. `pass = violations.is_empty()`.

Seed for `UNAPPROVED_WORDS` (extend to at least 150 from the ASD-STE100 Issue 9 dictionary): `("utilize","use"), ("utilise","use"), ("commence","start"), ("terminate","stop"), ("approximately","about"), ("additional","more"), ("sufficient","enough"), ("prior to","before"), ("subsequent to","after"), ("in order to","to"), ("facilitate","help"), ("demonstrate","show"), ("indicate","show"), ("ascertain","find out"), ("endeavour","try"), ("endeavor","try"), ("attempt","try"), ("obtain","get"), ("acquire","get"), ("purchase","buy"), ("require","need"), ("necessitate","need"), ("accomplish","do"), ("perform","do"), ("conduct","do"), ("implement","do"), ("assist","help"), ("permit","let"), ("enable","let"), ("ensure","make sure"), ("verify","check"), ("examine","check"), ("inspect","check"), ("modify","change"), ("alter","change"), ("adjust","change"), ("eliminate","remove"), ("locate","find"), ("whilst","while"), ("regarding","about"), ("concerning","about"), ("numerous","many"), ("majority","most"), ("optimum","best"), ("component","part"), ("methodology","method"), ("functionality","function"), ("in the event that","if"), ("at this point in time","now")`.

Mark the noun-cluster rule `// ponytail: function-word heuristic, no POS tagger; swap for a tagger if false positives dominate the eval`.

- [ ] **Step 1: Write failing tests**

```rust
#[test] fn passes_clean_text() { let r = check_style("# Title\n\nThe tool reads the file. It returns the text.\n"); assert!(r.pass); assert_eq!(r.sentences, 2); }
#[test] fn flags_long_sentence_and_list_limit() {
    let long = (0..26).map(|_| "word").collect::<Vec<_>>().join(" ") + ".";
    assert!(check_style(&long).violations.iter().any(|v| v.rule == "length"));
    let item = "- ".to_string() + &(0..21).map(|_| "word").collect::<Vec<_>>().join(" ") + ".";
    assert!(check_style(&item).violations.iter().any(|v| v.rule == "length"));
}
#[test] fn flags_passive_contraction_semicolon_word() {
    let r = check_style("The file was written by the tool. Don't stop; utilize it.\n");
    let rules: Vec<&str> = r.violations.iter().map(|v| v.rule.as_str()).collect();
    for want in ["passive","contraction","semicolon","word"] { assert!(rules.contains(&want), "{want}"); }
    assert!(r.violations.iter().any(|v| v.rule == "word" && v.hint == "use"));
}
#[test] fn skips_code_headings_and_references() {
    let r = check_style("# Don't; utilize\n```\nutilize; don't\n```\n## References\n- [S1] A utilized; paper's title\n");
    assert!(r.pass);
}
#[test] fn flags_paragraph_over_six_sentences() {
    let p = (0..7).map(|_| "It runs.").collect::<Vec<_>>().join(" ");
    assert!(check_style(&p).violations.iter().any(|v| v.rule == "paragraph"));
}
#[test] fn split_keeps_abbreviations_and_decimals() {
    assert_eq!(split_sentences("Use 3.5 GB, e.g. two files. Then stop.").len(), 2);
}
#[test] fn word_table_has_at_least_150_entries() { assert!(UNAPPROVED_WORDS.len() >= 150); }
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement `ste.rs` and the `check_style` arm** (`read_workspace_file` → `check_style` → `format_style_report`), **Step 4: `just check`, commit**

```bash
git commit -am "feat(research): check_style for ASD-STE100 measurable rules"
```

---

### Task 10: Bundled built-in skills

**Files:**
- Create: `skills/research-method.md`, `skills/source-triage.md`, `skills/write-research-paper.md`, `skills/write-research-proposal.md`, `skills/write-ste.md`, `skills/think-in-steps.md`
- Modify: `src-tauri/src/skills.rs`, `src-tauri/src/db.rs` (`AppSettings.disabled_builtin_skills: Vec<String>`), `src-tauri/src/lib.rs` (`toggle_skill` passes `&db`), `src/lib/ipc.ts` (`source: "builtin" | "global" | "project"`), `src/components/SkillsPane.tsx` (hide nothing; badge already shows source)

**Interfaces:**
```rust
static BUNDLED_SKILLS: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/../skills");
pub fn parse_skill_file(name: &str, raw: &str) -> Option<SkillInfo> // front matter "---\ndescription: ...\n---\n" then body; source "builtin", path "builtin:<name>"
pub fn builtin_skills() -> Vec<SkillInfo>
pub fn discover_skills(db: &Database, project_root: Option<&Path>) -> Vec<SkillInfo> // builtins (enabled unless in settings.disabled_builtin_skills) → global overrides by name → project overrides by name
pub fn set_skill_enabled(db: &Database, project_root: Option<&Path>, skill_name: &str, enabled: bool) -> Result<()> // for a builtin not overridden: edit settings.disabled_builtin_skills
```
`create_custom_skill` with a builtin name is allowed and overrides it (existing project-over-global rule). `delete_custom_skill` of a builtin name removes the override only.

Skill files, each `---\ndescription: <one line>\n---` then a body under 400 words. Bodies (exact copy):

`research-method.md` description: "How to frame a research question and run a search that ends."
```
# Research method

1. Frame the question. Write one sentence that says what you want to know. Write what evidence would settle it.
2. Plan with the sequentialthinking tool. Use at most 5 thoughts (think-in-steps skill).
3. Search broad, then narrow. Start with 2 or 3 general queries. Then search for the specific terms that the first results show.
4. Prefer primary sources: the paper, the standard, the official documentation, the dataset. Use a news article or a blog only to find the primary source.
5. For each result you keep: register it with add_source, then write 2 to 4 lines in research/notes.md under a heading with its key, like `## [S2] Title`.
6. After each batch of sources, add one thought: what is still missing? Stop when the question has evidence from at least 2 independent sources, or when 3 searches in a row add nothing new.
7. If you cannot find evidence, write that in the notes. Do not fill the gap from memory.
```

`source-triage.md` description: "How to judge a search result before you read it, and how to record it."
```
# Source triage

Before you fetch a result, check:
- Domain: a university, publisher, standards body, government, or the project's own site is strong. A content farm or an unknown blog is weak.
- Date: is it recent enough for the question? Old sources are fine for history.
- Author: a named author or organization is better than none.
- Type: paper, standard, documentation, dataset, report, news, opinion. Opinion does not support a factual claim.

Choose the tool:
- A paper, a DOI, or an arXiv id: use lookup_paper first. It returns the canonical record.
- A web page or PDF: use fetch_url. Start with the default length. Ask for more only if the first part shows the page is relevant.

Record it:
- Call add_source with the DOI, arXiv id, or URL. Use the key it returns.
- In research/notes.md, write the key, the claim the source supports, and where in the source you saw it. One note per source. Quote at most one sentence.
- If add_source cannot resolve the source, do not use it.
```

`write-research-paper.md` description: "Structure and rules for a short research paper that cites only ledger sources."
```
# Write a research paper

Draft to research/drafts/<slug>.md. Write from research/notes.md only. Do not add facts you did not record.

Structure:
1. Title
2. Abstract: 4 to 6 sentences. What question, what method, what you found.
3. Background: what is known, with a [Sn] after each claim.
4. Method: how you searched and what you included or excluded.
5. Findings: one subsection per finding. Each claim has a [Sn].
6. Limitations: what you could not verify, and what is missing.
7. References: one line per source, `- [Sn] Authors (Year). Title. URL`. Build it from list_sources.

Rules:
- Every factual claim ends with a key from add_source, like [S3]. Two keys look like [S1][S4].
- Do not cite a key that is not in list_sources.
- Follow the write-ste skill.
- Before you report done: run check_style and fix the violations. Then run check_citations. If it fails, remove or re-source the claim. Report the PASS lines to the user.
```

`write-research-proposal.md` description: "Structure and rules for a research proposal that cites only ledger sources."
```
# Write a research proposal

Draft to research/drafts/<slug>-proposal.md. Write from research/notes.md only.

Structure:
1. Title
2. Problem: what is unknown or broken, and why it matters. Cite [Sn] for each claim.
3. Prior work: what others did, with [Sn]. Say what gap remains.
4. Aims: 2 to 4 numbered aims. Each aim is one sentence.
5. Method: for each aim, what you will do, what data or tools you need, and how you will know it worked.
6. Timeline: a table with phases and durations.
7. Risks: what can fail and what you will do then.
8. References: `- [Sn] Authors (Year). Title. URL`, from list_sources.

Rules: the same as write-research-paper. Every claim has a key. Run check_style, then check_citations, before you report done.
```

`write-ste.md` description: "ASD-STE100 Simplified Technical English as the house style."
```
# Write in Simplified Technical English (ASD-STE100)

Sentences:
- Procedures and list items: 20 words or fewer. Descriptions: 25 words or fewer.
- One instruction per sentence. One topic per paragraph. At most 6 sentences per paragraph.
- Active voice. Write "The tool reads the file", not "The file is read by the tool".
- Present tense for facts. Imperative for instructions.

Words:
- Use the same word for the same thing in the whole text.
- Use simple words. Some common replacements: utilize → use, commence → start, approximately → about, sufficient → enough, prior to → before, in order to → to, demonstrate → show, obtain → get, require → need, perform → do, ensure → make sure, verify → check, modify → change, numerous → many, majority → most, component → part, methodology → method.
- No contractions (don't, it's). No semicolons. Use two sentences.
- No noun clusters of more than three words. Write "the cable for the main power supply", not "main power supply cable".
- Verbs: no -ing verb forms as verbs, no complex tenses. Write "The model stops", not "The model is stopping".

Numbers and names: use digits. Define an acronym the first time.

Check: run check_style on the draft. Fix every line it reports. Run it again until it passes. Then run check_citations.
```

`think-in-steps.md` description: "How to plan with the sequentialthinking tool."
```
# Think in steps

Use the sequentialthinking tool instead of long silent reasoning.

- Before the first search: plan in at most 5 thoughts. Thought 1 states the question. Thoughts 2 to 4 list the searches and sources you expect. The last thought sets nextThoughtNeeded to false.
- After each batch of sources: one thought that says what you learned and what is still missing. If nothing is missing, set nextThoughtNeeded to false and write.
- Keep each thought under 60 words.
- thoughtNumber and totalThoughts are integers, not strings. Example: {"thought": "Find the Reflexion paper and its results.", "thoughtNumber": 1, "totalThoughts": 3, "nextThoughtNeeded": true}
- Do not repeat a thought. Do not use a thought to write the paper.
```

- [ ] **Step 1: Write failing tests in `skills.rs`**

```rust
#[test]
fn bundled_skills_parse_and_are_short() {
    let s = builtin_skills();
    let names: Vec<&str> = s.iter().map(|x| x.name.as_str()).collect();
    for n in ["research-method","source-triage","write-research-paper","write-research-proposal","write-ste","think-in-steps"] { assert!(names.contains(&n), "{n}"); }
    for x in &s { assert!(!x.description.is_empty()); assert!(x.body.split_whitespace().count() < 400, "{} too long", x.name); assert_eq!(x.source, "builtin"); }
}
#[test]
fn global_skill_overrides_builtin_and_disabled_list_applies() {
    let dir = tempfile::tempdir().unwrap();
    std::env::set_var("THEA_HOME", dir.path());
    let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
    create_custom_skill(&db, None, "global", "write-ste", "mine", "body").unwrap();
    set_skill_enabled(&db, None, "think-in-steps", false).unwrap();
    let all = discover_skills(&db, None);
    let ste = all.iter().find(|s| s.name == "write-ste").unwrap();
    assert_eq!(ste.source, "global"); assert_eq!(ste.description, "mine");
    assert!(!all.iter().find(|s| s.name == "think-in-steps").unwrap().enabled);
    assert_eq!(all.iter().filter(|s| s.name == "write-ste").count(), 1);
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Write the six files and implement**, **Step 4: `just check`, commit**

```bash
git add skills src-tauri/src src/lib/ipc.ts
git commit -m "feat(skills): bundled research skills compiled in with include_dir"
```

---

### Task 11: MCP presets, `auto_approve`, argument coercion, thought-step UI

**Files:**
- Modify: `src-tauri/src/db.rs` (`McpServerConfig.auto_approve`, `mcp_presets()`, `ensure_mcp_presets()`, `mcp_servers` column `auto_approve INTEGER NOT NULL DEFAULT 0`)
- Modify: `src-tauri/src/mcp.rs` (`coerce_arguments`)
- Modify: `src-tauri/src/agent/mod.rs` (skip approval when `srv.auto_approve`; coerce before `call_tool`)
- Modify: `src-tauri/src/lib.rs` (setup calls `ensure_mcp_presets`; command `is_command_available(name: String) -> bool` via `which`)
- Modify: `src/lib/ipc.ts`, `src/components/SettingsModal.tsx` (npx note), `src/components/ChatView.tsx` (collapsed thoughts)

**Interfaces:**
```rust
// db.rs
#[serde(default)] pub auto_approve: bool, // on McpServerConfig
pub fn mcp_presets() -> Vec<McpServerConfig> // id "sequential-thinking": name "Sequential Thinking", command "npx", args ["-y","@modelcontextprotocol/server-sequential-thinking"], enabled true, auto_approve true; id "playwright": name "Playwright", command "npx", args ["-y","@playwright/mcp@latest"], enabled false, auto_approve false
impl Database { pub fn ensure_mcp_presets(&self) -> Result<()> } // save_mcp_server for each preset whose id is absent from list_mcp_servers()
// mcp.rs
pub fn coerce_arguments(args: &mut serde_json::Value, schema: &serde_json::Value) // for each schema property with "type" integer|number|boolean whose arg is a string, parse it in place; leave unparseable values alone
```
Dispatch: in the MCP branch, `let mut args = tc.arguments.clone(); coerce_arguments(&mut args, &mcp_tool.input_schema);` then approval unless `srv.auto_approve`, then `call_tool(&mcp_tool.tool_name, &args)`.

ChatView: a tool message whose `tool_name` ends with `__sequentialthinking` renders as `<details className="...">` with `<summary>Thought</summary>` and the `thought` argument text when available from `tool_calls_json` of the preceding assistant message, else the raw output. SettingsModal MCP tab: when any enabled server has `command === "npx"` and `api.isCommandAvailable("npx")` is false, show "Node.js is required for this server. Install Node 20 or later." Sidebar/Settings add form: an `auto_approve` checkbox labeled "Run without approval (safe for read-only servers)".

- [ ] **Step 1: Write failing tests**

```rust
// mcp.rs
#[test]
fn coerces_string_numbers_and_bools() {
    let schema = serde_json::json!({"type":"object","properties":{"thoughtNumber":{"type":"integer"},"nextThoughtNeeded":{"type":"boolean"},"score":{"type":"number"},"thought":{"type":"string"}}});
    let mut args = serde_json::json!({"thoughtNumber":"1","nextThoughtNeeded":"false","score":"0.5","thought":"7","other":"x"});
    coerce_arguments(&mut args, &schema);
    assert_eq!(args, serde_json::json!({"thoughtNumber":1,"nextThoughtNeeded":false,"score":0.5,"thought":"7","other":"x"}));
}
#[test]
fn leaves_unparseable_values_alone() {
    let schema = serde_json::json!({"properties":{"n":{"type":"integer"}}});
    let mut args = serde_json::json!({"n":"abc"});
    coerce_arguments(&mut args, &schema);
    assert_eq!(args["n"], "abc");
}
// db.rs
#[test]
fn presets_are_added_once_and_deletion_sticks() {
    let dir = tempfile::tempdir().unwrap(); std::env::set_var("THEA_HOME", dir.path());
    let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
    db.ensure_mcp_presets().unwrap();
    let s = db.list_mcp_servers().unwrap();
    assert!(s.iter().any(|x| x.id == "sequential-thinking" && x.enabled && x.auto_approve));
    assert!(s.iter().any(|x| x.id == "playwright" && !x.enabled));
    db.delete_mcp_server("playwright").unwrap();
    db.ensure_mcp_presets().unwrap(); // second launch must not resurrect it ...
    // ... so ensure_mcp_presets records seeded ids in settings.seeded_mcp_presets and skips them
    assert!(!db.list_mcp_servers().unwrap().iter().any(|x| x.id == "playwright"));
}
```
Add `AppSettings.seeded_mcp_presets: Vec<String>` (serde default) to make "deleting one stays deleted" hold.

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement backend**, **Step 4: Frontend changes**, **Step 5: `just check`, commit**

```bash
git commit -am "feat(mcp): sequential-thinking and playwright presets, auto_approve, argument coercion, collapsed thoughts"
```

---

### Task 12: Event-sink seam and a single `call_model` helper

**Files:**
- Create: `src-tauri/src/agent/sink.rs`
- Modify: `src-tauri/src/agent/mod.rs` (replace `AppHandle` with `Arc<dyn EventSink>`; extract `call_model`)
- Modify: `src-tauri/src/lib.rs:383` (spawn passes `Arc::new(app.clone())`)

**Interfaces:**
```rust
// agent/sink.rs
pub trait EventSink: Send + Sync {
    fn emit_event(&self, name: &str, payload: serde_json::Value);
}
impl EventSink for tauri::AppHandle { ... } // let _ = self.emit(name, payload);
#[derive(Default)] pub struct NullSink;
impl EventSink for NullSink { fn emit_event(&self, _: &str, _: serde_json::Value) {} }
pub struct RecordingSink { pub events: std::sync::Mutex<Vec<(String, serde_json::Value)>> } // used by the eval and tests

// agent/mod.rs
pub async fn run_agent_turn(sink: Arc<dyn EventSink>, db: Arc<Database>, gate: Arc<ApprovalGate>, chat_id: String, cancel: CancellationToken) -> Result<()>
pub async fn call_model(settings: &AppSettings, provider: &str, model: &str, messages: &[ChatMessage], tools: &[ToolDefinition], native_tools: bool, options: &ChatOptions, cancel: CancellationToken, on_delta: impl FnMut(&str)) -> Result<AssistantTurn> // the protocol dispatch that today lives inline in the loop
```
Every `app.emit("x", payload)` becomes `sink.emit_event("x", serde_json::to_value(payload)?)`. `request_approval_if_needed` and `execute_single_tool` take `&dyn EventSink`.

- [ ] **Step 1: Write a failing test**

```rust
#[tokio::test]
async fn approval_request_is_emitted_through_the_sink() {
    let sink = Arc::new(RecordingSink::default());
    let gate = ApprovalGate::default();
    let cancel = CancellationToken::new();
    let c2 = cancel.clone();
    tokio::spawn(async move { tokio::time::sleep(std::time::Duration::from_millis(50)).await; c2.cancel(); });
    let ok = request_approval_if_needed(sink.as_ref(), &gate, "chat", "proj", "write", "write_file", "s".into(), "d".into(), None, &cancel).await;
    assert!(!ok);
    let ev = sink.events.lock().unwrap();
    assert_eq!(ev[0].0, "agent:approval-request");
    assert_eq!(ev[0].1["tool_name"], "write_file");
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement the seam and `call_model`** (pure refactor otherwise; behaviour unchanged), **Step 4: `just check`, launch `just run` once and send one message to confirm streaming and approvals still work, commit**

```bash
git commit -am "refactor(agent): EventSink seam and call_model helper"
```

---

### Task 13: Lessons (Reflexion with signals), rating command, UI

**Files:**
- Create: `src-tauri/src/lessons.rs`, `src-tauri/src/agent/reflection.rs`
- Modify: `src-tauri/src/agent/mod.rs` (collect signals during the run; call `reflection::maybe_reflect` after the loop; inject lessons into the prompt)
- Modify: `src-tauri/src/lib.rs` (commands `list_lessons`, `update_lesson`, `delete_lesson`, `rate_message`)
- Modify: `src/lib/ipc.ts`, `src/components/ChatView.tsx` (thumbs on the last assistant message), `src/components/SkillsPane.tsx` (Lessons section)

**Interfaces:**
```rust
// lessons.rs
pub const MAX_LESSONS: usize = 20;
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Lesson { pub date: String, pub signal: String, pub text: String }
pub fn lessons_file(persona_id: &str) -> PathBuf // thea_home_dir()/lessons/<persona_id>.md
pub fn parse_lessons(md: &str) -> Vec<Lesson>   // lines "- YYYY-MM-DD | signal | text"; other lines ignored
pub fn render_lessons(l: &[Lesson]) -> String   // "# Lessons\n\n" + one line each
pub fn load_lessons(persona_id: &str) -> Vec<Lesson>
pub fn save_lessons(persona_id: &str, l: &[Lesson]) -> Result<()>
pub fn append_lesson(persona_id: &str, lesson: Lesson) -> Result<Vec<Lesson>> // drops the oldest beyond MAX_LESSONS
pub fn format_for_prompt(l: &[Lesson]) -> String // "" when empty, else numbered "1. text" lines

// agent/reflection.rs
pub enum Signal { Citations { pass: bool, detail: String }, Rating { up: bool, comment: Option<String> }, RepeatedErrors { tool: String, error: String, count: usize } }
impl Signal { pub fn label(&self) -> &'static str } // "check_citations" | "rating_up" | "rating_down" | "repeated_errors"
pub fn detect_repeated_errors(events: &[(String, String, String)]) -> Option<Signal> // (tool_name, status, output); same tool and same first 60 chars of an "error" output 3 or more times
pub fn summarize_trajectory(messages: &[StoredMessage]) -> String // tool lines "tool_name → status/first 80 chars", then the last assistant message truncated to 1500 chars; whole summary capped at 4000 chars
pub fn reflection_prompt(trajectory: &str, signal: &Signal, existing: &[Lesson]) -> Vec<ChatMessage>
pub fn accept_lesson(raw: &str) -> Option<String> // trimmed; starts with "When"; at most 2 sentences and 300 chars; else None
pub async fn maybe_reflect(db: &Database, persona_id: &str, chat_id: &str, signal: Signal) -> Result<Option<Lesson>> // builds trajectory from db.list_messages, calls agent::call_model with no tools and ChatOptions::default(), accept_lesson, append_lesson
```
In `run_agent_turn`: track `tool_events: Vec<(String,String,String)>` and `last_citation_report: Option<(bool, String)>` (from any `check_citations` output: pass = first line starts with "PASS"). After the loop, in order: if a citation report exists → `Signal::Citations`; else if `detect_repeated_errors` → that signal; else nothing. Only one reflection per turn. Lessons are loaded once per turn and passed to `build_system_prompt` as `format_for_prompt(&lessons)`.

Reflection system prompt (exact copy): "You improve a research assistant. Read the trajectory and the signal. Write exactly one lesson for next time, at most two sentences, in the form 'When X, do Y.' Do not repeat an existing lesson. Output only the lesson."

Commands: `list_lessons(persona_id) -> Vec<Lesson>`, `update_lesson(persona_id, index, text)`, `delete_lesson(persona_id, index)`, `rate_message(chat_id, message_id, up: bool, comment: Option<String>)` which spawns `maybe_reflect` with `Signal::Rating` using the chat's persona and returns immediately.

UI: ChatView shows ThumbsUp/ThumbsDown (lucide) under the last assistant message when not streaming; on click call `api.rateMessage`, then show "Thanks. Lesson saved when the model finds one." for 3 s. SkillsPane gains a "Lessons" section listing `list_lessons(activePersonaId)` with date, signal badge, editable text (inline input on click, save on blur), and a delete button.

- [ ] **Step 1: Write failing tests**

```rust
// lessons.rs
#[test] fn roundtrip_and_fifo_cap() {
    let dir = tempfile::tempdir().unwrap(); std::env::set_var("THEA_HOME", dir.path());
    for i in 0..25 { append_lesson("p", Lesson { date: "2026-11-13".into(), signal: "rating_down".into(), text: format!("When {i}, do y.") }).unwrap(); }
    let l = load_lessons("p");
    assert_eq!(l.len(), MAX_LESSONS); assert_eq!(l[0].text, "When 5, do y."); assert_eq!(l[19].text, "When 24, do y.");
    assert_eq!(parse_lessons(&render_lessons(&l)), l);
}
#[test] fn parse_ignores_other_lines() {
    assert_eq!(parse_lessons("# Lessons\n\nfree text\n- 2026-11-13 | check_citations | When a key is missing, add the source first.\n").len(), 1);
}
// reflection.rs
#[test] fn repeated_errors_need_three_same_tool_same_message() {
    let e = |t: &str, m: &str| (t.to_string(), "error".to_string(), m.to_string());
    assert!(detect_repeated_errors(&[e("fetch_url","Error: timeout"), e("fetch_url","Error: timeout")]).is_none());
    assert!(matches!(detect_repeated_errors(&[e("fetch_url","Error: timeout"), e("fetch_url","Error: timeout"), e("fetch_url","Error: timeout x")]), Some(Signal::RepeatedErrors { count: 3, .. })));
    assert!(detect_repeated_errors(&[e("a","x"), e("b","x"), e("c","x")]).is_none());
}
#[test] fn accept_lesson_filters_shape() {
    assert_eq!(accept_lesson(" When a fetch times out, try lookup_paper instead. "), Some("When a fetch times out, try lookup_paper instead.".into()));
    assert!(accept_lesson("Sure! Here is a lesson: When x, do y.").is_none());
    assert!(accept_lesson(&format!("When x, {}", "y ".repeat(200))).is_none());
    assert!(accept_lesson("When a. Do b. Then c.").is_none());
}
#[test] fn trajectory_summary_is_capped() {
    let msgs: Vec<StoredMessage> = (0..200).map(|i| StoredMessage { role: "tool".into(), content: "x".repeat(500), tool_name: Some(format!("t{i}")), ..Default::default() }).collect();
    assert!(summarize_trajectory(&msgs).chars().count() <= 4000);
}
```
(`StoredMessage` needs `#[derive(Default)]`.)

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement backend**, **Step 4: Frontend**, **Step 5: `just check`, commit**

```bash
git commit -am "feat(agent): Reflexion lessons from citation, rating and error signals"
```

---

### Task 14: Headless eval binary and cases

**Files:**
- Create: `src-tauri/src/bin/eval.rs`, `evals/research/{reflexion,citation-rates,ste-proposal,gemma-card,openalex-vs-crossref}.json`, `evals/results/.gitkeep`
- Modify: `justfile` (recipe `eval model="gemma4:e4b"`), `.gitignore` (`evals/results/*.json`), `README.md` (one paragraph under a "Research Assistant eval" heading)

**Interfaces:**
```rust
// eval.rs (binary; uses thea_lib::{agent, db, approvals, tools::{ledger, ste}})
#[derive(Deserialize)] struct Case { id: String, prompt: String, #[serde(default = "two")] min_sources: usize }
#[derive(Serialize)] struct CaseResult { id: String, citations_pass: bool, style_violations_per_100: f32, sources: usize, thought_steps: usize, steps_used: usize, draft_produced: bool, max_prompt_chars: usize, error: Option<String> }
#[derive(Serialize)] struct Report { model: String, date: String, cases: Vec<CaseResult> }
```
Flow per case: `THEA_HOME` = a tempdir (set before anything else), `Database::open`, `reseed_builtin_personas`, `ensure_mcp_presets`, write settings with `default_provider "ollama"`, `default_model` = `--model`, `ollama_base_url` = `--base-url` (default `http://127.0.0.1:11434`); create a project in a second tempdir with persona `research-assistant`; `gate.mark_always_allowed(project_id, "write")`; create chat, add the user message, `run_agent_turn(Arc::new(RecordingSink), ...)` with a 15-minute timeout. Score: `draft_produced` = any `research/drafts/*.md`; `check_citations` over each draft against `load_ledger` (all must pass); `style_violations_per_100` = `violations * 100 / sentences` summed over drafts; `sources` = ledger length; `thought_steps` = tool messages whose name ends with `__sequentialthinking`; `steps_used` = assistant messages; `max_prompt_chars` from `agent:prompt-size` events. Print a table (id, cit, style/100, src, thoughts, steps, draft) and write `evals/results/<model-sanitized>-<YYYY-MM-DD>.json`. Exit code 1 if any `citations_pass` is false.

Cases (`prompt` field; `min_sources` 2 unless stated):
- `reflexion`: "What does the Reflexion paper by Shinn and others (2023) propose, and what results does it report on HumanEval? Write a short research paper."
- `citation-rates`: "How often do large language models fabricate citations? Collect the published measurements and write a short research paper."
- `ste-proposal`: "Write a research proposal on using ASD-STE100 Simplified Technical English to make documentation generated by language models easier to check."
- `gemma-card`: "According to Google's official model documentation, what context length and capabilities do the Gemma 3 models have? Write a short research paper." (`min_sources` 1)
- `openalex-vs-crossref`: "Compare OpenAlex and Crossref as sources of scholarly metadata, using their official documentation. Write a short research paper."

- [ ] **Step 1: Add the justfile recipe and a compile check**

```make
# Run the research eval against a local Ollama model (needs Ollama running)
eval model="gemma4:e4b":
    cargo run --manifest-path src-tauri/Cargo.toml --bin eval -- --model {{model}}
```

- [ ] **Step 2: Write `eval.rs` and the five case files**

- [ ] **Step 3: Verify it builds and parses cases without a model**

Run: `cargo run --manifest-path src-tauri/Cargo.toml --bin eval -- --model none --dry-run`
Expected: prints the five case ids and exits 0 (`--dry-run` skips the agent and scoring).

- [ ] **Step 4: Run once for real (needs Ollama with gemma4:e4b pulled)**

Run: `just eval`
Expected: a table with five rows and a results file. Record the numbers in the commit message body. If the model never produces a draft, that is a finding, not a plan failure; report it.

- [ ] **Step 5: `just check`, commit**

```bash
git add src-tauri/src/bin evals justfile .gitignore README.md
git commit -m "feat(eval): headless research eval with citation and style scoring"
```

---

### Task 15: Changelog and final review

**Files:**
- Modify: `CHANGELOG.md` (Unreleased → Added entries), `README.md` (Research Assistant paragraph: what the tools do, where `research/` lives, that lessons are in `~/.thea/lessons/`)

- [ ] **Step 1: Write the entries**, **Step 2: `just check`**, **Step 3: Commit**

```bash
git commit -am "docs: changelog and README for the research assistant"
```

Then use `superpowers:finishing-a-development-branch`.

---

## Self-review notes

- Spec coverage: section 1 tools → Tasks 3 to 9; section 2 folder → Task 3 and skills text; section 3 skills → Task 10; section 4 prompt, capabilities, budget, thinking, context window → Tasks 1, 2, 8; section 5 lessons → Task 13; 5b delivery → Tasks 2, 10, 11; section 6 MCP → Task 11; section 7 eval → Task 14. "Left to the builder" items are decided in Tasks 4 (regex stripping), 5 (DuckDuckGo parsing, user agent), 13 (thumbs under the last assistant message, `rate_message`), 3 (code-fence handling), 12 (sink seam).
- Spec deviation, stated: section 5b says presets arrive disabled, section 6 says sequential-thinking is enabled. The plan enables sequential-thinking and leaves playwright disabled, since the Research Assistant lists sequential-thinking in `mcp_server_ids`.
- Spec deviation, stated: tools live in three files (`research.rs`, `ledger.rs`, `ste.rs`) rather than one `research.rs`, so each file has one responsibility.
- Type consistency checked: `ChatOptions`, `ModelCapabilities`, `EventSink`, `Source`, `CitationReport`, `StyleReport`, `Lesson`, `Signal` are named identically wherever used.
