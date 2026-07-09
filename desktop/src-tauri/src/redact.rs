//! scrub emails and home-directory paths out of raw sidecar output.
//!
//! the backend structlog pipeline redacts its own structured events
//! (services/log_redaction.py), but uncaught tracebacks, uvicorn
//! output, and panics reach the shell on the sidecar's stderr with
//! no such treatment — and shell logs go into the diagnostics zip.
//! this mirrors the backend's regexes at that last chokepoint.

use std::sync::OnceLock;

use regex::Regex;

const REDACTED_EMAIL: &str = "<redacted-email>";

struct Rules {
    email: Regex,
    // (pattern, replacement) — home prefixes collapse to ~
    homes: Vec<Regex>,
}

fn rules() -> &'static Rules {
    static RULES: OnceLock<Rules> = OnceLock::new();
    RULES.get_or_init(|| {
        // same shapes as the python side: a quote/space/slash ends
        // the username so embedded json/paths stay intact.
        let mut patterns: Vec<String> = Vec::new();
        // the running user's own home first, so non-standard
        // locations are still caught.
        if let Some(home) = dirs::home_dir() {
            let home = home.to_string_lossy();
            if home.len() > 1 {
                patterns.push(regex::escape(&home));
            }
        }
        patterns.push(r#"/home/[^/\\\s"']+"#.to_string());
        patterns.push(r#"/Users/[^/\\\s"']+"#.to_string());
        patterns.push(r#"[A-Za-z]:[\\/]Users[\\/][^\\/\s"']+"#.to_string());

        Rules {
            email: Regex::new(
                r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
            )
            .expect("email regex is valid"),
            homes: patterns
                .into_iter()
                .map(|p| Regex::new(&p).expect("home regex is valid"))
                .collect(),
        }
    })
}

/// redact emails and home paths from a line of sidecar output.
pub fn redact(text: &str) -> String {
    let r = rules();
    let mut out = r.email.replace_all(text, REDACTED_EMAIL).into_owned();
    for home in &r.homes {
        out = home.replace_all(&out, "~").into_owned();
    }
    out
}

#[cfg(test)]
mod tests {
    use super::redact;

    #[test]
    fn scrubs_emails() {
        assert_eq!(
            redact("login failed for alice@example.org here"),
            "login failed for <redacted-email> here",
        );
    }

    #[test]
    fn scrubs_generic_home_paths() {
        assert_eq!(redact("opened /home/alice/evidence.mp4"), "opened ~/evidence.mp4");
        assert_eq!(
            redact("opened /Users/bob/case.zip"),
            "opened ~/case.zip",
        );
    }

    #[test]
    fn leaves_ordinary_text_untouched() {
        let s = "processing asset 42 at stage transcode";
        assert_eq!(redact(s), s);
    }
}
