// ponytail: Tauri command/agent fns take many plain args; bundle into structs if they keep growing.
#![allow(clippy::too_many_arguments)]

pub mod db;
pub mod files;
pub mod lessons;
pub mod lmstudio;
pub mod print;
pub mod sidecar;
pub mod skills;
pub mod templates;
pub mod turn_request;

use db::{
    thea_home_dir, AppSettings, Chat, Database, KnowledgeFile, McpServerConfig, Persona, Project,
    ProviderEntry, StoredMessage,
};
use files::FileNode;
use serde_json::{json, Value};
use sidecar::{ApprovalDecision, McpRemoteTool, ModelCapabilities, ModelInfo, Sidecar};
use skills::SkillInfo;
use std::path::Path;
use std::sync::Arc;
use tauri::{AppHandle, Emitter, Manager, State};
use templates::ProjectTemplate;

pub struct AppState {
    pub db: Arc<Database>,
    pub sidecar: Arc<Sidecar>,
}

type CmdResult<T> = Result<T, String>;

fn provider_json(id: &str, protocol: &str, base_url: &str, api_key: &str, model: &str) -> Value {
    json!({"id": id, "protocol": protocol, "base_url": base_url, "api_key": api_key, "model": model})
}

/// `method` (`list_models` or `test_provider`) through the sidecar; rows are labelled with the provider id.
async fn list_models(
    sidecar: &Sidecar,
    method: &str,
    id: &str,
    protocol: &str,
    base_url: &str,
    api_key: &str,
) -> anyhow::Result<Vec<ModelInfo>> {
    let v = sidecar
        .call(
            method,
            json!({"provider": provider_json(id, protocol, base_url, api_key, "")}),
        )
        .await?;
    let mut models: Vec<ModelInfo> = serde_json::from_value(v)?;
    for m in &mut models {
        m.provider = id.to_string();
    }
    Ok(models)
}

#[tauri::command]
fn get_settings(state: State<'_, AppState>) -> CmdResult<AppSettings> {
    state.db.get_settings().map_err(|e| e.to_string())
}

#[tauri::command]
fn save_settings(state: State<'_, AppState>, settings: AppSettings) -> CmdResult<()> {
    state.db.save_settings(&settings).map_err(|e| e.to_string())
}

#[tauri::command]
fn list_personas(state: State<'_, AppState>) -> CmdResult<Vec<Persona>> {
    state.db.list_personas().map_err(|e| e.to_string())
}

#[tauri::command]
fn save_custom_persona(
    state: State<'_, AppState>,
    id: Option<String>,
    name: String,
    tagline: String,
    system_prompt: String,
    starter_prompts: Vec<String>,
    skill_ids: Option<Vec<String>>,
    mcp_server_ids: Option<Vec<String>>,
) -> CmdResult<Persona> {
    state
        .db
        .save_custom_persona(
            id.as_deref(),
            &name,
            &tagline,
            &system_prompt,
            &starter_prompts,
            &skill_ids.unwrap_or_default(),
            &mcp_server_ids.unwrap_or_default(),
        )
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_custom_persona(state: State<'_, AppState>, id: String) -> CmdResult<()> {
    state
        .db
        .delete_custom_persona(&id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_providers(state: State<'_, AppState>) -> CmdResult<Vec<ProviderEntry>> {
    state.db.list_providers().map_err(|e| e.to_string())
}

#[tauri::command]
fn save_provider(
    state: State<'_, AppState>,
    provider: ProviderEntry,
) -> CmdResult<Vec<ProviderEntry>> {
    state.db.save_provider(&provider).map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_provider(state: State<'_, AppState>, id: String) -> CmdResult<Vec<ProviderEntry>> {
    state.db.delete_provider(&id).map_err(|e| e.to_string())
}

#[tauri::command]
async fn list_provider_models(state: State<'_, AppState>) -> CmdResult<Vec<ModelInfo>> {
    let settings = state.db.get_settings().map_err(|e| e.to_string())?;
    let providers_list = state.db.list_providers().map_err(|e| e.to_string())?;
    let mut all = Vec::new();

    for p in providers_list.into_iter().filter(|p| p.enabled) {
        let (base_url, api_key) = settings.resolve_provider_config(&p.id);
        let is_active = settings.default_provider == p.id;
        let is_local = base_url.contains("127.0.0.1") || base_url.contains("localhost");
        if p.protocol == "ollama" || is_active || !api_key.trim().is_empty() || is_local {
            if let Ok(mut models) = list_models(
                &state.sidecar,
                "list_models",
                &p.id,
                &p.protocol,
                &base_url,
                &api_key,
            )
            .await
            {
                all.append(&mut models);
            }
        }
    }
    Ok(all)
}

#[tauri::command]
async fn get_model_capabilities(
    state: State<'_, AppState>,
    model: String,
) -> CmdResult<ModelCapabilities> {
    let settings = state.db.get_settings().unwrap_or_default();
    let (base_url, _) = settings.resolve_provider_config("ollama");
    let v = state
        .sidecar
        .call(
            "model_capabilities",
            json!({"provider": provider_json("ollama", "ollama", &base_url, "", &model)}),
        )
        .await
        .map_err(|e| e.to_string())?;
    serde_json::from_value(v).map_err(|e| e.to_string())
}

/// One provider's models for the Settings dropdown; unlike the Test, no key check.
#[tauri::command]
async fn list_models_for_provider(
    state: State<'_, AppState>,
    provider: String,
    base_url: String,
    api_key: String,
) -> CmdResult<Vec<ModelInfo>> {
    let settings = state.db.get_settings().unwrap_or_default();
    let protocol = settings.resolve_provider_protocol(&provider);
    list_models(
        &state.sidecar,
        "list_models",
        &provider,
        &protocol,
        &base_url,
        &api_key,
    )
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
async fn test_provider_connection(
    state: State<'_, AppState>,
    provider: String,
    base_url: String,
    api_key: String,
) -> CmdResult<Vec<ModelInfo>> {
    let settings = state.db.get_settings().unwrap_or_default();
    let protocol = settings.resolve_provider_protocol(&provider);
    list_models(
        &state.sidecar,
        "test_provider",
        &provider,
        &protocol,
        &base_url,
        &api_key,
    )
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_projects(state: State<'_, AppState>) -> CmdResult<Vec<Project>> {
    state.db.list_projects().map_err(|e| e.to_string())
}

#[tauri::command]
fn create_project(
    state: State<'_, AppState>,
    name: String,
    root_path: String,
    instructions: String,
    persona_id: Option<String>,
    template_id: Option<String>,
) -> CmdResult<Project> {
    let path = Path::new(&root_path);
    let mut final_instructions = instructions;
    if let Some(tid) = template_id {
        if !tid.is_empty() {
            let tpl = templates::scaffold_template(&tid, &name, path).map_err(|e| e.to_string())?;
            if final_instructions.trim().is_empty() {
                final_instructions = tpl.default_instructions;
            }
        }
    } else {
        std::fs::create_dir_all(path).map_err(|e| e.to_string())?;
    }
    let pid = state.db.resolve_default_persona_id(persona_id.as_deref());
    state
        .db
        .create_project(&name, &root_path, &final_instructions, &pid)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn update_project(
    state: State<'_, AppState>,
    id: String,
    name: String,
    instructions: String,
    persona_id: String,
) -> CmdResult<Project> {
    state
        .db
        .update_project(&id, &name, &instructions, &persona_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_project(state: State<'_, AppState>, id: String) -> CmdResult<()> {
    state.db.delete_project(&id).map_err(|e| e.to_string())
}

#[tauri::command]
fn list_project_files(
    state: State<'_, AppState>,
    project_id: String,
    sub_path: Option<String>,
) -> CmdResult<Vec<FileNode>> {
    let proj = state
        .db
        .get_project(&project_id)
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "Project not found".to_string())?;
    files::list_workspace_files(Path::new(&proj.root_path), sub_path.as_deref(), 300)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn read_project_file(
    state: State<'_, AppState>,
    project_id: String,
    relative_path: String,
) -> CmdResult<String> {
    let proj = state
        .db
        .get_project(&project_id)
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "Project not found".to_string())?;
    files::read_workspace_file(Path::new(&proj.root_path), &relative_path)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn write_project_file(
    state: State<'_, AppState>,
    project_id: String,
    relative_path: String,
    content: String,
) -> CmdResult<String> {
    let proj = state
        .db
        .get_project(&project_id)
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "Project not found".to_string())?;
    files::write_workspace_file(Path::new(&proj.root_path), &relative_path, &content)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_knowledge_files(
    state: State<'_, AppState>,
    project_id: String,
) -> CmdResult<Vec<KnowledgeFile>> {
    state
        .db
        .list_knowledge_files(&project_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn add_knowledge_file(
    state: State<'_, AppState>,
    project_id: String,
    relative_path: String,
) -> CmdResult<KnowledgeFile> {
    state
        .db
        .add_knowledge_file(&project_id, &relative_path)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn remove_knowledge_file(state: State<'_, AppState>, id: String) -> CmdResult<()> {
    state
        .db
        .remove_knowledge_file(&id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_templates() -> Vec<ProjectTemplate> {
    templates::list_templates()
}

#[tauri::command]
fn list_chats(state: State<'_, AppState>, project_id: Option<String>) -> CmdResult<Vec<Chat>> {
    state
        .db
        .list_chats(project_id.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn create_chat(
    state: State<'_, AppState>,
    project_id: Option<String>,
    title: String,
    provider: String,
    model: String,
) -> CmdResult<Chat> {
    state
        .db
        .create_chat(project_id.as_deref(), &title, &provider, &model)
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn delete_chat(state: State<'_, AppState>, chat_id: String) -> CmdResult<()> {
    let _ = state.sidecar.send_cancel(chat_id.clone()).await;
    state.db.delete_chat(&chat_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn list_messages(state: State<'_, AppState>, chat_id: String) -> CmdResult<Vec<StoredMessage>> {
    // `system` rows carry only model history for the sidecar; the UI never shows them.
    let mut rows = state
        .db
        .list_messages(&chat_id)
        .map_err(|e| e.to_string())?;
    rows.retain(|m| m.role != "system");
    Ok(rows)
}

#[tauri::command]
async fn send_user_message(
    app: AppHandle,
    state: State<'_, AppState>,
    chat_id: String,
    content: String,
) -> CmdResult<StoredMessage> {
    let existing = state
        .db
        .list_messages(&chat_id)
        .map_err(|e| e.to_string())?;
    let user_msg = state
        .db
        .add_message(&chat_id, "user", &content, None, None, None, None)
        .map_err(|e| e.to_string())?;

    if existing.is_empty() {
        let title: String = content
            .lines()
            .next()
            .unwrap_or("New Chat")
            .chars()
            .take(48)
            .collect();
        let _ = state.db.update_chat_title(&chat_id, title.trim());
    }

    let db = state.db.clone();
    let sidecar = state.sidecar.clone();
    tokio::spawn(async move {
        let sent = match turn_request::build_turn_request(&db, &chat_id) {
            Ok(req) => sidecar.send_turn(req).await,
            Err(e) => Err(e),
        };
        // Once sent, the sidecar (or its exit) reports `chat:finished`.
        if let Err(e) = sent {
            let _ = app.emit(
                "chat:finished",
                json!({"chat_id": chat_id, "error": e.to_string()}),
            );
        }
    });

    Ok(user_msg)
}

#[tauri::command]
async fn stop_chat_generation(state: State<'_, AppState>, chat_id: String) -> CmdResult<()> {
    state
        .sidecar
        .send_cancel(chat_id)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn respond_to_approval(
    state: State<'_, AppState>,
    request_id: String,
    decision: ApprovalDecision,
) -> CmdResult<bool> {
    state
        .sidecar
        .send_approval(request_id, decision)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_lessons(persona_id: String) -> CmdResult<Vec<lessons::Lesson>> {
    Ok(lessons::load_lessons(&persona_id))
}

#[tauri::command]
fn update_lesson(persona_id: String, index: usize, text: String) -> CmdResult<()> {
    let mut l = lessons::load_lessons(&persona_id);
    l.get_mut(index).ok_or("No such lesson")?.text = text.trim().replace('\n', " ");
    lessons::save_lessons(&persona_id, &l).map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_lesson(persona_id: String, index: usize) -> CmdResult<()> {
    let mut l = lessons::load_lessons(&persona_id);
    if index >= l.len() {
        return Err("No such lesson".into());
    }
    l.remove(index);
    lessons::save_lessons(&persona_id, &l).map_err(|e| e.to_string())
}

/// Returns immediately; the reflection runs in the background.
#[tauri::command]
async fn rate_message(
    state: State<'_, AppState>,
    chat_id: String,
    message_id: String,
    up: bool,
    comment: Option<String>,
) -> CmdResult<()> {
    let _ = message_id; // the whole trajectory is summarized, not one message
    let db = state.db.clone();
    let chat = db
        .get_chat(&chat_id)
        .map_err(|e| e.to_string())?
        .ok_or("Chat not found")?;
    let project = db.workspace_for_chat(&chat).map_err(|e| e.to_string())?;
    let settings = db.get_settings().unwrap_or_default();
    // Lessons belong to a persona; a plain chat has none, so its ratings teach nothing.
    let Some(persona_id) = turn_request::resolve_persona_id(&settings, project.as_ref()) else {
        return Ok(());
    };
    let history: Vec<sidecar::StoredRow> = db
        .list_messages(&chat_id)
        .map_err(|e| e.to_string())?
        .into_iter()
        .map(Into::into)
        .collect();
    let params = json!({
        "persona_id": persona_id,
        "up": up,
        "comment": comment,
        "provider": turn_request::resolve_provider(&settings, &chat),
        "history": history,
        "lessons": turn_request::lesson_texts(&persona_id),
    });
    // The sidecar emits a `lesson` event when the reflection yields one.
    let sidecar = state.sidecar.clone();
    tokio::spawn(async move {
        if let Err(e) = sidecar.call("reflect_rating", params).await {
            eprintln!("reflection failed: {e}");
        }
    });
    Ok(())
}

#[tauri::command]
fn list_skills(
    state: State<'_, AppState>,
    project_id: Option<String>,
) -> CmdResult<Vec<SkillInfo>> {
    let proj_root = project_id
        .and_then(|pid| state.db.get_project(&pid).ok().flatten())
        .map(|p| std::path::PathBuf::from(p.root_path));
    Ok(skills::discover_skills(&state.db, proj_root.as_deref()))
}

#[tauri::command]
fn toggle_skill(
    state: State<'_, AppState>,
    project_id: Option<String>,
    skill_name: String,
    enabled: bool,
) -> CmdResult<()> {
    let proj_root = project_id
        .and_then(|pid| state.db.get_project(&pid).ok().flatten())
        .map(|p| std::path::PathBuf::from(p.root_path));
    skills::set_skill_enabled(&state.db, proj_root.as_deref(), &skill_name, enabled)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn create_skill(
    state: State<'_, AppState>,
    project_id: Option<String>,
    scope: String,
    name: String,
    description: String,
    body: String,
) -> CmdResult<SkillInfo> {
    let proj_root = project_id
        .and_then(|pid| state.db.get_project(&pid).ok().flatten())
        .map(|p| std::path::PathBuf::from(p.root_path));
    skills::create_custom_skill(
        &state.db,
        proj_root.as_deref(),
        &scope,
        &name,
        &description,
        &body,
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_skill(
    state: State<'_, AppState>,
    project_id: Option<String>,
    skill_name: String,
) -> CmdResult<()> {
    let proj_root = project_id
        .and_then(|pid| state.db.get_project(&pid).ok().flatten())
        .map(|p| std::path::PathBuf::from(p.root_path));
    skills::delete_custom_skill(proj_root.as_deref(), &skill_name).map_err(|e| e.to_string())
}

#[tauri::command]
async fn start_lmstudio_server(base_url: String) -> CmdResult<()> {
    lmstudio::start_server(&base_url).await
}

#[tauri::command]
fn is_command_available(name: String) -> bool {
    which::which(name).is_ok()
}

#[tauri::command]
fn list_mcp_servers(state: State<'_, AppState>) -> CmdResult<Vec<McpServerConfig>> {
    state.db.list_mcp_servers().map_err(|e| e.to_string())
}

#[tauri::command]
fn save_mcp_server(
    state: State<'_, AppState>,
    server: McpServerConfig,
) -> CmdResult<McpServerConfig> {
    state.db.save_mcp_server(&server).map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_mcp_server(state: State<'_, AppState>, id: String) -> CmdResult<()> {
    state.db.delete_mcp_server(&id).map_err(|e| e.to_string())
}

#[tauri::command]
async fn test_mcp_server(
    state: State<'_, AppState>,
    server: McpServerConfig,
) -> CmdResult<Vec<McpRemoteTool>> {
    let v = state
        .sidecar
        .call("test_mcp_server", json!({ "server": server }))
        .await
        .map_err(|e| e.to_string())?;
    serde_json::from_value(v).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(print::PrintPages::default())
        .register_uri_scheme_protocol(print::SCHEME, print::serve)
        .setup(|app| {
            db::secrets::load(); // API keys from ~/.thea/credentials, once at startup
                                 // Track tauri.conf.json and icon.png so rustc always re-expands tauri::generate_context!()
            let _ = include_str!("../tauri.conf.json");
            let _ = include_bytes!("../icons/icon.png");
            if let Some(icon) = app.default_window_icon().cloned() {
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.set_icon(icon);
                    let _ = win.set_title("");
                }
            }
            let thea_dir = thea_home_dir();
            let _ = std::fs::create_dir_all(thea_dir.join("skills"));
            let db_path = thea_dir.join("thea.sqlite3");

            // Migrate existing database from OS app_data_dir if ~/.thea/thea.sqlite3 doesn't exist yet
            if !db_path.exists() {
                if let Ok(legacy_dir) = app.path().app_data_dir() {
                    let legacy_db = legacy_dir.join("thea.sqlite3");
                    if legacy_db.exists() {
                        let _ = std::fs::copy(&legacy_db, &db_path);
                    }
                }
            }

            let db = Database::open(&db_path).expect("Failed to initialize Thea SQLite database");
            // Ensure ~/.thea/providers.json, ~/.thea/settings.json, ~/.thea/personas.json, ~/.thea/skills.json, ~/.thea/mcp.json are initialized
            let _ = db.list_providers();
            let _ = db.get_settings();
            let _ = db.list_personas();
            let _ = db.reseed_builtin_personas();
            let _ = skills::discover_skills(&db, None);
            let _ = db.list_mcp_servers();
            let _ = db.ensure_mcp_presets();

            let db = Arc::new(db);
            let sidecar = Sidecar::spawn(app.handle().clone(), db.clone())?;
            app.manage(AppState { db, sidecar });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            print::print_artifact,
            get_settings,
            save_settings,
            get_model_capabilities,
            list_providers,
            save_provider,
            delete_provider,
            list_personas,
            save_custom_persona,
            delete_custom_persona,
            list_provider_models,
            test_provider_connection,
            list_models_for_provider,
            start_lmstudio_server,
            list_projects,
            create_project,
            update_project,
            delete_project,
            list_project_files,
            read_project_file,
            write_project_file,
            list_knowledge_files,
            add_knowledge_file,
            remove_knowledge_file,
            list_templates,
            list_chats,
            create_chat,
            delete_chat,
            list_messages,
            send_user_message,
            stop_chat_generation,
            respond_to_approval,
            list_skills,
            list_lessons,
            update_lesson,
            delete_lesson,
            rate_message,
            toggle_skill,
            create_skill,
            delete_skill,
            list_mcp_servers,
            is_command_available,
            save_mcp_server,
            delete_mcp_server,
            test_mcp_server,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Thea")
        // Managed state is never dropped on exit, so the sidecar is stopped here.
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<AppState>() {
                    tauri::async_runtime::block_on(state.sidecar.shutdown());
                }
            }
        });
}
