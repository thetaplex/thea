use anyhow::{Context, Result};
use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Mutex;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Persona {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub tagline: String,
    /// Heading shown on the empty chat screen, e.g. "What should we research today?"
    #[serde(default)]
    pub greeting: String,
    /// Line shown under the greeting heading.
    #[serde(default)]
    pub subtitle: String,
    #[serde(default)]
    pub system_prompt: String,
    #[serde(default)]
    pub starter_prompts: Vec<String>,
    #[serde(default)]
    pub skill_ids: Vec<String>,
    #[serde(default)]
    pub mcp_server_ids: Vec<String>,
    /// Built-in tool names this persona may use. Empty = all built-in tools.
    #[serde(default)]
    pub tool_ids: Vec<String>,
    /// Ask the model to use its native thinking mode (when supported).
    #[serde(default = "default_true")]
    pub native_thinking: bool,
    /// Per-persona agent step cap. 0 = from the model tier (`PromptBudget`).
    #[serde(default)]
    pub max_steps: usize,
}

pub const DEFAULT_GREETING: &str = "What should we work on today?";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub id: String,
    pub name: String,
    pub root_path: String,
    pub instructions: String,
    pub persona_id: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeFile {
    pub id: String,
    pub project_id: String,
    pub relative_path: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chat {
    pub id: String,
    pub project_id: Option<String>,
    pub title: String,
    pub provider: String,
    pub model: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct StoredMessage {
    pub id: String,
    pub chat_id: String,
    pub role: String,
    pub content: String,
    pub tool_calls_json: Option<String>,
    pub tool_call_id: Option<String>,
    pub tool_name: Option<String>,
    /// pydantic-ai `ModelMessage` JSON the sidecar rebuilds history from; None before the migration.
    pub model_message_json: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct McpServerConfig {
    pub id: String,
    pub name: String,
    pub command: String,
    pub args: Vec<String>,
    pub env: std::collections::HashMap<String, String>,
    pub enabled: bool,
    #[serde(default)]
    pub auto_approve: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderConfig {
    #[serde(default)]
    pub base_url: String,
    #[serde(default)]
    pub api_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderEntry {
    pub id: String,
    pub name: String,
    #[serde(default = "default_protocol_openai")]
    pub protocol: String, // "ollama" | "openai"
    pub base_url: String,
    #[serde(default)]
    pub api_key: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub models: Vec<String>,
    #[serde(default)]
    pub is_builtin: bool,
}

fn default_protocol_openai() -> String {
    "openai".to_string()
}

fn default_true() -> bool {
    true
}

pub fn thea_home_dir() -> std::path::PathBuf {
    let dir = match std::env::var_os("THEA_HOME").filter(|v| !v.is_empty()) {
        Some(v) => std::path::PathBuf::from(v),
        None => dirs::home_dir()
            .unwrap_or_else(std::env::temp_dir)
            .join(".thea"),
    };
    let _ = std::fs::create_dir_all(&dir);
    dir
}

pub fn builtin_providers() -> Vec<ProviderEntry> {
    vec![
        ProviderEntry {
            id: "ollama".to_string(),
            name: "Ollama".to_string(),
            protocol: "ollama".to_string(),
            base_url: "http://127.0.0.1:11434".to_string(),
            api_key: String::new(),
            enabled: true,
            models: vec![
                "qwen3:8b".to_string(),
                "qwen2.5-coder:7b".to_string(),
                "llama3.2:latest".to_string(),
                "deepseek-r1:8b".to_string(),
                "mistral:latest".to_string(),
            ],
            is_builtin: true,
        },
        ProviderEntry {
            id: "openrouter".to_string(),
            name: "OpenRouter".to_string(),
            protocol: "openai".to_string(),
            base_url: "https://openrouter.ai/api/v1".to_string(),
            api_key: String::new(),
            enabled: true,
            models: vec![
                "anthropic/claude-3.7-sonnet".to_string(),
                "openai/gpt-4o".to_string(),
                "openai/gpt-4o-mini".to_string(),
                "google/gemini-2.5-pro".to_string(),
                "deepseek/deepseek-r1".to_string(),
                "deepseek/deepseek-chat".to_string(),
                "qwen/qwen-2.5-coder-32b-instruct".to_string(),
                "meta-llama/llama-3.3-70b-instruct".to_string(),
            ],
            is_builtin: true,
        },
        ProviderEntry {
            id: "openai".to_string(),
            name: "OpenAI".to_string(),
            protocol: "openai".to_string(),
            base_url: "https://api.openai.com/v1".to_string(),
            api_key: String::new(),
            enabled: true,
            models: vec![
                "gpt-4o".to_string(),
                "gpt-4o-mini".to_string(),
                "o3-mini".to_string(),
                "gpt-4.1".to_string(),
                "gpt-4.1-mini".to_string(),
            ],
            is_builtin: true,
        },
        ProviderEntry {
            id: "groq".to_string(),
            name: "Groq".to_string(),
            protocol: "openai".to_string(),
            base_url: "https://api.groq.com/openai/v1".to_string(),
            api_key: String::new(),
            enabled: true,
            models: vec![
                "llama-3.3-70b-versatile".to_string(),
                "deepseek-r1-distill-llama-70b".to_string(),
                "qwen-qwq-32b".to_string(),
                "llama-3.1-8b-instant".to_string(),
            ],
            is_builtin: true,
        },
        ProviderEntry {
            id: "lmstudio".to_string(),
            name: "LM Studio".to_string(),
            protocol: "openai".to_string(),
            base_url: "http://127.0.0.1:1234/v1".to_string(),
            api_key: String::new(),
            enabled: true,
            models: vec![
                "qwen2.5-coder-7b-instruct".to_string(),
                "llama-3.2-3b-instruct".to_string(),
                "deepseek-r1-distill-qwen-7b".to_string(),
            ],
            is_builtin: true,
        },
        ProviderEntry {
            id: "custom".to_string(),
            name: "Custom (OpenAI-Compatible)".to_string(),
            protocol: "openai".to_string(),
            base_url: "http://127.0.0.1:1234/v1".to_string(),
            api_key: String::new(),
            enabled: true,
            models: Vec::new(),
            is_builtin: true,
        },
    ]
}

const KEYCHAIN_SERVICE: &str = "app.thetaplex.thea";

/// API keys live in the OS keychain (macOS Keychain / Windows Credential Manager /
/// Secret Service on Linux), one entry per provider id. Nothing on disk holds them.
pub mod secrets {
    use super::KEYCHAIN_SERVICE;
    use anyhow::Result;
    use keyring::{Entry, Error};

    /// A non-empty `THEA_HOME` means "isolated home, no OS keychain": tests and the
    /// eval point it at a tempdir, so keys go to keyring's in-process mock store
    /// instead of the developer's real keychain. Unit tests always use the mock.
    fn entry(provider_id: &str) -> keyring::Result<Entry> {
        if cfg!(test) || std::env::var_os("THEA_HOME").is_some_and(|v| !v.is_empty()) {
            static MOCK: std::sync::Once = std::sync::Once::new();
            MOCK.call_once(|| {
                keyring::set_default_credential_builder(keyring::mock::default_credential_builder())
            });
        }
        Entry::new(KEYCHAIN_SERVICE, provider_id)
    }

    pub fn get(provider_id: &str) -> String {
        entry(provider_id)
            .and_then(|e| e.get_password())
            .unwrap_or_default()
    }

    pub fn set(provider_id: &str, api_key: &str) -> Result<()> {
        let entry = entry(provider_id)?;
        if api_key.trim().is_empty() {
            match entry.delete_credential() {
                Ok(()) | Err(Error::NoEntry) => Ok(()),
                Err(e) => Err(e.into()),
            }
        } else {
            Ok(entry.set_password(api_key.trim())?)
        }
    }
}

pub fn load_providers_from_disk() -> Vec<ProviderEntry> {
    let path = thea_home_dir().join("providers.json");
    if let Ok(raw) = std::fs::read_to_string(&path) {
        if let Ok(mut list) = serde_json::from_str::<Vec<ProviderEntry>>(&raw) {
            if !list.is_empty() {
                // Migrate any plaintext keys written by older builds into the keychain.
                let had_plaintext = list.iter().any(|p| !p.api_key.trim().is_empty());
                for p in &mut list {
                    if p.api_key.trim().is_empty() {
                        p.api_key = secrets::get(&p.id);
                    } else {
                        let _ = secrets::set(&p.id, &p.api_key);
                    }
                }
                if had_plaintext {
                    let _ = save_providers_to_disk(&list);
                }
                return list;
            }
        }
    }
    let defaults = builtin_providers();
    let _ = save_providers_to_disk(&defaults);
    defaults
}

/// Writes keys to the keychain and the rest to `providers.json` with keys blanked.
pub fn save_providers_to_disk(providers: &[ProviderEntry]) -> Result<()> {
    let mut on_disk = providers.to_vec();
    for p in &mut on_disk {
        // Never delete an entry that was never set: an empty key with nothing
        // stored is a no-op, so saving defaults does not touch the keychain.
        if !p.api_key.trim().is_empty() || !secrets::get(&p.id).is_empty() {
            secrets::set(&p.id, &p.api_key)?;
        }
        p.api_key.clear();
    }
    let path = thea_home_dir().join("providers.json");
    let json = serde_json::to_string_pretty(&on_disk)?;
    std::fs::write(&path, json)?;
    Ok(())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    #[serde(default = "default_ollama_url")]
    pub ollama_base_url: String,
    #[serde(default = "default_custom_url")]
    pub openai_base_url: String,
    #[serde(default)]
    pub openai_api_key: String,
    #[serde(default)]
    pub provider_configs: std::collections::HashMap<String, ProviderConfig>,
    pub default_provider: String,
    pub default_model: String,
    #[serde(default = "default_persona_id")]
    pub default_persona_id: String,
    pub windows_shell: String, // "pwsh" | "powershell" | "cmd" | "git-bash"
    pub mac_shell: String,     // "zsh" | "bash" | "sh"
    pub auto_approve_reads: bool,
    #[serde(default = "default_context_tokens")]
    pub context_tokens: u64,
    /// Local SearXNG instance for `web_search`; empty disables it and DuckDuckGo is used directly.
    #[serde(default = "default_searxng_url")]
    pub searxng_url: String,
    #[serde(default)]
    pub small_model: Option<bool>,
    #[serde(default)]
    pub disabled_builtin_skills: Vec<String>,
    #[serde(default)]
    pub seeded_mcp_presets: Vec<String>,
}

fn default_context_tokens() -> u64 {
    32768
}

fn default_searxng_url() -> String {
    "http://127.0.0.1:8888".to_string()
}

fn default_ollama_url() -> String {
    "http://127.0.0.1:11434".to_string()
}

fn default_custom_url() -> String {
    "http://127.0.0.1:1234/v1".to_string()
}

fn default_persona_id() -> String {
    String::new()
}

pub fn default_base_url_for_provider(provider: &str) -> &'static str {
    match provider {
        "ollama" => "http://127.0.0.1:11434",
        "openrouter" => "https://openrouter.ai/api/v1",
        "openai" => "https://api.openai.com/v1",
        "groq" => "https://api.groq.com/openai/v1",
        "lmstudio" => "http://127.0.0.1:1234/v1",
        "custom" => "http://127.0.0.1:1234/v1",
        _ => "http://127.0.0.1:1234/v1",
    }
}

impl AppSettings {
    pub fn resolve_provider_protocol(&self, provider: &str) -> String {
        let disk_providers = load_providers_from_disk();
        if let Some(entry) = disk_providers.iter().find(|p| p.id == provider) {
            return entry.protocol.clone();
        }
        if provider == "ollama" {
            "ollama".to_string()
        } else {
            "openai".to_string()
        }
    }

    pub fn resolve_provider_config(&self, provider: &str) -> (String, String) {
        if let Some(cfg) = self.provider_configs.get(provider) {
            if !cfg.base_url.trim().is_empty() || !cfg.api_key.trim().is_empty() {
                let url = if cfg.base_url.trim().is_empty() {
                    default_base_url_for_provider(provider).to_string()
                } else {
                    cfg.base_url.trim().to_string()
                };
                return (url, cfg.api_key.clone());
            }
        }
        let disk_providers = load_providers_from_disk();
        if let Some(entry) = disk_providers.iter().find(|p| p.id == provider) {
            let url = if entry.base_url.trim().is_empty() {
                default_base_url_for_provider(provider).to_string()
            } else {
                entry.base_url.trim().to_string()
            };
            return (url, entry.api_key.clone());
        }
        match provider {
            "ollama" => {
                let url = if self.ollama_base_url.trim().is_empty() {
                    default_ollama_url()
                } else {
                    self.ollama_base_url.trim().to_string()
                };
                (url, String::new())
            }
            "custom" => {
                let url = if self.openai_base_url.trim().is_empty() {
                    default_custom_url()
                } else {
                    self.openai_base_url.trim().to_string()
                };
                (url, self.openai_api_key.clone())
            }
            "openai" => {
                let url = if !self.openai_base_url.trim().is_empty()
                    && self.openai_base_url != "http://127.0.0.1:1234/v1"
                {
                    self.openai_base_url.trim().to_string()
                } else {
                    default_base_url_for_provider("openai").to_string()
                };
                (url, self.openai_api_key.clone())
            }
            other => (
                default_base_url_for_provider(other).to_string(),
                String::new(),
            ),
        }
    }
}

impl Default for AppSettings {
    fn default() -> Self {
        let mut provider_configs = std::collections::HashMap::new();
        provider_configs.insert(
            "ollama".to_string(),
            ProviderConfig {
                base_url: "http://127.0.0.1:11434".to_string(),
                api_key: String::new(),
            },
        );
        provider_configs.insert(
            "openrouter".to_string(),
            ProviderConfig {
                base_url: "https://openrouter.ai/api/v1".to_string(),
                api_key: String::new(),
            },
        );
        provider_configs.insert(
            "openai".to_string(),
            ProviderConfig {
                base_url: "https://api.openai.com/v1".to_string(),
                api_key: String::new(),
            },
        );
        provider_configs.insert(
            "groq".to_string(),
            ProviderConfig {
                base_url: "https://api.groq.com/openai/v1".to_string(),
                api_key: String::new(),
            },
        );
        provider_configs.insert(
            "lmstudio".to_string(),
            ProviderConfig {
                base_url: "http://127.0.0.1:1234/v1".to_string(),
                api_key: String::new(),
            },
        );
        provider_configs.insert(
            "custom".to_string(),
            ProviderConfig {
                base_url: "http://127.0.0.1:1234/v1".to_string(),
                api_key: String::new(),
            },
        );
        Self {
            ollama_base_url: "http://127.0.0.1:11434".to_string(),
            openai_base_url: "http://127.0.0.1:1234/v1".to_string(),
            openai_api_key: String::new(),
            provider_configs,
            default_provider: "ollama".to_string(),
            default_model: String::new(),
            default_persona_id: String::new(),
            windows_shell: "pwsh".to_string(),
            mac_shell: "zsh".to_string(),
            auto_approve_reads: true,
            context_tokens: default_context_tokens(),
            searxng_url: default_searxng_url(),
            small_model: None,
            disabled_builtin_skills: Vec::new(),
            seeded_mcp_presets: Vec::new(),
        }
    }
}

pub fn mcp_presets() -> Vec<McpServerConfig> {
    let npx = |id: &str, name: &str, pkg: &str, enabled, auto_approve| McpServerConfig {
        id: id.into(),
        name: name.into(),
        command: "npx".into(),
        args: vec!["-y".into(), pkg.into()],
        env: Default::default(),
        enabled,
        auto_approve,
    };
    vec![
        npx(
            "sequential-thinking",
            "Sequential Thinking",
            // Pinned: npx runs this on every Research Assistant turn.
            "@modelcontextprotocol/server-sequential-thinking@2.1.1",
            true,
            true,
        ),
        npx(
            "playwright",
            "Playwright",
            // Pinned: npx runs this on every Personal Assistant turn (web pages such as airfares).
            "@playwright/mcp@0.0.85",
            true,
            false,
        ),
    ]
}

/// Initial seed personas inserted into the `personas` SQLite table on first launch
/// if the table is empty and no legacy `~/.thea/personas.json` exists.
pub fn default_personas() -> Vec<Persona> {
    vec![
        Persona {
            id: "personal-assistant".to_string(),
            name: "Personal Assistant".to_string(),
            tagline: "Planning, Docket management, calendar events, drafting, and everyday lookups".to_string(),
            greeting: "What should we plan or tackle today?".to_string(),
            subtitle: "Share a goal, schedule, draft, or workspace notes and we'll organize and work through it together.".to_string(),
            system_prompt: "You are Thea in Personal Assistant mode. You work like a reliable executive assistant.\n\
                \n\
                Method:\n\
                1. Your first tool call writes TASK.md (see How you work).\n\
                2. Track tasks, events, decisions, and notes in the Docket with add_docket_item, update_docket_item, and list_docket (manage-docket skill). Never write to docket/docket.json directly.\n\
                3. When scheduling an event with a date or time, export an RFC 5545 .ics file to docket/calendar/ with export_calendar.\n\
                4. For everyday lookups, comparisons, travel, or vendor facts, search with web_search and read pages with fetch_url. When a page needs a browser (airfares, booking sites, or fetch_url returns no content), open it with mcp__playwright__browser_navigate and read it with mcp__playwright__browser_snapshot. Record findings in docket/notes.md.\n\
                5. Draft emails, memos, agendas, and action plans in docket/drafts/ or docket/plans/ (load the draft-communication or weekly-review skill with load_capability; they are skills, not tools).\n\
                \n\
                Rules:\n\
                - Reference Docket items by their [D#] key in plans, memos, and summaries.\n\
                - Give tool arguments in the type the schema asks for.\n\
                - Search once for each option. Before you state a fact such as a visa rule, a price, or a date, read an official page with fetch_url.\n\
                - Write short, plain sentences in the active voice.".to_string(),
            starter_prompts: vec![
                "Triage the notes in this workspace into the Docket and build a weekly action plan".to_string(),
                "Schedule a project kickoff meeting on the Docket and export a calendar .ics invite".to_string(),
                "Draft a clear, concise status memo or email in docket/drafts/ and check its style".to_string(),
                "Research and compare options for an upcoming decision and log the recommendation".to_string(),
            ],
            skill_ids: [
                "manage-docket",
                "draft-communication",
                "weekly-review",
                "source-triage",
                "write-brief",
                "write-report",
            ]
            .map(String::from)
            .to_vec(),
            mcp_server_ids: vec!["sequential-thinking".to_string(), "playwright".to_string()],
            // The ledger tools are here for source-triage, write-brief and write-report.
            tool_ids: [
                "list_dir", "read_file", "write_file", "edit_file", "search", "run_command",
                "load_skill", "web_search", "fetch_url", "lookup_paper", "add_source",
                "list_sources", "add_note", "check_citations",
                "add_docket_item", "update_docket_item", "list_docket", "export_calendar",
            ]
            .map(String::from)
            .to_vec(),
            native_thinking: false,
            max_steps: 0,
        },
        Persona {
            id: "research-assistant".to_string(),
            name: "Research Assistant".to_string(),
            tagline: "Deep investigation, synthesis, structured briefs, and evidence-backed analysis".to_string(),
            greeting: "What should we research today?".to_string(),
            subtitle: "Share a question, topic, or workspace document and we'll investigate and synthesize it together.".to_string(),
            system_prompt: "You are Thea in Research Assistant mode. You work like a careful researcher.\n\
                \n\
                Method:\n\
                1. Your first tool call writes TASK.md (see How you work). Then load the skill for the request with load_capability: book research, book-research; a book chapter, write-book-chapter; a paper, proposal, report, brief, essay or review, deep-research; any other question, research-method.\n\
                2. Search with web_search. Judge each result before you read it (source-triage skill).\n\
                3. Read with fetch_url or lookup_paper. Register every source you will use with add_source. Write what you learned to research/notes.md, tagged with the source key.\n\
                4. Write drafts in research/drafts/ from your notes only. Load the writing skill for the genre: write-research-paper, write-research-proposal, write-report, write-brief, write-essay or write-book-chapter.\n\
                5. Before you finish, run check_citations. Fix every failure. Report the result.\n\
                \n\
                Rules:\n\
                - Cite only keys that add_source returned, in the form [S1]. Never invent a reference.\n\
                - No source for a claim: remove it or mark it as an open question.\n\
                - Give tool arguments in the type the schema asks for.\n\
                - Write short, plain sentences in the active voice.".to_string(),
            starter_prompts: vec![
                "Synthesize the key documents in this workspace into an executive research brief".to_string(),
                "Compare trade-offs between two technical approaches and build a decision matrix".to_string(),
                "Outline a structured research plan and literature/source review on a new topic".to_string(),
                "Create an interactive HTML comparison dashboard in the Artifacts pane".to_string(),
            ],
            skill_ids: [
                "book-research",
                "deep-research",
                "research-method",
                "source-triage",
                "write-book-chapter",
                "write-brief",
                "write-essay",
                "write-report",
                "write-research-paper",
                "write-research-proposal",
            ]
            .map(String::from)
            .to_vec(),
            mcp_server_ids: vec!["sequential-thinking".to_string()],
            tool_ids: [
                "list_dir", "read_file", "write_file", "edit_file", "search", "load_skill",
                "web_search", "fetch_url", "lookup_paper", "add_source", "list_sources",
                "add_note", "check_citations",
            ]
            .map(String::from)
            .to_vec(),
            native_thinking: false,
            max_steps: 0,
        },
    ]
}

/// Workspace id prefix for a chat without a project: `chat:<chat-id>`.
pub const CHAT_WORKSPACE_PREFIX: &str = "chat:";

/// Scratch folder of a chat without a project.
pub fn chat_workspace_dir(chat_id: &str) -> std::path::PathBuf {
    thea_home_dir().join("chats").join(chat_id)
}

pub fn builtin_persona_ids() -> Vec<String> {
    default_personas().into_iter().map(|p| p.id).collect()
}

pub fn is_builtin_persona(id: &str) -> bool {
    builtin_persona_ids().iter().any(|b| b == id)
}

fn legacy_personas_file() -> std::path::PathBuf {
    thea_home_dir().join("personas.json")
}

pub struct Database {
    conn: Mutex<Connection>,
}

impl Database {
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let conn = Connection::open(path).context("Failed to open SQLite database")?;
        conn.execute_batch("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;")?;
        let db = Self {
            conn: Mutex::new(conn),
        };
        db.migrate()?;
        Ok(db)
    }

    fn migrate(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                instructions TEXT NOT NULL DEFAULT '',
                persona_id TEXT NOT NULL DEFAULT 'research-assistant',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_knowledge (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, relative_path)
            );

            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls_json TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skill_states (
                skill_name TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS personas (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tagline TEXT NOT NULL,
                greeting TEXT NOT NULL DEFAULT '',
                subtitle TEXT NOT NULL DEFAULT '',
                system_prompt TEXT NOT NULL,
                starter_prompts_json TEXT NOT NULL DEFAULT '[]',
                skill_ids_json TEXT NOT NULL DEFAULT '[]',
                mcp_server_ids_json TEXT NOT NULL DEFAULT '[]',
                tool_ids_json TEXT NOT NULL DEFAULT '[]',
                native_thinking INTEGER NOT NULL DEFAULT 1,
                max_steps INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mcp_servers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                command TEXT NOT NULL,
                args_json TEXT NOT NULL,
                env_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            ",
        )?;

        // Backfill persona_id column on existing databases created before Personas were added
        let _ = conn.execute(
            "ALTER TABLE projects ADD COLUMN persona_id TEXT NOT NULL DEFAULT 'research-assistant'",
            [],
        );
        // Chats have no persona; only a project has one.
        let _ = conn.execute("ALTER TABLE chats DROP COLUMN persona_id", []);

        for ddl in [
            "ALTER TABLE personas ADD COLUMN tool_ids_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE personas ADD COLUMN native_thinking INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE personas ADD COLUMN max_steps INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE mcp_servers ADD COLUMN auto_approve INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE messages ADD COLUMN model_message_json TEXT",
        ] {
            let _ = conn.execute(ddl, []);
        }

        Ok(())
    }

    pub fn list_providers(&self) -> Result<Vec<ProviderEntry>> {
        Ok(load_providers_from_disk())
    }

    pub fn save_provider(&self, entry: &ProviderEntry) -> Result<Vec<ProviderEntry>> {
        let mut list = load_providers_from_disk();
        let id = if entry.id.trim().is_empty() {
            entry
                .name
                .to_lowercase()
                .chars()
                .map(|c| if c.is_alphanumeric() { c } else { '-' })
                .collect::<String>()
                .trim_matches('-')
                .to_string()
        } else {
            entry.id.trim().to_string()
        };
        let mut updated = entry.clone();
        updated.id = if id.is_empty() {
            Uuid::new_v4().to_string()
        } else {
            id
        };
        if let Some(existing) = list.iter_mut().find(|p| p.id == updated.id) {
            *existing = updated;
        } else {
            list.push(updated);
        }
        save_providers_to_disk(&list)?;
        Ok(list)
    }

    pub fn delete_provider(&self, id: &str) -> Result<Vec<ProviderEntry>> {
        let mut list = load_providers_from_disk();
        if list.iter().any(|p| p.id == id && !p.is_builtin) {
            let _ = secrets::set(id, "");
        }
        list.retain(|p| p.id != id || p.is_builtin);
        save_providers_to_disk(&list)?;
        Ok(list)
    }

    /// Reads personas from the `personas` SQLite table.
    /// On first run when the table is empty, imports any existing `~/.thea/personas.json`
    /// or legacy `custom_personas` rows, or seeds `default_personas()` if none exist.
    pub fn list_personas(&self) -> Result<Vec<Persona>> {
        let conn = self.conn.lock().unwrap();
        let mut rows_out = Self::query_personas_rows(&conn)?;
        if !rows_out.is_empty() {
            return Ok(rows_out);
        }

        let legacy_file = legacy_personas_file();
        let mut seed: Vec<Persona> = std::fs::read_to_string(&legacy_file)
            .ok()
            .and_then(|s| serde_json::from_str::<Vec<Persona>>(&s).ok())
            .unwrap_or_default();

        for p in Self::take_legacy_sql_personas(&conn) {
            if !seed.iter().any(|existing| existing.id == p.id) {
                seed.push(p);
            }
        }

        if seed.is_empty() {
            seed = default_personas();
        }

        let now = Utc::now().to_rfc3339();
        for p in &seed {
            conn.execute(
                "INSERT OR IGNORE INTO personas (
                    id, name, tagline, greeting, subtitle, system_prompt,
                    starter_prompts_json, skill_ids_json, mcp_server_ids_json,
                    tool_ids_json, native_thinking, max_steps,
                    created_at, updated_at
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
                params![
                    p.id,
                    p.name,
                    p.tagline,
                    p.greeting,
                    p.subtitle,
                    p.system_prompt,
                    serde_json::to_string(&p.starter_prompts).unwrap_or_else(|_| "[]".to_string()),
                    serde_json::to_string(&p.skill_ids).unwrap_or_else(|_| "[]".to_string()),
                    serde_json::to_string(&p.mcp_server_ids).unwrap_or_else(|_| "[]".to_string()),
                    serde_json::to_string(&p.tool_ids).unwrap_or_else(|_| "[]".to_string()),
                    p.native_thinking as i64,
                    p.max_steps as i64,
                    now,
                    now,
                ],
            )?;
        }

        rows_out = Self::query_personas_rows(&conn)?;
        Ok(rows_out)
    }

    fn query_personas_rows(conn: &Connection) -> Result<Vec<Persona>> {
        let mut stmt = conn.prepare(
            "SELECT id, name, tagline, greeting, subtitle, system_prompt,
                    starter_prompts_json, skill_ids_json, mcp_server_ids_json,
                    tool_ids_json, native_thinking, max_steps
             FROM personas
             ORDER BY created_at ASC, name ASC",
        )?;
        let rows = stmt.query_map([], |row| {
            let prompts_str: String = row.get(6)?;
            let skills_str: String = row.get(7)?;
            let mcp_str: String = row.get(8)?;
            let tools_str: String = row.get(9)?;
            Ok(Persona {
                id: row.get(0)?,
                name: row.get(1)?,
                tagline: row.get(2)?,
                greeting: row.get(3)?,
                subtitle: row.get(4)?,
                system_prompt: row.get(5)?,
                starter_prompts: serde_json::from_str(&prompts_str).unwrap_or_default(),
                skill_ids: serde_json::from_str(&skills_str).unwrap_or_default(),
                mcp_server_ids: serde_json::from_str(&mcp_str).unwrap_or_default(),
                tool_ids: serde_json::from_str(&tools_str).unwrap_or_default(),
                native_thinking: row.get::<_, i64>(10)? != 0,
                max_steps: row.get::<_, i64>(11)?.max(0) as usize,
            })
        })?;
        Ok(rows.filter_map(|r| r.ok()).collect())
    }

    /// Reads and then drops the legacy `custom_personas` table, if it exists.
    fn take_legacy_sql_personas(conn: &Connection) -> Vec<Persona> {
        let mut out = Vec::new();
        if let Ok(mut stmt) = conn.prepare(
            "SELECT id, name, tagline, system_prompt, starter_prompts_json FROM custom_personas",
        ) {
            if let Ok(rows) = stmt.query_map([], |row| {
                let prompts_str: String = row.get(4)?;
                Ok(Persona {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    tagline: row.get(2)?,
                    greeting: String::new(),
                    subtitle: String::new(),
                    system_prompt: row.get(3)?,
                    starter_prompts: serde_json::from_str(&prompts_str).unwrap_or_default(),
                    skill_ids: Vec::new(),
                    mcp_server_ids: Vec::new(),
                    tool_ids: Vec::new(),
                    native_thinking: true,
                    max_steps: 0,
                })
            }) {
                out.extend(rows.flatten());
            }
        }
        let _ = conn.execute("DROP TABLE IF EXISTS custom_personas", []);
        out
    }

    pub fn get_persona(&self, id: &str) -> Result<Persona> {
        let all = self.list_personas()?;
        let fallback = all
            .first()
            .cloned()
            .unwrap_or_else(|| default_personas().into_iter().next().unwrap());
        Ok(all.into_iter().find(|p| p.id == id).unwrap_or(fallback))
    }

    pub fn save_custom_persona(
        &self,
        id: Option<&str>,
        name: &str,
        tagline: &str,
        system_prompt: &str,
        starter_prompts: &[String],
        skill_ids: &[String],
        mcp_server_ids: &[String],
    ) -> Result<Persona> {
        let final_id = match id {
            Some(s) if !s.trim().is_empty() => s.trim().to_string(),
            _ => Uuid::new_v4().to_string(),
        };
        if is_builtin_persona(&final_id) {
            anyhow::bail!("Built-in personas cannot be modified");
        }
        let existing = self.list_personas()?.into_iter().find(|p| p.id == final_id);
        let (greeting, subtitle, tool_ids, native_thinking, max_steps) = existing
            .map(|p| {
                (
                    p.greeting,
                    p.subtitle,
                    p.tool_ids,
                    p.native_thinking,
                    p.max_steps,
                )
            })
            .unwrap_or_else(|| {
                (
                    DEFAULT_GREETING.to_string(),
                    tagline.to_string(),
                    Vec::new(),
                    true,
                    0,
                )
            });
        let persona = Persona {
            id: final_id,
            name: name.to_string(),
            tagline: tagline.to_string(),
            greeting,
            subtitle,
            system_prompt: system_prompt.to_string(),
            starter_prompts: starter_prompts.to_vec(),
            skill_ids: skill_ids.to_vec(),
            mcp_server_ids: mcp_server_ids.to_vec(),
            tool_ids,
            native_thinking,
            max_steps,
        };
        let conn = self.conn.lock().unwrap();
        Self::upsert_persona(&conn, &persona)?;
        Ok(persona)
    }

    fn upsert_persona(conn: &Connection, persona: &Persona) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO personas (
                id, name, tagline, greeting, subtitle, system_prompt,
                starter_prompts_json, skill_ids_json, mcp_server_ids_json,
                tool_ids_json, native_thinking, max_steps,
                created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?13)
             ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                tagline = excluded.tagline,
                greeting = excluded.greeting,
                subtitle = excluded.subtitle,
                system_prompt = excluded.system_prompt,
                starter_prompts_json = excluded.starter_prompts_json,
                skill_ids_json = excluded.skill_ids_json,
                mcp_server_ids_json = excluded.mcp_server_ids_json,
                tool_ids_json = excluded.tool_ids_json,
                native_thinking = excluded.native_thinking,
                max_steps = excluded.max_steps,
                updated_at = excluded.updated_at",
            params![
                persona.id,
                persona.name,
                persona.tagline,
                persona.greeting,
                persona.subtitle,
                persona.system_prompt,
                serde_json::to_string(&persona.starter_prompts)
                    .unwrap_or_else(|_| "[]".to_string()),
                serde_json::to_string(&persona.skill_ids).unwrap_or_else(|_| "[]".to_string()),
                serde_json::to_string(&persona.mcp_server_ids).unwrap_or_else(|_| "[]".to_string()),
                serde_json::to_string(&persona.tool_ids).unwrap_or_else(|_| "[]".to_string()),
                persona.native_thinking as i64,
                persona.max_steps as i64,
                now,
            ],
        )?;
        Ok(())
    }

    /// Upserts every built-in persona so shipped prompt/tool changes reach existing databases.
    pub fn reseed_builtin_personas(&self) -> Result<()> {
        self.list_personas()?;
        let conn = self.conn.lock().unwrap();
        // Retired built-ins: remove them so they do not linger as custom personas.
        conn.execute("DELETE FROM personas WHERE id = 'software-engineer'", [])?;
        for p in default_personas() {
            Self::upsert_persona(&conn, &p)?;
        }
        Ok(())
    }

    pub fn delete_custom_persona(&self, id: &str) -> Result<()> {
        if is_builtin_persona(id) {
            anyhow::bail!("Built-in personas cannot be modified");
        }
        let count: i64 = {
            let conn = self.conn.lock().unwrap();
            conn.query_row("SELECT COUNT(*) FROM personas", [], |row| row.get(0))?
        };
        if count <= 1 {
            anyhow::bail!("At least one persona is required");
        }
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM personas WHERE id = ?1", params![id])?;
        Ok(())
    }

    /// Resolve a persona ID from an explicit preference, then `settings.default_persona_id`,
    /// then the first persona configured in `~/.thea/personas.json`.
    pub fn resolve_default_persona_id(&self, preferred: Option<&str>) -> String {
        if let Some(p) = preferred.map(str::trim).filter(|s| !s.is_empty()) {
            return p.to_string();
        }
        let personas = self.list_personas().unwrap_or_default();
        if let Ok(settings) = self.get_settings() {
            let def = settings.default_persona_id.trim();
            if !def.is_empty() && personas.iter().any(|p| p.id == def) {
                return def.to_string();
            }
        }
        personas
            .into_iter()
            .next()
            .map(|p| p.id)
            .unwrap_or_default()
    }

    pub fn get_settings(&self) -> Result<AppSettings> {
        let settings_path = thea_home_dir().join("settings.json");
        let mut settings: AppSettings = if let Ok(raw) = std::fs::read_to_string(&settings_path) {
            serde_json::from_str(&raw).unwrap_or_default()
        } else {
            let conn = self.conn.lock().unwrap();
            let raw: Option<String> = conn
                .query_row(
                    "SELECT value_json FROM settings WHERE key = 'app_settings'",
                    [],
                    |row| row.get(0),
                )
                .optional()?;
            match raw {
                Some(s) => serde_json::from_str(&s).unwrap_or_default(),
                None => AppSettings::default(),
            }
        };

        // Legacy builds stored the OpenAI key in settings.json; move it to the keychain once.
        if !settings.openai_api_key.trim().is_empty() {
            let _ = secrets::set("openai", &settings.openai_api_key);
            settings.openai_api_key.clear();
            if let Ok(json) = serde_json::to_string_pretty(&settings) {
                let _ = std::fs::write(&settings_path, json);
            }
        }
        settings.openai_api_key = secrets::get("openai");

        // Sync provider_configs with ~/.thea/providers.json
        let providers = load_providers_from_disk();
        for p in &providers {
            settings.provider_configs.insert(
                p.id.clone(),
                ProviderConfig {
                    base_url: p.base_url.clone(),
                    api_key: p.api_key.clone(),
                },
            );
        }
        if !settings_path.exists() {
            if let Ok(json) = serde_json::to_string_pretty(&settings) {
                let _ = std::fs::write(&settings_path, json);
            }
        }
        Ok(settings)
    }

    /// Client entry point. `disabled_builtin_skills` and `seeded_mcp_presets` are
    /// server-owned: the copy on disk wins over whatever (possibly stale) snapshot
    /// the client sends. Server code that changes them calls `write_settings`.
    pub fn save_settings(&self, settings: &AppSettings) -> Result<()> {
        let mut merged = settings.clone();
        if let Some(disk) = std::fs::read_to_string(thea_home_dir().join("settings.json"))
            .ok()
            .and_then(|raw| serde_json::from_str::<AppSettings>(&raw).ok())
        {
            merged.disabled_builtin_skills = disk.disabled_builtin_skills;
            merged.seeded_mcp_presets = disk.seeded_mcp_presets;
        }
        self.write_settings(&merged)
    }

    /// Writes every field as given, including the server-owned ones.
    pub fn write_settings(&self, settings: &AppSettings) -> Result<()> {
        let settings_path = thea_home_dir().join("settings.json");
        let mut on_disk = settings.clone();
        // Empty means "nothing to migrate", not "delete": key removal goes through
        // save_provider, and settings.json never carries a key after migration.
        if !on_disk.openai_api_key.is_empty() {
            secrets::set("openai", &on_disk.openai_api_key)?;
        }
        on_disk.openai_api_key.clear();
        for cfg in on_disk.provider_configs.values_mut() {
            cfg.api_key.clear();
        }
        let pretty_json = serde_json::to_string_pretty(&on_disk)?;
        std::fs::write(&settings_path, &pretty_json)?;

        // Also update ~/.thea/providers.json with any updated base_url / api_key
        let mut providers = load_providers_from_disk();
        for (prov_id, cfg) in &settings.provider_configs {
            if let Some(entry) = providers.iter_mut().find(|p| &p.id == prov_id) {
                if !cfg.base_url.trim().is_empty() {
                    entry.base_url = cfg.base_url.trim().to_string();
                }
                entry.api_key = cfg.api_key.clone();
            }
        }
        let _ = save_providers_to_disk(&providers);
        Ok(())
    }

    pub fn list_projects(&self) -> Result<Vec<Project>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, name, root_path, instructions, persona_id, created_at, updated_at
             FROM projects ORDER BY updated_at DESC",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Project {
                id: row.get(0)?,
                name: row.get(1)?,
                root_path: row.get(2)?,
                instructions: row.get(3)?,
                persona_id: row.get(4)?,
                created_at: row.get(5)?,
                updated_at: row.get(6)?,
            })
        })?;
        Ok(rows.collect::<std::result::Result<Vec<_>, _>>()?)
    }

    /// Also resolves `chat:<chat-id>` to an in-memory workspace for a chat without a
    /// project, creating its folder. Unknown chats and chats in a project give `None`.
    pub fn get_project(&self, id: &str) -> Result<Option<Project>> {
        if let Some(chat_id) = id.strip_prefix(CHAT_WORKSPACE_PREFIX) {
            let Some(chat) = self.get_chat(chat_id)?.filter(|c| c.project_id.is_none()) else {
                return Ok(None);
            };
            let root = chat_workspace_dir(&chat.id);
            std::fs::create_dir_all(&root)
                .with_context(|| format!("Failed to create {}", root.display()))?;
            return Ok(Some(Project {
                id: id.to_string(),
                name: "Chat workspace".to_string(),
                root_path: root.to_string_lossy().into_owned(),
                instructions: String::new(),
                persona_id: String::new(),
                created_at: chat.created_at,
                updated_at: chat.updated_at,
            }));
        }
        let conn = self.conn.lock().unwrap();
        let proj = conn
            .query_row(
                "SELECT id, name, root_path, instructions, persona_id, created_at, updated_at
                 FROM projects WHERE id = ?1",
                params![id],
                |row| {
                    Ok(Project {
                        id: row.get(0)?,
                        name: row.get(1)?,
                        root_path: row.get(2)?,
                        instructions: row.get(3)?,
                        persona_id: row.get(4)?,
                        created_at: row.get(5)?,
                        updated_at: row.get(6)?,
                    })
                },
            )
            .optional()?;
        Ok(proj)
    }

    pub fn create_project(
        &self,
        name: &str,
        root_path: &str,
        instructions: &str,
        persona_id: &str,
    ) -> Result<Project> {
        let final_persona = self.resolve_default_persona_id(Some(persona_id));
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        let project = Project {
            id: Uuid::new_v4().to_string(),
            name: name.to_string(),
            root_path: root_path.to_string(),
            instructions: instructions.to_string(),
            persona_id: final_persona,
            created_at: now.clone(),
            updated_at: now,
        };
        conn.execute(
            "INSERT INTO projects (id, name, root_path, instructions, persona_id, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                project.id,
                project.name,
                project.root_path,
                project.instructions,
                project.persona_id,
                project.created_at,
                project.updated_at
            ],
        )?;
        Ok(project)
    }

    pub fn update_project(
        &self,
        id: &str,
        name: &str,
        instructions: &str,
        persona_id: &str,
    ) -> Result<Project> {
        let now = Utc::now().to_rfc3339();
        {
            let conn = self.conn.lock().unwrap();
            let changed = conn.execute(
                "UPDATE projects SET name = ?1, instructions = ?2, persona_id = ?3, updated_at = ?4 WHERE id = ?5",
                params![name, instructions, persona_id, now, id],
            )?;
            if changed == 0 {
                anyhow::bail!("Project not found");
            }
        }
        self.get_project(id)?
            .ok_or_else(|| anyhow::anyhow!("Project not found"))
    }

    pub fn delete_project(&self, id: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM projects WHERE id = ?1", params![id])?;
        Ok(())
    }

    pub fn list_knowledge_files(&self, project_id: &str) -> Result<Vec<KnowledgeFile>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, project_id, relative_path, created_at
             FROM project_knowledge WHERE project_id = ?1 ORDER BY relative_path ASC",
        )?;
        let rows = stmt.query_map(params![project_id], |row| {
            Ok(KnowledgeFile {
                id: row.get(0)?,
                project_id: row.get(1)?,
                relative_path: row.get(2)?,
                created_at: row.get(3)?,
            })
        })?;
        Ok(rows.collect::<std::result::Result<Vec<_>, _>>()?)
    }

    pub fn add_knowledge_file(
        &self,
        project_id: &str,
        relative_path: &str,
    ) -> Result<KnowledgeFile> {
        let conn = self.conn.lock().unwrap();
        let kf = KnowledgeFile {
            id: Uuid::new_v4().to_string(),
            project_id: project_id.to_string(),
            relative_path: relative_path.to_string(),
            created_at: Utc::now().to_rfc3339(),
        };
        conn.execute(
            "INSERT OR IGNORE INTO project_knowledge (id, project_id, relative_path, created_at)
             VALUES (?1, ?2, ?3, ?4)",
            params![kf.id, kf.project_id, kf.relative_path, kf.created_at],
        )?;
        Ok(kf)
    }

    pub fn remove_knowledge_file(&self, id: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM project_knowledge WHERE id = ?1", params![id])?;
        Ok(())
    }

    pub fn list_chats(&self, project_id: Option<&str>) -> Result<Vec<Chat>> {
        let conn = self.conn.lock().unwrap();
        let mut chats = Vec::new();
        if let Some(pid) = project_id {
            let mut stmt = conn.prepare(
                "SELECT id, project_id, title, provider, model, created_at, updated_at
                 FROM chats WHERE project_id = ?1 ORDER BY updated_at DESC",
            )?;
            let rows = stmt.query_map(params![pid], Self::map_chat)?;
            for r in rows {
                chats.push(r?);
            }
        } else {
            let mut stmt = conn.prepare(
                "SELECT id, project_id, title, provider, model, created_at, updated_at
                 FROM chats WHERE project_id IS NULL ORDER BY updated_at DESC",
            )?;
            let rows = stmt.query_map([], Self::map_chat)?;
            for r in rows {
                chats.push(r?);
            }
        }
        Ok(chats)
    }

    fn map_chat(row: &rusqlite::Row<'_>) -> rusqlite::Result<Chat> {
        Ok(Chat {
            id: row.get(0)?,
            project_id: row.get(1)?,
            title: row.get(2)?,
            provider: row.get(3)?,
            model: row.get(4)?,
            created_at: row.get(5)?,
            updated_at: row.get(6)?,
        })
    }

    pub fn get_chat(&self, id: &str) -> Result<Option<Chat>> {
        let conn = self.conn.lock().unwrap();
        Ok(conn
            .query_row(
                "SELECT id, project_id, title, provider, model, created_at, updated_at
                 FROM chats WHERE id = ?1",
                params![id],
                Self::map_chat,
            )
            .optional()?)
    }

    pub fn create_chat(
        &self,
        project_id: Option<&str>,
        title: &str,
        provider: &str,
        model: &str,
    ) -> Result<Chat> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        let chat = Chat {
            id: Uuid::new_v4().to_string(),
            project_id: project_id.map(|s| s.to_string()),
            title: title.to_string(),
            provider: provider.to_string(),
            model: model.to_string(),
            created_at: now.clone(),
            updated_at: now,
        };
        conn.execute(
            "INSERT INTO chats (id, project_id, title, provider, model, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                chat.id,
                chat.project_id,
                chat.title,
                chat.provider,
                chat.model,
                chat.created_at,
                chat.updated_at
            ],
        )?;
        Ok(chat)
    }

    pub fn update_chat_title(&self, id: &str, title: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        conn.execute(
            "UPDATE chats SET title = ?1, updated_at = ?2 WHERE id = ?3",
            params![title, now, id],
        )?;
        Ok(())
    }

    /// The chat's project, or its scratch workspace when it has none.
    pub fn workspace_for_chat(&self, chat: &Chat) -> Result<Option<Project>> {
        match &chat.project_id {
            Some(pid) => self.get_project(pid),
            None => self.get_project(&format!("{CHAT_WORKSPACE_PREFIX}{}", chat.id)),
        }
    }

    pub fn delete_chat(&self, id: &str) -> Result<()> {
        // Only a chat that exists has a folder; never build a path from an unknown id.
        // Remove the folder first so a failure keeps the row and a retry can finish.
        if self.get_chat(id)?.is_some() {
            match std::fs::remove_dir_all(chat_workspace_dir(id)) {
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => return Err(e.into()),
                _ => {}
            }
        }
        self.conn
            .lock()
            .unwrap()
            .execute("DELETE FROM chats WHERE id = ?1", params![id])?;
        Ok(())
    }

    pub fn list_messages(&self, chat_id: &str) -> Result<Vec<StoredMessage>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, chat_id, role, content, tool_calls_json, tool_call_id, tool_name, model_message_json, created_at
             FROM messages WHERE chat_id = ?1 ORDER BY created_at ASC, rowid ASC",
        )?;
        let rows = stmt.query_map(params![chat_id], |row| {
            Ok(StoredMessage {
                id: row.get(0)?,
                chat_id: row.get(1)?,
                role: row.get(2)?,
                content: row.get(3)?,
                tool_calls_json: row.get(4)?,
                tool_call_id: row.get(5)?,
                tool_name: row.get(6)?,
                model_message_json: row.get(7)?,
                created_at: row.get(8)?,
            })
        })?;
        Ok(rows.collect::<std::result::Result<Vec<_>, _>>()?)
    }

    pub fn add_message(
        &self,
        chat_id: &str,
        role: &str,
        content: &str,
        tool_calls_json: Option<&str>,
        tool_call_id: Option<&str>,
        tool_name: Option<&str>,
        model_message_json: Option<&str>,
    ) -> Result<StoredMessage> {
        let conn = self.conn.lock().unwrap();
        let now = Utc::now().to_rfc3339();
        let msg = StoredMessage {
            id: Uuid::new_v4().to_string(),
            chat_id: chat_id.to_string(),
            role: role.to_string(),
            content: content.to_string(),
            tool_calls_json: tool_calls_json.map(|s| s.to_string()),
            tool_call_id: tool_call_id.map(|s| s.to_string()),
            tool_name: tool_name.map(|s| s.to_string()),
            model_message_json: model_message_json.map(|s| s.to_string()),
            created_at: now.clone(),
        };
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, tool_calls_json, tool_call_id, tool_name, model_message_json, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                msg.id,
                msg.chat_id,
                msg.role,
                msg.content,
                msg.tool_calls_json,
                msg.tool_call_id,
                msg.tool_name,
                msg.model_message_json,
                msg.created_at
            ],
        )?;
        conn.execute(
            "UPDATE chats SET updated_at = ?1 WHERE id = ?2",
            params![now, chat_id],
        )?;
        Ok(msg)
    }

    pub fn is_skill_enabled(&self, skill_name: &str) -> Result<bool> {
        let conn = self.conn.lock().unwrap();
        let enabled: Option<i64> = conn
            .query_row(
                "SELECT enabled FROM skill_states WHERE skill_name = ?1",
                params![skill_name],
                |r| r.get(0),
            )
            .optional()?;
        Ok(enabled.unwrap_or(1) != 0)
    }

    pub fn set_skill_enabled(&self, skill_name: &str, enabled: bool) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO skill_states (skill_name, enabled) VALUES (?1, ?2)
             ON CONFLICT(skill_name) DO UPDATE SET enabled = excluded.enabled",
            params![skill_name, if enabled { 1 } else { 0 }],
        )?;
        Ok(())
    }

    pub fn list_mcp_servers(&self) -> Result<Vec<McpServerConfig>> {
        let mcp_file = thea_home_dir().join("mcp.json");
        if let Ok(raw) = std::fs::read_to_string(&mcp_file) {
            if let Ok(list) = serde_json::from_str::<Vec<McpServerConfig>>(&raw) {
                return Ok(list);
            }
        }
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, name, command, args_json, env_json, enabled, auto_approve FROM mcp_servers ORDER BY name ASC",
        )?;
        let rows = stmt.query_map([], |row| {
            let args_str: String = row.get(3)?;
            let env_str: String = row.get(4)?;
            let enabled_int: i64 = row.get(5)?;
            let auto_int: i64 = row.get(6)?;
            Ok(McpServerConfig {
                id: row.get(0)?,
                name: row.get(1)?,
                command: row.get(2)?,
                args: serde_json::from_str(&args_str).unwrap_or_default(),
                env: serde_json::from_str(&env_str).unwrap_or_default(),
                enabled: enabled_int != 0,
                auto_approve: auto_int != 0,
            })
        })?;
        let servers = rows.collect::<std::result::Result<Vec<_>, _>>()?;
        if let Ok(json) = serde_json::to_string_pretty(&servers) {
            let _ = std::fs::write(&mcp_file, json);
        }
        Ok(servers)
    }

    pub fn save_mcp_server(&self, server: &McpServerConfig) -> Result<McpServerConfig> {
        let id = if server.id.is_empty() {
            Uuid::new_v4().to_string()
        } else {
            server.id.clone()
        };
        let saved = McpServerConfig {
            id: id.clone(),
            ..server.clone()
        };
        {
            let conn = self.conn.lock().unwrap();
            let args_json = serde_json::to_string(&server.args)?;
            let env_json = serde_json::to_string(&server.env)?;
            conn.execute(
                "INSERT INTO mcp_servers (id, name, command, args_json, env_json, enabled, auto_approve)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
                 ON CONFLICT(id) DO UPDATE SET
                   name = excluded.name,
                   command = excluded.command,
                   args_json = excluded.args_json,
                   env_json = excluded.env_json,
                   enabled = excluded.enabled,
                   auto_approve = excluded.auto_approve",
                params![
                    id,
                    server.name,
                    server.command,
                    args_json,
                    env_json,
                    if server.enabled { 1 } else { 0 },
                    if server.auto_approve { 1 } else { 0 }
                ],
            )?;
        }
        let mcp_file = thea_home_dir().join("mcp.json");
        let mut servers: Vec<McpServerConfig> = std::fs::read_to_string(&mcp_file)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default();
        if let Some(ex) = servers.iter_mut().find(|s| s.id == saved.id) {
            *ex = saved.clone();
        } else {
            servers.push(saved.clone());
        }
        let _ = std::fs::write(&mcp_file, serde_json::to_string_pretty(&servers)?);
        Ok(saved)
    }

    /// Seeds each preset once: ids already present or already recorded in
    /// `seeded_mcp_presets` are skipped, so a deleted preset stays deleted.
    pub fn ensure_mcp_presets(&self) -> Result<()> {
        let existing = self.list_mcp_servers()?;
        let mut settings = self.get_settings()?;
        let mut changed = false;
        for p in mcp_presets() {
            if existing.iter().any(|s| s.id == p.id) || settings.seeded_mcp_presets.contains(&p.id)
            {
                continue;
            }
            self.save_mcp_server(&p)?;
            settings.seeded_mcp_presets.push(p.id);
            changed = true;
        }
        if changed {
            self.write_settings(&settings)?;
        }
        Ok(())
    }

    pub fn delete_mcp_server(&self, id: &str) -> Result<()> {
        {
            let conn = self.conn.lock().unwrap();
            conn.execute("DELETE FROM mcp_servers WHERE id = ?1", params![id])?;
        }
        let mcp_file = thea_home_dir().join("mcp.json");
        if let Ok(raw) = std::fs::read_to_string(&mcp_file) {
            if let Ok(mut servers) = serde_json::from_str::<Vec<McpServerConfig>>(&raw) {
                servers.retain(|s| s.id != id);
                let _ = std::fs::write(&mcp_file, serde_json::to_string_pretty(&servers)?);
            }
        }
        Ok(())
    }
}

#[cfg(test)]
pub fn test_env_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
    LOCK.lock().unwrap_or_else(|e| e.into_inner())
}

#[cfg(test)]
mod persona_tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn reseed_overwrites_builtin_prompt_and_keeps_custom() {
        let _g = test_env_lock();
        let dir = tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        db.list_personas().unwrap();
        db.save_custom_persona(Some("mine"), "Mine", "t", "p", &[], &[], &[])
            .unwrap();
        {
            let conn = db.conn.lock().unwrap();
            conn.execute(
                "UPDATE personas SET system_prompt='old' WHERE id='research-assistant'",
                [],
            )
            .unwrap();
        }
        db.reseed_builtin_personas().unwrap();
        let ra = db.get_persona("research-assistant").unwrap();
        assert!(ra
            .system_prompt
            .starts_with("You are Thea in Research Assistant mode."));
        assert!(!ra.native_thinking);
        assert_eq!(ra.max_steps, 0, "0 = step cap from the model tier");
        assert!(ra.tool_ids.contains(&"add_source".to_string()));
        // A changed tool list reaches an existing database with the reseed.
        assert!(ra.tool_ids.contains(&"add_note".to_string()));
        assert!(!ra.tool_ids.contains(&"check_style".to_string()));
        assert!(db.get_persona("mine").unwrap().id == "mine");
    }

    #[test]
    fn builtin_personas_reject_edit_and_delete() {
        let _g = test_env_lock();
        let dir = tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        assert!(db
            .save_custom_persona(Some("research-assistant"), "x", "x", "x", &[], &[], &[])
            .is_err());
        assert!(db.delete_custom_persona("research-assistant").is_err());
    }
}

#[cfg(test)]
mod save_settings_tests {
    use super::*;

    #[test]
    fn save_settings_under_thea_home_keeps_keys_off_disk() {
        let _g = test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        db.save_settings(&AppSettings::default()).unwrap();
        let raw = std::fs::read_to_string(dir.path().join("settings.json")).unwrap();
        let back: AppSettings = serde_json::from_str(&raw).unwrap();
        assert!(back.openai_api_key.is_empty());
    }

    #[test]
    fn provider_defaults_round_trip_under_thea_home_without_os_keychain() {
        let _g = test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let providers = load_providers_from_disk();
        assert!(!providers.is_empty());
        save_providers_to_disk(&providers).unwrap();
        assert!(dir.path().join("providers.json").exists());
    }

    #[test]
    fn client_save_cannot_drop_server_owned_fields() {
        let _g = test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        let mut s = db.get_settings().unwrap();
        s.disabled_builtin_skills = vec!["some-builtin".into()];
        s.seeded_mcp_presets = vec!["playwright".into()];
        db.write_settings(&s).unwrap();
        db.save_settings(&AppSettings::default()).unwrap();
        let back = db.get_settings().unwrap();
        assert_eq!(
            back.disabled_builtin_skills,
            vec!["some-builtin".to_string()]
        );
        assert_eq!(back.seeded_mcp_presets, vec!["playwright".to_string()]);
    }
}

#[cfg(test)]
mod mcp_preset_tests {
    use super::*;

    #[test]
    fn presets_are_added_once_and_deletion_sticks() {
        let _g = test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        db.ensure_mcp_presets().unwrap();
        let s = db.list_mcp_servers().unwrap();
        assert!(s
            .iter()
            .any(|x| x.id == "sequential-thinking" && x.enabled && x.auto_approve));
        assert!(s
            .iter()
            .any(|x| x.id == "playwright" && x.enabled && !x.auto_approve));
        db.delete_mcp_server("playwright").unwrap();
        db.ensure_mcp_presets().unwrap();
        assert!(!db
            .list_mcp_servers()
            .unwrap()
            .iter()
            .any(|x| x.id == "playwright"));
    }
}

#[cfg(test)]
mod chat_workspace_tests {
    use super::*;
    use std::path::PathBuf;

    fn setup() -> (
        std::sync::MutexGuard<'static, ()>,
        tempfile::TempDir,
        Database,
    ) {
        let g = test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        (g, dir, db)
    }

    #[test]
    fn chat_without_project_gets_scratch_workspace() {
        let (_g, dir, db) = setup();
        let chat = db.create_chat(None, "t", "ollama", "m").unwrap();
        let ws = db.workspace_for_chat(&chat).unwrap().unwrap();
        assert_eq!(ws.id, format!("chat:{}", chat.id));
        assert_eq!(
            PathBuf::from(&ws.root_path),
            dir.path().join("chats").join(&chat.id)
        );
        assert!(PathBuf::from(&ws.root_path).is_dir());
        assert_eq!(ws.persona_id, "", "a chat without a project has no persona");
    }

    #[test]
    fn chat_workspace_id_only_resolves_for_projectless_chats() {
        let (_g, dir, db) = setup();
        assert!(db.get_project("chat:no-such-chat").unwrap().is_none());
        assert!(db.get_project("chat:../..").unwrap().is_none());
        let p = db
            .create_project("p", dir.path().to_str().unwrap(), "", "personal-assistant")
            .unwrap();
        let c = db.create_chat(Some(&p.id), "t", "ollama", "m").unwrap();
        assert!(db.get_project(&format!("chat:{}", c.id)).unwrap().is_none());
        assert_eq!(db.workspace_for_chat(&c).unwrap().unwrap().id, p.id);
    }

    #[test]
    fn update_project_on_a_chat_workspace_is_an_error() {
        let (_g, _dir, db) = setup();
        let chat = db.create_chat(None, "t", "ollama", "m").unwrap();
        let id = format!("chat:{}", chat.id);
        assert!(db
            .update_project(&id, "x", "", "personal-assistant")
            .is_err());
    }

    #[cfg(unix)]
    #[test]
    fn failed_folder_removal_keeps_the_chat() {
        use std::os::unix::fs::PermissionsExt;
        let (_g, dir, db) = setup();
        let chat = db.create_chat(None, "t", "ollama", "m").unwrap();
        let root = PathBuf::from(db.workspace_for_chat(&chat).unwrap().unwrap().root_path);
        std::fs::write(root.join("a.md"), "x").unwrap();
        let chats = dir.path().join("chats");
        std::fs::set_permissions(&chats, std::fs::Permissions::from_mode(0o500)).unwrap();
        let res = db.delete_chat(&chat.id);
        std::fs::set_permissions(&chats, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert!(res.is_err());
        assert!(db.get_chat(&chat.id).unwrap().is_some());
        db.delete_chat(&chat.id).unwrap();
        assert!(!root.exists());
    }

    #[test]
    fn delete_chat_removes_its_workspace_only() {
        let (_g, dir, db) = setup();
        let chat = db.create_chat(None, "t", "ollama", "m").unwrap();
        let root = PathBuf::from(db.workspace_for_chat(&chat).unwrap().unwrap().root_path);
        std::fs::write(root.join("TASK.md"), "x").unwrap();
        let sentinel = dir.path().join("keep.txt");
        std::fs::write(&sentinel, "x").unwrap();
        db.delete_chat("..").unwrap();
        db.delete_chat("").unwrap();
        assert!(sentinel.exists());
        db.delete_chat(&chat.id).unwrap();
        assert!(!root.exists());
    }
}
