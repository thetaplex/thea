use anyhow::{Context, Result};
use include_dir::{include_dir, Dir};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

static BUNDLED_TEMPLATES: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/../templates");

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectTemplate {
    pub id: String,
    pub name: String,
    pub description: String,
    pub icon: String,
    pub default_instructions: String,
    #[serde(default)]
    pub files: HashMap<String, String>,
}

pub fn list_templates() -> Vec<ProjectTemplate> {
    let mut out = Vec::new();
    for dir in BUNDLED_TEMPLATES.dirs() {
        if let Some(file) = dir.get_file(dir.path().join("template.json")) {
            if let Some(raw) = file.contents_utf8() {
                if let Ok(tpl) = serde_json::from_str::<ProjectTemplate>(raw) {
                    out.push(tpl);
                }
            }
        }
    }
    out.sort_by(|a, b| a.name.cmp(&b.name));
    out
}

pub fn scaffold_template(
    template_id: &str,
    project_name: &str,
    target_dir: &Path,
) -> Result<ProjectTemplate> {
    let templates = list_templates();
    let tpl = templates
        .into_iter()
        .find(|t| t.id == template_id)
        .with_context(|| format!("Unknown template '{}'", template_id))?;

    fs::create_dir_all(target_dir)
        .with_context(|| format!("Could not create directory {}", target_dir.display()))?;
    if !tpl.files.is_empty() && fs::read_dir(target_dir)?.next().is_some() {
        anyhow::bail!(
            "Folder {} is not empty; pick an empty folder for a template or use 'Open existing folder'",
            target_dir.display()
        );
    }

    let slug: String = project_name
        .trim()
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string();
    let slug = if slug.is_empty() {
        "thea-app".to_string()
    } else {
        slug
    };

    for (rel_path, raw_content) in &tpl.files {
        let dest = target_dir.join(rel_path);
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }
        let rendered = raw_content
            .replace("{{PROJECT_NAME}}", project_name)
            .replace("{{PROJECT_SLUG}}", &slug);
        fs::write(&dest, rendered)?;
    }

    Ok(tpl)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn scaffolds_react_vite_template() {
        let dir = tempdir().unwrap();
        let tpl = scaffold_template("react-vite", "My Cool App", dir.path()).unwrap();
        assert_eq!(tpl.id, "react-vite");
        let pkg = fs::read_to_string(dir.path().join("package.json")).unwrap();
        assert!(pkg.contains("\"my-cool-app\""));
        assert!(dir.path().join("src/App.tsx").exists());
    }

    #[test]
    fn refuses_non_empty_target() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join("keep.txt"), "mine").unwrap();
        assert!(scaffold_template("react-vite", "x", dir.path()).is_err());
        assert_eq!(
            fs::read_to_string(dir.path().join("keep.txt")).unwrap(),
            "mine"
        );
    }
}
