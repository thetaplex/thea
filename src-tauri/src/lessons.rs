//! Per-persona lessons file: `~/.thea/lessons/<persona-id>.md`. Storage and formatting only.
use crate::db::thea_home_dir;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

pub const MAX_LESSONS: usize = 20;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Lesson {
    pub date: String,
    pub signal: String,
    pub text: String,
}

pub fn lessons_file(persona_id: &str) -> PathBuf {
    // Persona ids become file names; keep path separators out.
    let safe: String = persona_id
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect();
    thea_home_dir().join("lessons").join(format!("{safe}.md"))
}

pub fn parse_lessons(md: &str) -> Vec<Lesson> {
    md.lines()
        .filter_map(|l| {
            let mut p = l.strip_prefix("- ")?.splitn(3, " | ");
            Some(Lesson {
                date: p.next()?.trim().to_string(),
                signal: p.next()?.trim().to_string(),
                text: p.next()?.trim().to_string(),
            })
        })
        .collect()
}

pub fn render_lessons(l: &[Lesson]) -> String {
    let mut out = String::from("# Lessons\n\n");
    for x in l {
        let one = |s: &str| s.split_whitespace().collect::<Vec<_>>().join(" ");
        out.push_str(&format!(
            "- {} | {} | {}\n",
            one(&x.date),
            one(&x.signal),
            one(&x.text)
        ));
    }
    out
}

pub fn load_lessons(persona_id: &str) -> Vec<Lesson> {
    std::fs::read_to_string(lessons_file(persona_id))
        .map(|s| parse_lessons(&s))
        .unwrap_or_default()
}

pub fn save_lessons(persona_id: &str, l: &[Lesson]) -> Result<()> {
    let path = lessons_file(persona_id);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(path, render_lessons(l))?;
    Ok(())
}

pub fn append_lesson(persona_id: &str, lesson: Lesson) -> Result<Vec<Lesson>> {
    let mut l = load_lessons(persona_id);
    l.push(lesson);
    if l.len() > MAX_LESSONS {
        l.drain(..l.len() - MAX_LESSONS);
    }
    save_lessons(persona_id, &l)?;
    Ok(l)
}

pub fn format_for_prompt(l: &[Lesson]) -> String {
    l.iter()
        .enumerate()
        .map(|(i, x)| format!("{}. {}", i + 1, x.text))
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_and_fifo_cap() {
        let _g = crate::db::test_env_lock();
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("THEA_HOME", dir.path());
        for i in 0..25 {
            append_lesson(
                "p",
                Lesson {
                    date: "2026-11-13".into(),
                    signal: "rating_down".into(),
                    text: format!("When {i}, do y."),
                },
            )
            .unwrap();
        }
        let l = load_lessons("p");
        assert_eq!(l.len(), MAX_LESSONS);
        assert_eq!(l[0].text, "When 5, do y.");
        assert_eq!(l[19].text, "When 24, do y.");
        assert_eq!(parse_lessons(&render_lessons(&l)), l);
    }

    #[test]
    fn render_collapses_newlines() {
        let l = vec![Lesson {
            date: "2026-11-13".into(),
            signal: "rating_up".into(),
            text: "When x,\ndo y.".into(),
        }];
        let md = render_lessons(&l);
        assert_eq!(md.lines().filter(|l| l.starts_with("- ")).count(), 1);
        assert_eq!(parse_lessons(&md)[0].text, "When x, do y.");
    }

    #[test]
    fn parse_ignores_other_lines() {
        assert_eq!(
            parse_lessons("# Lessons\n\nfree text\n- 2026-11-13 | check_citations | When a key is missing, add the source first.\n").len(),
            1
        );
    }
}
