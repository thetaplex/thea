//! Starts LM Studio's local server through its `lms` CLI, so a saved LM Studio
//! provider answers without the user opening the Developer tab.
use std::path::PathBuf;

/// The port in a base URL such as `http://127.0.0.1:1234/v1`; LM Studio's 1234 when none is given.
pub fn port_of(base_url: &str) -> Option<u16> {
    let rest = base_url.split_once("://").map_or(base_url, |(_, r)| r);
    let host = rest.split('/').next()?;
    match host.rsplit_once(':') {
        Some((_, port)) => port.parse().ok(),
        None => Some(1234),
    }
}

/// `lms` from LM Studio's install folder, else from PATH.
fn lms_path() -> Option<PathBuf> {
    let exe = if cfg!(windows) { "lms.exe" } else { "lms" };
    dirs::home_dir()
        .map(|h| h.join(".lmstudio").join("bin").join(exe))
        .filter(|p| p.is_file())
        .or_else(|| which::which("lms").ok())
}

pub async fn start_server(base_url: &str) -> Result<(), String> {
    let port =
        port_of(base_url).ok_or_else(|| format!("No port in the LM Studio URL {base_url}"))?;
    let lms = lms_path().ok_or(
        "LM Studio's `lms` tool was not found. Install LM Studio, or start its server in the Developer tab.",
    )?;
    let out = tokio::process::Command::new(lms)
        .args(["server", "start", "--port", &port.to_string()])
        .output()
        .await
        .map_err(|e| format!("Could not run lms: {e}"))?;
    if out.status.success() {
        Ok(())
    } else {
        let msg = String::from_utf8_lossy(if out.stderr.is_empty() {
            &out.stdout
        } else {
            &out.stderr
        });
        Err(format!("LM Studio server did not start: {}", msg.trim()))
    }
}

#[cfg(test)]
mod tests {
    use super::port_of;

    #[test]
    fn port_from_base_url() {
        assert_eq!(port_of("http://127.0.0.1:1234/v1"), Some(1234));
        assert_eq!(port_of("http://localhost:1235"), Some(1235));
        assert_eq!(port_of("http://localhost/v1"), Some(1234));
        assert_eq!(port_of("http://localhost:abc/v1"), None);
    }
}
