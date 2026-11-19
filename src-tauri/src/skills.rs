use crate::db::{thea_home_dir, Database, Persona};
use anyhow::{Context, Result};
use include_dir::{include_dir, Dir};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

static BUNDLED_SKILLS: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/../skills");

fn default_global_source() -> String {
    "global".to_string()
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillInfo {
    pub name: String,
    pub description: String,
    pub body: String,
    #[serde(default = "default_global_source")]
    pub source: String, // "builtin" | "global" | "project"
    #[serde(default)]
    pub path: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
}

pub fn global_skills_file() -> PathBuf {
    thea_home_dir().join("skills.json")
}

pub fn project_skills_file(project_root: &Path) -> PathBuf {
    project_root.join(".thea").join("skills.json")
}

fn load_skills_json(file_path: &Path, source: &str) -> Vec<SkillInfo> {
    if !file_path.exists() {
        if source == "global" {
            let _ = fs::write(file_path, "[]\n");
        }
        return Vec::new();
    }
    let Ok(raw) = fs::read_to_string(file_path) else {
        return Vec::new();
    };
    let mut list: Vec<SkillInfo> = serde_json::from_str(&raw).unwrap_or_default();
    for s in &mut list {
        s.source = source.to_string();
        if s.path.is_empty() {
            s.path = file_path.to_string_lossy().to_string();
        }
    }
    list
}

fn save_skills_json(file_path: &Path, skills: &[SkillInfo]) -> Result<()> {
    if let Some(parent) = file_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(skills)?;
    fs::write(file_path, json)?;
    Ok(())
}

/// Parse `---\ndescription: ...\n---\n<body>`. Returns None without front matter.
pub fn parse_skill_file(name: &str, raw: &str) -> Option<SkillInfo> {
    let raw = raw.replace("\r\n", "\n");
    let rest = raw.strip_prefix("---\n")?;
    let (front, body) = rest.split_once("\n---\n")?;
    let description = front
        .lines()
        .find_map(|l| l.strip_prefix("description:"))?
        .trim()
        .to_string();
    Some(SkillInfo {
        name: name.to_string(),
        description,
        body: body.trim().to_string(),
        source: "builtin".to_string(),
        path: format!("builtin:{name}"),
        enabled: true,
    })
}

pub fn builtin_skills() -> Vec<SkillInfo> {
    let mut out: Vec<SkillInfo> = BUNDLED_SKILLS
        .files()
        .filter_map(|f| {
            let name = f.path().file_stem()?.to_str()?;
            parse_skill_file(name, f.contents_utf8()?)
        })
        .collect();
    out.sort_by(|a, b| a.name.cmp(&b.name));
    out
}

pub fn discover_skills(_db: &Database, project_root: Option<&Path>) -> Vec<SkillInfo> {
    // Built-ins are not listed in the UI, so there is no way to re-enable one;
    // they are always enabled. `disabled_builtin_skills` is legacy and ignored.
    let mut skills = builtin_skills();

    let mut layers = vec![load_skills_json(&global_skills_file(), "global")];
    if let Some(root) = project_root {
        layers.push(load_skills_json(&project_skills_file(root), "project"));
    }
    for layer in layers {
        for s in layer {
            skills.retain(|x| x.name != s.name);
            skills.push(s);
        }
    }
    skills
}

/// Skills a persona gets. Empty `skill_ids` means all. A built-in persona's list
/// restricts only built-in skills, so the user's own skills stay available to it.
pub fn skills_for(persona: &Persona, skills: Vec<SkillInfo>) -> Vec<SkillInfo> {
    if persona.skill_ids.is_empty() {
        return skills;
    }
    let builtin = crate::db::is_builtin_persona(&persona.id);
    skills
        .into_iter()
        .filter(|s| {
            (builtin && s.source != "builtin") || persona.skill_ids.iter().any(|id| id == &s.name)
        })
        .collect()
}

/// Writes the enabled skills as an Agent Skills library, `<dir>/<name>/SKILL.md`, for the
/// sidecar. The directory is cleared first. Returns the names written.
pub fn write_skill_library(dir: &Path, skills: &[SkillInfo]) -> Result<Vec<String>> {
    match fs::remove_dir_all(dir) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => return Err(e.into()),
        _ => {}
    }
    let mut names = Vec::new();
    for s in skills.iter().filter(|s| s.enabled) {
        // Names from a hand-edited skills.json become directory names; keep them to slugs.
        if s.name.is_empty()
            || !s
                .name
                .chars()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
        {
            continue;
        }
        let skill_dir = dir.join(&s.name);
        fs::create_dir_all(&skill_dir)?;
        // JSON strings are valid YAML scalars, so the description needs no YAML escaping.
        let md = format!(
            "---\nname: {}\ndescription: {}\n---\n\n{}\n",
            s.name,
            serde_json::to_string(&s.description)?,
            s.body
        );
        fs::write(skill_dir.join("SKILL.md"), md)?;
        names.push(s.name.clone());
    }
    Ok(names)
}

pub fn set_skill_enabled(
    db: &Database,
    project_root: Option<&Path>,
    skill_name: &str,
    enabled: bool,
) -> Result<()> {
    if let Some(root) = project_root {
        let proj_file = project_skills_file(root);
        if proj_file.exists() {
            let mut proj_skills = load_skills_json(&proj_file, "project");
            if let Some(item) = proj_skills.iter_mut().find(|s| s.name == skill_name) {
                item.enabled = enabled;
                save_skills_json(&proj_file, &proj_skills)?;
                return Ok(());
            }
        }
    }

    let global_file = global_skills_file();
    let mut global_skills = load_skills_json(&global_file, "global");
    if let Some(item) = global_skills.iter_mut().find(|s| s.name == skill_name) {
        item.enabled = enabled;
        save_skills_json(&global_file, &global_skills)?;
        return Ok(());
    }

    if builtin_skills().iter().any(|s| s.name == skill_name) {
        let mut settings = db.get_settings()?;
        settings.disabled_builtin_skills.retain(|n| n != skill_name);
        if !enabled {
            settings
                .disabled_builtin_skills
                .push(skill_name.to_string());
        }
        db.write_settings(&settings)?;
    }
    Ok(())
}

pub fn create_custom_skill(
    _db: &Database,
    project_root: Option<&Path>,
    scope: &str, // "global" | "project"
    name: &str,
    description: &str,
    body: &str,
) -> Result<SkillInfo> {
    let slug: String = name
        .trim()
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string();
    if slug.is_empty() {
        anyhow::bail!("Skill name cannot be empty");
    }

    let target_file = if scope == "project" {
        let root =
            project_root.context("Select a project first to create a project-scoped skill")?;
        project_skills_file(root)
    } else {
        global_skills_file()
    };

    let mut list = load_skills_json(&target_file, scope);
    let skill = SkillInfo {
        name: slug.clone(),
        description: description.trim().to_string(),
        body: body.trim().to_string(),
        source: scope.to_string(),
        path: target_file.to_string_lossy().to_string(),
        enabled: true,
    };

    if let Some(existing) = list.iter_mut().find(|s| s.name == slug) {
        *existing = skill.clone();
    } else {
        list.push(skill.clone());
    }
    save_skills_json(&target_file, &list)?;

    Ok(skill)
}

pub fn delete_custom_skill(project_root: Option<&Path>, skill_name: &str) -> Result<()> {
    if let Some(root) = project_root {
        let proj_file = project_skills_file(root);
        if proj_file.exists() {
            let mut proj_skills = load_skills_json(&proj_file, "project");
            let before = proj_skills.len();
            proj_skills.retain(|s| s.name != skill_name);
            if proj_skills.len() != before {
                save_skills_json(&proj_file, &proj_skills)?;
            }
        }
    }

    let global_file = global_skills_file();
    let mut global_skills = load_skills_json(&global_file, "global");
    global_skills.retain(|s| s.name != skill_name);
    save_skills_json(&global_file, &global_skills)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_skills_parse() {
        let s = builtin_skills();
        let names: Vec<&str> = s.iter().map(|x| x.name.as_str()).collect();
        for n in [
            "deep-research",
            "book-research",
            "write-essay",
            "research-method",
            "source-triage",
            "write-research-paper",
            "write-research-proposal",
            "write-report",
            "write-brief",
            "write-book-chapter",
            "manage-docket",
            "draft-communication",
            "weekly-review",
        ] {
            assert!(names.contains(&n), "{n}");
        }
        assert!(
            !names.contains(&"task-checklist")
                && !names.contains(&"think-in-steps")
                && !names.contains(&"write-ste")
        );
        for x in &s {
            assert!(x.description.contains("Use when"), "{}", x.name);
            assert_eq!(x.source, "builtin");
        }
    }

    #[test]
    fn global_skill_overrides_builtin() {
        let _g = crate::db::test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        create_custom_skill(&db, None, "global", "write-brief", "mine", "body").unwrap();
        set_skill_enabled(&db, None, "write-brief", false).unwrap();
        let all = discover_skills(&db, None);
        let brief = all.iter().find(|s| s.name == "write-brief").unwrap();
        assert_eq!(brief.source, "global");
        assert_eq!(brief.description, "mine");
        assert_eq!(all.iter().filter(|s| s.name == "write-brief").count(), 1);
    }

    #[test]
    fn builtins_are_always_enabled_even_when_listed_as_disabled() {
        let _g = crate::db::test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
        set_skill_enabled(&db, None, "write-brief", false).unwrap();
        let all = discover_skills(&db, None);
        assert!(
            all.iter()
                .find(|s| s.name == "write-brief")
                .unwrap()
                .enabled
        );
    }

    #[test]
    fn skill_library_has_frontmatter_and_is_cleared() {
        let dir = tempfile::tempdir().unwrap();
        let lib = dir.path().join("lib");
        std::fs::create_dir_all(lib.join("stale")).unwrap();
        let mut s = builtin_skills()[0].clone();
        s.description = "Use when: \"quoted\"".into();
        let mut off = s.clone();
        off.name = "off".into();
        off.enabled = false;
        let mut bad = s.clone();
        bad.name = "../x".into();
        let names = write_skill_library(&lib, &[s.clone(), off, bad]).unwrap();
        assert_eq!(names, vec![s.name.clone()]);
        assert!(!lib.join("stale").exists());
        let md = std::fs::read_to_string(lib.join(&s.name).join("SKILL.md")).unwrap();
        assert!(md.starts_with(&format!(
            "---\nname: {}\ndescription: \"Use when: \\\"quoted\\\"\"\n---\n",
            s.name
        )));
        assert!(md.contains(&s.body));
    }

    #[test]
    fn builtin_persona_skill_list_keeps_user_skills() {
        let mut skills = builtin_skills();
        let mut mine = skills[0].clone();
        mine.name = "my-own".to_string();
        mine.source = "global".to_string();
        skills.push(mine);
        let pa = crate::db::default_personas()
            .into_iter()
            .find(|p| p.id == "personal-assistant")
            .unwrap();
        let names: Vec<String> = skills_for(&pa, skills.clone())
            .into_iter()
            .map(|s| s.name)
            .collect();
        assert!(names.iter().any(|n| n == "my-own"));
        assert!(names.iter().any(|n| n == "manage-docket"));
        assert!(!names.iter().any(|n| n == "research-method"));
        let mut custom = pa.clone();
        custom.id = "mine".to_string();
        custom.skill_ids = vec!["manage-docket".to_string()];
        let names: Vec<String> = skills_for(&custom, skills)
            .into_iter()
            .map(|s| s.name)
            .collect();
        assert_eq!(names, vec!["manage-docket".to_string()]);
    }
}
