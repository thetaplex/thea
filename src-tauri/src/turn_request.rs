//! What Rust resolves from the database for the sidecar: the `turn` request and the
//! provider a chat runs on.
use crate::db::{
    is_builtin_persona, thea_home_dir, AppSettings, Chat, Database, Project, CHAT_WORKSPACE_PREFIX,
};
use crate::sidecar::{Provider, StoredRow, TurnRequest, WirePersona, Workspace};
use crate::{lessons, skills};
use anyhow::{anyhow, Result};
use serde_json::json;

/// A project's persona, else the settings default. A chat without a project has none.
pub fn resolve_persona_id(settings: &AppSettings, project: Option<&Project>) -> Option<String> {
    let p = project.filter(|p| !p.id.starts_with(CHAT_WORKSPACE_PREFIX))?;
    Some(if p.persona_id.is_empty() {
        settings.default_persona_id.clone()
    } else {
        p.persona_id.clone()
    })
}

/// The settings' default provider and model win over the chat's own.
pub fn resolve_provider(settings: &AppSettings, chat: &Chat) -> Provider {
    let pick = |s: &str, c: &str| if s.trim().is_empty() { c } else { s }.to_string();
    let id = pick(&settings.default_provider, &chat.provider);
    let (base_url, api_key) = settings.resolve_provider_config(&id);
    Provider {
        protocol: settings.resolve_provider_protocol(&id),
        base_url,
        api_key,
        model: pick(&settings.default_model, &chat.model),
    }
}

/// Lesson texts for the prompt, oldest first.
pub fn lesson_texts(persona_id: &str) -> Vec<String> {
    lessons::load_lessons(persona_id)
        .into_iter()
        .map(|l| l.text)
        .collect()
}

/// Everything the sidecar needs for one turn of `chat_id`. Also writes the persona's
/// skills to `<thea_home>/run/skills/<chat_id>/`.
pub fn build_turn_request(db: &Database, chat_id: &str) -> Result<TurnRequest> {
    let settings = db.get_settings().unwrap_or_default();
    let chat = db
        .get_chat(chat_id)?
        .ok_or_else(|| anyhow!("Chat not found"))?;
    let project = db.workspace_for_chat(&chat)?;
    let persona = match resolve_persona_id(&settings, project.as_ref()) {
        Some(id) => Some(db.get_persona(&id)?),
        None => None,
    };
    let root = project
        .as_ref()
        .map(|p| std::path::PathBuf::from(&p.root_path));
    let skill_dir = thea_home_dir().join("run").join("skills").join(chat_id);
    let skills = match &persona {
        Some(p) => skills::skills_for(p, skills::discover_skills(db, root.as_deref())),
        None => Vec::new(),
    };
    let skill_names = skills::write_skill_library(&skill_dir, &skills)?;
    let lessons = persona
        .as_ref()
        .map(|p| lesson_texts(&p.id))
        .unwrap_or_default();
    let knowledge_files = match &project {
        Some(p) => db
            .list_knowledge_files(&p.id)
            .unwrap_or_default()
            .into_iter()
            .map(|k| k.relative_path)
            .collect(),
        None => Vec::new(),
    };
    Ok(TurnRequest {
        chat_id: chat_id.to_string(),
        persona: persona.map(|persona| WirePersona {
            builtin: is_builtin_persona(&persona.id),
            id: persona.id,
            name: persona.name,
            tagline: persona.tagline,
            system_prompt: persona.system_prompt,
            tool_ids: persona.tool_ids,
            skill_ids: persona.skill_ids,
            mcp_server_ids: persona.mcp_server_ids,
            native_thinking: persona.native_thinking,
            max_steps: persona.max_steps,
        }),
        provider: resolve_provider(&settings, &chat),
        small_model: settings.small_model,
        workspace: project.map(|p| Workspace {
            is_chat: p.id.starts_with(CHAT_WORKSPACE_PREFIX),
            id: p.id,
            name: p.name,
            root_path: p.root_path,
            instructions: p.instructions,
        }),
        knowledge_files,
        skill_dirs: vec![skill_dir.to_string_lossy().into_owned()],
        skills: skill_names,
        // The sidecar picks the persona's servers itself.
        mcp_servers: db.list_mcp_servers().unwrap_or_default(),
        settings: json!({ "searxng_url": settings.searxng_url }),
        lessons,
        history: db
            .list_messages(chat_id)?
            .into_iter()
            .map(StoredRow::from)
            .collect(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn turn_request_carries_history_skills_and_workspace() {
        let _g = crate::db::test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        db.list_personas().unwrap();
        let root = dir.path().join("proj");
        std::fs::create_dir_all(&root).unwrap();
        let proj = db
            .create_project(
                "P",
                &root.to_string_lossy(),
                "Be brief.",
                "research-assistant",
            )
            .unwrap();
        let chat = db.create_chat(Some(&proj.id), "t", "ollama", "m").unwrap();
        db.add_message(&chat.id, "user", "hi", None, None, None, None)
            .unwrap();
        db.add_message(&chat.id, "system", "", None, None, None, Some("[{}]"))
            .unwrap();
        let req = build_turn_request(&db, &chat.id).unwrap();
        let persona = req.persona.as_ref().unwrap();
        assert_eq!(
            (persona.id.as_str(), persona.builtin),
            ("research-assistant", true)
        );
        assert_eq!(req.provider.protocol, "ollama");
        assert_eq!(req.history.len(), 2, "system rows go to the sidecar");
        assert_eq!(req.history[1].model_message_json.as_deref(), Some("[{}]"));
        let ws = req.workspace.unwrap();
        assert_eq!((ws.instructions.as_str(), ws.is_chat), ("Be brief.", false));
        assert!(!req.skills.is_empty());
        let lib = std::path::Path::new(&req.skill_dirs[0]);
        assert!(lib.join(&req.skills[0]).join("SKILL.md").is_file());
    }

    #[test]
    fn a_chat_without_a_project_is_a_plain_chat() {
        let _g = crate::db::test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        db.list_personas().unwrap();
        let chat = db.create_chat(None, "t", "ollama", "m").unwrap();
        let req = build_turn_request(&db, &chat.id).unwrap();
        assert!(req.persona.is_none());
        assert!(req.skills.is_empty() && req.lessons.is_empty());
        assert!(
            req.workspace.unwrap().is_chat,
            "it still has its own folder"
        );
    }
}
