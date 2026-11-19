//! The file pane's workspace access: list, read and write inside a project root.
use anyhow::{bail, Context, Result};
use ignore::WalkBuilder;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Component, Path, PathBuf};

/// Kept by the sidecar's `add_source` tool; the pane must not overwrite it.
const LEDGER_PATH: &str = "research/sources.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileNode {
    pub name: String,
    pub relative_path: String,
    pub is_dir: bool,
    pub size: u64,
}

/// Secret-bearing files the model must never see: read tools are auto-approved and
/// their output may be sent to a cloud provider.
pub fn is_secret_file(name: &str) -> bool {
    name.starts_with(".env")
}

fn is_excluded(name: &str) -> bool {
    matches!(name, ".git" | "node_modules" | "target" | ".venv") || is_secret_file(name)
}

pub fn list_workspace_files(
    project_root: &Path,
    sub_path: Option<&str>,
    max_entries: usize,
) -> Result<Vec<FileNode>> {
    let target = match sub_path {
        Some(p) if !p.trim().is_empty() && p.trim() != "." => {
            resolve_sandboxed_path(project_root, p)?
        }
        _ => project_root.canonicalize()?,
    };
    let canon_root = project_root.canonicalize()?;

    let mut entries = Vec::new();
    let walker = WalkBuilder::new(&target)
        .max_depth(Some(3))
        .hidden(false)
        .git_ignore(true)
        .filter_entry(|e| !is_excluded(&e.file_name().to_string_lossy()))
        .build();

    for result in walker {
        let Ok(entry) = result else { continue };
        if entry.path() == target {
            continue;
        }
        let Ok(rel) = entry.path().strip_prefix(&canon_root) else {
            continue;
        };
        let meta = entry.metadata().ok();
        let is_dir = meta.as_ref().map(|m| m.is_dir()).unwrap_or(false);
        let size = meta.as_ref().map(|m| m.len()).unwrap_or(0);
        entries.push(FileNode {
            name: entry.file_name().to_string_lossy().to_string(),
            relative_path: rel.to_string_lossy().replace('\\', "/"),
            is_dir,
            size,
        });
        if entries.len() >= max_entries {
            break;
        }
    }
    entries.sort_by(|a, b| {
        b.is_dir
            .cmp(&a.is_dir)
            .then(a.relative_path.cmp(&b.relative_path))
    });
    Ok(entries)
}

pub fn read_workspace_file(project_root: &Path, user_path: &str) -> Result<String> {
    let path = resolve_sandboxed_path(project_root, user_path)?;
    if path
        .file_name()
        .map(|n| is_secret_file(&n.to_string_lossy()))
        .unwrap_or(false)
    {
        bail!(
            "'{}' may contain secrets and is not readable by tools",
            user_path
        );
    }
    let meta = fs::metadata(&path).with_context(|| format!("File not found: {}", user_path))?;
    if meta.len() > 512 * 1024 {
        bail!(
            "File '{}' is larger than 512 KB ({} bytes)",
            user_path,
            meta.len()
        );
    }
    let content = fs::read_to_string(&path)
        .with_context(|| format!("Could not read '{}' as UTF-8 text", user_path))?;
    Ok(content)
}

pub fn write_workspace_file(project_root: &Path, user_path: &str, content: &str) -> Result<String> {
    if is_ledger_file(project_root, user_path) {
        bail!(
            "'{}' is managed by the add_source tool and cannot be written directly",
            user_path
        );
    }
    let path = resolve_sandboxed_path(project_root, user_path)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&path, content).with_context(|| format!("Failed to write file '{}'", user_path))?;
    Ok(format!("Wrote {} bytes to {}", content.len(), user_path))
}

/// Case-insensitive on the resolved path, so `./`, `..` and case variants are caught too.
fn is_ledger_file(project_root: &Path, user_path: &str) -> bool {
    match (
        resolve_sandboxed_path(project_root, user_path),
        resolve_sandboxed_path(project_root, LEDGER_PATH),
    ) {
        (Ok(a), Ok(b)) => a
            .to_string_lossy()
            .eq_ignore_ascii_case(&b.to_string_lossy()),
        _ => false,
    }
}

/// `Path::canonicalize` on Windows returns `\\?\C:\...`; model-supplied absolute paths
/// never carry that prefix, so strip it before comparing.
// ponytail: handles drive paths only; `\\?\UNC\` shares are left as-is.
fn strip_verbatim(p: PathBuf) -> PathBuf {
    let s = p.to_string_lossy();
    match s.strip_prefix(r"\\?\") {
        Some(rest) => PathBuf::from(rest),
        None => p,
    }
}

/// Small models leak markdown into path arguments: `` `research/notes.md` ``,
/// `**drafts/a.md**`, `"a.md",`. Strip the wrapping noise so the file lands under
/// the name the model meant and the UI recognises its extension.
fn clean_path_arg(user_path: &str) -> String {
    user_path
        .trim()
        .trim_matches(|c: char| matches!(c, '`' | '*' | '"' | '\'' | ',' | ';' | '_'))
        .trim()
        .to_string()
}

/// Resolves `rel_or_abs` inside `project_root` and guarantees the resolved path
/// stays strictly inside `project_root` (preventing `..` traversal and symlink escapes).
pub fn resolve_sandboxed_path(project_root: &Path, user_path: &str) -> Result<PathBuf> {
    let user_path = &clean_path_arg(user_path);
    let canon_root = strip_verbatim(
        project_root
            .canonicalize()
            .with_context(|| format!("Project root does not exist: {}", project_root.display()))?,
    );

    let candidate = Path::new(user_path);
    let joined = if candidate.is_absolute() {
        strip_verbatim(candidate.to_path_buf())
    } else {
        canon_root.join(candidate)
    };

    // Normalize lexical components first (`..`, `.`)
    let mut normalized = PathBuf::new();
    for comp in joined.components() {
        match comp {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }

    if !normalized.starts_with(&canon_root) {
        bail!(
            "Path '{}' escapes project workspace '{}'",
            user_path,
            canon_root.display()
        );
    }

    // If the target or an ancestor already exists on disk, canonicalize that ancestor
    // to ensure symlinks inside the workspace don't point outside the workspace.
    let mut probe = normalized.as_path();
    while !probe.exists() {
        if let Some(parent) = probe.parent() {
            probe = parent;
        } else {
            break;
        }
    }
    if probe.exists() {
        let canon_probe = strip_verbatim(probe.canonicalize()?);
        if !canon_probe.starts_with(&canon_root) {
            bail!(
                "Symlink target for '{}' escapes project workspace '{}'",
                user_path,
                canon_root.display()
            );
        }
    }

    Ok(normalized)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn write_file_refuses_the_ledger() {
        let dir = tempdir().unwrap();
        for p in [
            "research/sources.json",
            "research/./sources.json",
            "research//sources.json",
            "research/../research/sources.json",
            "Research/Sources.json",
        ] {
            let err = write_workspace_file(dir.path(), p, "[]")
                .unwrap_err()
                .to_string();
            assert!(err.contains("add_source"), "{p}");
        }
    }

    #[test]
    fn env_files_are_hidden() {
        let dir = tempdir().unwrap();
        fs::write(dir.path().join(".env"), "SECRET=1").unwrap();
        assert!(read_workspace_file(dir.path(), ".env").is_err());
        let listed = list_workspace_files(dir.path(), None, 50).unwrap();
        assert!(listed.iter().all(|f| f.name != ".env"));
    }

    #[test]
    fn paths_stay_inside_the_workspace() {
        let dir = tempdir().unwrap();
        assert!(resolve_sandboxed_path(dir.path(), "src/main.rs")
            .unwrap()
            .ends_with("src/main.rs"));
        assert!(resolve_sandboxed_path(dir.path(), "../../etc/passwd").is_err());
        assert!(resolve_sandboxed_path(dir.path(), "/etc/hosts").is_err());
        assert_eq!(clean_path_arg("`research/notes.md`"), "research/notes.md");
    }
}
