//! The Python agent sidecar: spawn, JSON-lines relay, restart, pending calls.
//! The serde types mirror `agent/src/thea_agent/protocol.py`; the fixtures in
//! `agent/tests/fixtures/protocol/` are round-tripped on both sides.

use crate::db::{thea_home_dir, Database, McpServerConfig};
use crate::lessons::{self, Lesson};
use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::Path;
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::oneshot;

const STOPPED: &str = "The agent process stopped.";
/// Longer than Python's own `EOF_GRACE`, so a clean exit is the normal case.
const SHUTDOWN_GRACE: std::time::Duration = std::time::Duration::from_secs(3);

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WirePersona {
    pub id: String,
    pub name: String,
    pub tagline: String,
    pub system_prompt: String,
    pub tool_ids: Vec<String>,
    pub skill_ids: Vec<String>,
    pub mcp_server_ids: Vec<String>,
    pub builtin: bool,
    pub native_thinking: bool,
    pub max_steps: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Provider {
    pub protocol: String,
    pub base_url: String,
    pub api_key: String,
    pub model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Workspace {
    pub id: String,
    pub name: String,
    pub root_path: String,
    pub instructions: String,
    pub is_chat: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StoredRow {
    pub role: String,
    pub content: String,
    pub tool_calls_json: Option<String>,
    pub tool_call_id: Option<String>,
    pub tool_name: Option<String>,
    pub model_message_json: Option<String>,
}

impl From<crate::db::StoredMessage> for StoredRow {
    fn from(m: crate::db::StoredMessage) -> Self {
        StoredRow {
            role: m.role,
            content: m.content,
            tool_calls_json: m.tool_calls_json,
            tool_call_id: m.tool_call_id,
            tool_name: m.tool_name,
            model_message_json: m.model_message_json,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TurnRequest {
    pub chat_id: String,
    /// None for a chat without a project: a plain chat.
    pub persona: Option<WirePersona>,
    pub provider: Provider,
    pub small_model: Option<bool>,
    pub workspace: Option<Workspace>,
    pub knowledge_files: Vec<String>,
    pub skill_dirs: Vec<String>,
    pub skills: Vec<String>,
    pub mcp_servers: Vec<McpServerConfig>,
    pub settings: Value,
    pub lessons: Vec<String>,
    pub history: Vec<StoredRow>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalDecision {
    Approve,
    AlwaysAllowProject,
    Reject,
}

/// One line either way.
#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum Line {
    Turn(Box<TurnRequest>),
    Approval {
        request_id: String,
        decision: ApprovalDecision,
    },
    Cancel {
        chat_id: String,
    },
    Call {
        id: String,
        method: String,
        params: Value,
    },
    Event {
        name: String,
        payload: Value,
    },
    Result {
        id: String,
        ok: bool,
        #[serde(default)]
        value: Value,
        #[serde(default)]
        error: Option<String>,
    },
}

/// Same shape as Python's `test_mcp_server` rows, returned to the MCP settings pane.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpRemoteTool {
    pub server_id: String,
    pub server_name: String,
    pub tool_name: String,
    pub qualified_name: String,
    pub description: String,
    pub input_schema: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelInfo {
    pub id: String,
    pub name: String,
    pub provider: String,
    pub size_bytes: Option<u64>,
    pub parameter_size: Option<String>,
    pub supports_tools: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelCapabilities {
    pub supports_tools: bool,
    pub supports_thinking: bool,
    pub context_length: Option<u64>,
    #[serde(default)]
    pub parameter_size: Option<String>,
}

#[derive(Deserialize)]
struct MessageRow {
    chat_id: String,
    role: String,
    content: String,
    tool_calls_json: Option<String>,
    tool_call_id: Option<String>,
    tool_name: Option<String>,
    model_message_json: Option<String>,
}

#[derive(Deserialize)]
struct LessonEvent {
    persona_id: String,
    signal: String,
    text: String,
}

pub type EmitFn = Arc<dyn Fn(&str, Value) + Send + Sync>;
type CommandFn = Box<dyn Fn() -> Command + Send + Sync>;

/// What one process owes: running turns per chat and unanswered calls. Each process has its
/// own, so a dead process only finishes what was sent to it.
#[derive(Default)]
struct Tracked {
    dead: bool,
    running: HashMap<String, usize>,
    pending: HashMap<String, oneshot::Sender<Result<Value, String>>>,
}

type State = Arc<Mutex<Tracked>>;

struct Proc {
    stdin: ChildStdin,
    state: State,
    child: Child,
}

pub struct Sidecar {
    db: Arc<Database>,
    emit: EmitFn,
    command: CommandFn,
    proc: tokio::sync::Mutex<Option<Proc>>,
}

/// `uv run --project <repo>/agent python -m thea_agent`.
pub fn dev_command() -> Command {
    let project = Path::new(env!("CARGO_MANIFEST_DIR")).join("../agent");
    let mut c = Command::new("uv");
    c.arg("run")
        .arg("--project")
        .arg(project)
        .args(["python", "-m", "thea_agent"])
        .env_remove("VIRTUAL_ENV");
    c
}

fn bundled_command(resource_dir: &Path) -> Command {
    let python = if cfg!(windows) {
        resource_dir.join("python").join("python.exe")
    } else {
        resource_dir.join("python").join("bin").join("python3")
    };
    let mut c = Command::new(python);
    c.args(["-m", "thea_agent"])
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env("PYTHONNOUSERSITE", "1");
    c
}

impl Sidecar {
    pub fn new(db: Arc<Database>, emit: EmitFn, command: CommandFn) -> Arc<Self> {
        Arc::new(Sidecar {
            db,
            emit,
            command,
            proc: tokio::sync::Mutex::new(None),
        })
    }

    /// The app's sidecar: the dev project in debug builds, the bundled Python in release.
    /// The process starts on the first request.
    pub fn spawn(app: tauri::AppHandle, db: Arc<Database>) -> Result<Arc<Self>> {
        use tauri::{Emitter, Manager};
        let command: CommandFn = if cfg!(debug_assertions) {
            Box::new(dev_command)
        } else {
            let dir = app.path().resource_dir()?;
            Box::new(move || bundled_command(&dir))
        };
        let emit: EmitFn = Arc::new(move |name: &str, payload: Value| {
            let _ = app.emit(name, payload);
        });
        Ok(Self::new(db, emit, command))
    }

    fn start(&self) -> Result<Proc> {
        let logs = thea_home_dir().join("logs");
        std::fs::create_dir_all(&logs)?;
        let log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(logs.join("agent.log"))?;
        let mut cmd = (self.command)();
        cmd.env("PYTHONUTF8", "1")
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(log)
            .kill_on_drop(true);
        #[cfg(windows)]
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        let mut child = cmd
            .spawn()
            .map_err(|e| anyhow!("Could not start the agent process: {e}"))?;
        let stdin = child.stdin.take().ok_or_else(|| anyhow!("no stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("no stdout"))?;
        let state = State::default();
        tokio::spawn(read_loop(
            BufReader::new(stdout),
            state.clone(),
            self.db.clone(),
            self.emit.clone(),
        ));
        Ok(Proc {
            stdin,
            state,
            child,
        })
    }

    /// Writes one line, starting the process first when `respawn` and it is not running.
    /// `track` records what the line owes under the same lock the reader drains at EOF.
    /// Returns false when not running and `respawn` is off (nothing to cancel or approve).
    async fn send(
        &self,
        line: &Line,
        respawn: bool,
        track: impl FnOnce(&mut Tracked),
    ) -> Result<bool> {
        let mut guard = self.proc.lock().await;
        let mut track = Some(track);
        loop {
            if let Some(p) = guard.as_ref() {
                let mut t = p.state.lock().unwrap();
                if !t.dead {
                    if let Some(f) = track.take() {
                        f(&mut t);
                    }
                    break;
                }
            }
            if !respawn {
                return Ok(false);
            }
            *guard = Some(self.start()?);
        }
        let p = guard.as_mut().expect("started above");
        let mut buf = serde_json::to_vec(line)?;
        buf.push(b'\n');
        // A write fails only when the process died; its reader reports that at EOF.
        if let Err(e) = async {
            p.stdin.write_all(&buf).await?;
            p.stdin.flush().await
        }
        .await
        {
            eprintln!("agent write failed: {e}");
        }
        Ok(true)
    }

    /// On app exit: closes stdin so Python cancels its turns and exits, then kills the
    /// process if it is still running after the grace period.
    // ponytail: in dev the kill reaches `uv`, not its Python child; the stdin EOF is what
    // stops Python there. Kill the process group if that ever proves insufficient.
    pub async fn shutdown(&self) {
        self.shutdown_within(SHUTDOWN_GRACE).await
    }

    async fn shutdown_within(&self, grace: std::time::Duration) {
        let Some(Proc {
            stdin, mut child, ..
        }) = self.proc.lock().await.take()
        else {
            return;
        };
        drop(stdin);
        if tokio::time::timeout(grace, child.wait()).await.is_err() {
            let _ = child.kill().await;
        }
    }

    pub async fn send_turn(&self, req: TurnRequest) -> Result<()> {
        let chat_id = req.chat_id.clone();
        self.send(&Line::Turn(Box::new(req)), true, |t| {
            *t.running.entry(chat_id).or_default() += 1;
        })
        .await
        .map(drop)
    }

    pub async fn send_approval(
        &self,
        request_id: String,
        decision: ApprovalDecision,
    ) -> Result<bool> {
        self.send(
            &Line::Approval {
                request_id,
                decision,
            },
            false,
            |_| {},
        )
        .await
    }

    pub async fn send_cancel(&self, chat_id: String) -> Result<()> {
        self.send(&Line::Cancel { chat_id }, false, |_| {})
            .await
            .map(drop)
    }

    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        let id = uuid::Uuid::new_v4().to_string();
        let (tx, rx) = oneshot::channel();
        let line = Line::Call {
            id: id.clone(),
            method: method.to_string(),
            params,
        };
        self.send(&line, true, |t| {
            t.pending.insert(id, tx);
        })
        .await?;
        rx.await
            .map_err(|_| anyhow!(STOPPED))?
            .map_err(|e| anyhow!(e))
    }
}

/// Reads the sidecar's stdout until EOF: stores `message` and `lesson`, relays the rest,
/// answers calls. At EOF finishes every running chat with an error and fails every call.
async fn read_loop(
    reader: impl AsyncBufRead + Unpin,
    state: State,
    db: Arc<Database>,
    emit: EmitFn,
) {
    let mut lines = reader.lines();
    while let Ok(Some(raw)) = lines.next_line().await {
        if raw.trim().is_empty() {
            continue;
        }
        match serde_json::from_str::<Line>(&raw) {
            Ok(Line::Event { name, payload }) => {
                if let Err(e) = handle_event(&db, &emit, &state, &name, payload) {
                    eprintln!("agent event {name} failed: {e}");
                }
            }
            Ok(Line::Result {
                id,
                ok,
                value,
                error,
            }) => {
                if let Some(tx) = state.lock().unwrap().pending.remove(&id) {
                    let _ = tx.send(if ok {
                        Ok(value)
                    } else {
                        Err(error.unwrap_or_default())
                    });
                }
            }
            _ => eprintln!("agent line ignored: {raw}"),
        }
    }
    let (running, pending) = {
        let mut t = state.lock().unwrap();
        t.dead = true;
        (
            std::mem::take(&mut t.running),
            std::mem::take(&mut t.pending),
        )
    };
    for chat_id in running.into_keys() {
        emit(
            "chat:finished",
            json!({"chat_id": chat_id, "error": STOPPED}),
        );
    }
    for (_, tx) in pending {
        let _ = tx.send(Err(STOPPED.to_string()));
    }
}

fn handle_event(
    db: &Database,
    emit: &EmitFn,
    state: &State,
    name: &str,
    payload: Value,
) -> Result<()> {
    match name {
        "message" => {
            let m: MessageRow = serde_json::from_value(payload)?;
            db.add_message(
                &m.chat_id,
                &m.role,
                &m.content,
                m.tool_calls_json.as_deref(),
                m.tool_call_id.as_deref(),
                m.tool_name.as_deref(),
                m.model_message_json.as_deref(),
            )?;
        }
        "lesson" => {
            let l: LessonEvent = serde_json::from_value(payload)?;
            lessons::append_lesson(
                &l.persona_id,
                Lesson {
                    date: chrono::Local::now().format("%Y-%m-%d").to_string(),
                    signal: l.signal,
                    text: l.text,
                },
            )?;
        }
        _ => {
            if name == "chat:finished" {
                if let Some(id) = payload.get("chat_id").and_then(Value::as_str) {
                    let mut t = state.lock().unwrap();
                    if let Some(n) = t.running.get_mut(id) {
                        *n -= 1;
                        if *n == 0 {
                            t.running.remove(id);
                        }
                    }
                }
            }
            emit(name, payload);
        }
    }
    Ok(())
}

#[cfg(test)]
// The env lock only serializes THEA_HOME between tests; each test runs on one thread.
#[allow(clippy::await_holding_lock)]
mod tests {
    use super::*;
    use std::time::Duration;

    type Log = Arc<Mutex<Vec<(String, Value)>>>;

    fn recorder() -> (EmitFn, Log) {
        let log: Log = Arc::default();
        let l = log.clone();
        (
            Arc::new(move |name: &str, payload: Value| {
                l.lock().unwrap().push((name.to_string(), payload))
            }),
            log,
        )
    }

    fn fixture(name: &str) -> String {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../agent/tests/fixtures/protocol");
        std::fs::read_to_string(dir.join(name)).unwrap()
    }

    fn test_db() -> (tempfile::TempDir, Arc<Database>) {
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        (dir, Arc::new(db))
    }

    async fn wait_for(log: &Log, name: &str) -> Vec<Value> {
        for _ in 0..250 {
            let hits: Vec<Value> = log
                .lock()
                .unwrap()
                .iter()
                .filter(|(n, _)| n == name)
                .map(|(_, p)| p.clone())
                .collect();
            if !hits.is_empty() {
                return hits;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        panic!("no {name} event");
    }

    #[test]
    fn protocol_fixtures_deserialize() {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../agent/tests/fixtures/protocol");
        let mut n = 0;
        for entry in std::fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            let raw: Value =
                serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
            let line: Line = serde_json::from_value(raw.clone())
                .unwrap_or_else(|e| panic!("{}: {e}", path.display()));
            assert_eq!(
                serde_json::to_value(&line).unwrap(),
                raw,
                "{}",
                path.display()
            );
            n += 1;
        }
        assert_eq!(n, 7);
    }

    #[tokio::test]
    async fn routes_message_events_to_db() {
        let _g = crate::db::test_env_lock();
        let (_dir, db) = test_db();
        let chat = db.create_chat(None, "t", "ollama", "m").unwrap();
        let line = json!({"type": "event", "name": "message", "payload": {
            "chat_id": chat.id, "role": "assistant", "content": "hi",
            "tool_calls_json": null, "tool_call_id": null, "tool_name": null,
            "model_message_json": "[{}]"}});
        let (emit, log) = recorder();
        read_loop(
            format!("{line}\n").as_bytes(),
            Arc::default(),
            db.clone(),
            emit,
        )
        .await;
        let rows = db.list_messages(&chat.id).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].content, "hi");
        assert_eq!(rows[0].model_message_json.as_deref(), Some("[{}]"));
        assert!(log.lock().unwrap().iter().all(|(n, _)| n != "message"));
    }

    #[tokio::test]
    async fn relays_ui_events() {
        let _g = crate::db::test_env_lock();
        let (_dir, db) = test_db();
        let (emit, log) = recorder();
        read_loop(
            fixture("event.json").replace('\n', " ").as_bytes(),
            Arc::default(),
            db,
            emit,
        )
        .await;
        let log = log.lock().unwrap();
        assert_eq!(
            log[0],
            (
                "chat:delta".into(),
                json!({"chat_id": "c1", "delta": "Hel"})
            )
        );
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn eof_finishes_running_chats() {
        let _g = crate::db::test_env_lock();
        let (_dir, db) = test_db();
        let (emit, log) = recorder();
        let spawns = Arc::new(Mutex::new(0));
        let s = spawns.clone();
        // A stand-in that reads one line and exits, like a crash mid-turn.
        let sidecar = Sidecar::new(
            db,
            emit,
            Box::new(move || {
                *s.lock().unwrap() += 1;
                let mut c = Command::new("sh");
                c.args(["-c", "head -n 1 >/dev/null"]);
                c
            }),
        );
        let req: TurnRequest = match serde_json::from_str(&fixture("turn.json")).unwrap() {
            Line::Turn(t) => *t,
            _ => unreachable!(),
        };
        sidecar.send_turn(req.clone()).await.unwrap();
        let finished = wait_for(&log, "chat:finished").await;
        assert_eq!(
            finished,
            vec![json!({"chat_id": "c1", "error": "The agent process stopped."})]
        );
        // A pending call fails instead of hanging.
        let err = sidecar.call("ping", json!({})).await.unwrap_err();
        assert!(err.to_string().contains("stopped"), "{err}");
        // The next send respawns.
        sidecar.send_turn(req).await.unwrap();
        for _ in 0..250 {
            if wait_for(&log, "chat:finished").await.len() == 2 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        assert_eq!(wait_for(&log, "chat:finished").await.len(), 2);
        assert_eq!(*spawns.lock().unwrap(), 3);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn replaced_turn_then_eof_finishes_once() {
        let _g = crate::db::test_env_lock();
        let (_dir, db) = test_db();
        let (emit, log) = recorder();
        // Two turns for one chat; the replaced one finishes (null), then the process dies.
        let sidecar = Sidecar::new(
            db,
            emit,
            Box::new(|| {
                let mut c = Command::new("sh");
                c.args([
                    "-c",
                    r#"head -n 2 >/dev/null; echo '{"type":"event","name":"chat:finished","payload":{"chat_id":"c1","error":null}}'"#,
                ]);
                c
            }),
        );
        let req: TurnRequest = match serde_json::from_str(&fixture("turn.json")).unwrap() {
            Line::Turn(t) => *t,
            _ => unreachable!(),
        };
        sidecar.send_turn(req.clone()).await.unwrap();
        sidecar.send_turn(req).await.unwrap();
        for _ in 0..250 {
            if wait_for(&log, "chat:finished").await.len() >= 2 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
        tokio::time::sleep(Duration::from_millis(100)).await; // no third one arrives
        assert_eq!(
            wait_for(&log, "chat:finished").await,
            vec![
                json!({"chat_id": "c1", "error": null}),
                json!({"chat_id": "c1", "error": "The agent process stopped."}),
            ]
        );
    }

    #[test]
    fn bundled_python_ignores_pythonpath() {
        let c = bundled_command(Path::new("/r"));
        let envs: Vec<_> = c.as_std().get_envs().collect();
        assert!(envs.contains(&(std::ffi::OsStr::new("PYTHONPATH"), None)));
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn shutdown_kills_a_child_that_ignores_eof() {
        let _g = crate::db::test_env_lock();
        let (_dir, db) = test_db();
        let (emit, _log) = recorder();
        let sidecar = Sidecar::new(
            db,
            emit,
            Box::new(|| {
                let mut c = Command::new("sh");
                c.args(["-c", "trap '' TERM; while :; do sleep 1; done"]);
                c
            }),
        );
        let req: TurnRequest = match serde_json::from_str(&fixture("turn.json")).unwrap() {
            Line::Turn(t) => *t,
            _ => unreachable!(),
        };
        sidecar.send_turn(req).await.unwrap();
        let pid = sidecar
            .proc
            .lock()
            .await
            .as_ref()
            .unwrap()
            .child
            .id()
            .unwrap();
        let started = std::time::Instant::now();
        sidecar.shutdown_within(Duration::from_millis(200)).await;
        assert!(started.elapsed() < Duration::from_secs(2));
        let alive = std::process::Command::new("kill")
            .args(["-0", &pid.to_string()])
            .status()
            .unwrap()
            .success();
        assert!(!alive, "child {pid} still running");
    }

    /// Spawns the real dev sidecar (needs uv): `cargo test -- --ignored dev_sidecar_answers_ping`.
    #[tokio::test]
    #[ignore]
    async fn dev_sidecar_answers_ping() {
        let _g = crate::db::test_env_lock();
        let (_dir, db) = test_db();
        let (emit, _log) = recorder();
        let sidecar = Sidecar::new(db, emit, Box::new(dev_command));
        let pong = tokio::time::timeout(Duration::from_secs(60), sidecar.call("ping", json!({})))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(pong, json!("pong"));
        let caps = sidecar
            .call(
                "model_capabilities",
                json!({"provider": {"protocol": "openai", "base_url": "http://127.0.0.1:9",
                    "api_key": "", "model": "m"}}),
            )
            .await
            .unwrap();
        let caps: ModelCapabilities = serde_json::from_value(caps).unwrap();
        assert!(caps.supports_tools);
        let err = sidecar.call("nope", json!({})).await.unwrap_err();
        assert!(err.to_string().contains("unknown method"), "{err}");
        // stdin EOF alone stops uv and Python; no kill needed.
        let started = std::time::Instant::now();
        sidecar.shutdown().await;
        assert!(
            started.elapsed() < SHUTDOWN_GRACE,
            "{:?}",
            started.elapsed()
        );
    }
}
