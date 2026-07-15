// validation and recovery helpers for the bootstrap secrets store.
// the store file deliberately survives factory reset and data-dir
// deletion, so a corrupt file or value used to brick boot with no
// user-reachable remedy. these helpers let the shell detect the
// damage, move the evidence aside, and regenerate — at the cost of
// one forced re-login (the secret key only signs jwts; nothing at
// rest is encrypted with it).

use std::path::{Path, PathBuf};

// mirror of the backend's validate_secret_key() floor
// (backend/src/loom/config.py, _MIN_SECRET_LENGTH = 32). hex is not
// required — over-constraining here would rotate values the backend
// happily accepts. surrounding whitespace marks a mangled write, not
// a usable secret.
pub fn is_valid_secret(value: &str) -> bool {
    let trimmed = value.trim();
    trimmed == value && trimmed.len() >= 32
}

// move an unreadable store file to a timestamped .bak sibling so a
// fresh store can take its place. never clobbers an earlier backup:
// the file is forensic evidence of what went wrong.
pub fn backup_corrupt_store(path: &Path) -> Result<PathBuf, String> {
    let file_name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or_else(|| format!("{} has no file name", path.display()))?;
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let mut candidate =
        path.with_file_name(format!("{file_name}.corrupt-{ts}.bak"));
    let mut counter = 1u32;
    while candidate.exists() {
        candidate = path.with_file_name(format!(
            "{file_name}.corrupt-{ts}-{counter}.bak"
        ));
        counter += 1;
    }
    std::fs::rename(path, &candidate)
        .map_err(|e| format!("failed to move corrupt store aside: {e}"))?;
    Ok(candidate)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn valid_secrets_meet_the_backend_floor() {
        assert!(is_valid_secret(&"a".repeat(32)));
        assert!(is_valid_secret(
            "0123456789abcdef0123456789abcdef0123456789abcdef"
        ));
        // non-hex but long enough: the backend accepts it, so must we
        assert!(is_valid_secret(&"secret-with-dashes-".repeat(3)));
    }

    #[test]
    fn invalid_secrets_are_rejected() {
        assert!(!is_valid_secret(""));
        assert!(!is_valid_secret("too-short"));
        assert!(!is_valid_secret(&"a".repeat(31)));
        // whitespace padding marks a mangled write
        assert!(!is_valid_secret(&format!(" {} ", "a".repeat(32))));
        assert!(!is_valid_secret(&format!("{}\n", "a".repeat(32))));
    }

    #[test]
    fn backup_moves_the_file_aside() {
        let dir = tempdir().unwrap();
        let store = dir.path().join("secrets.json");
        std::fs::write(&store, b"{not json").unwrap();

        let backup = backup_corrupt_store(&store).unwrap();

        assert!(!store.exists());
        assert!(backup.exists());
        let name = backup.file_name().unwrap().to_str().unwrap();
        assert!(name.starts_with("secrets.json.corrupt-"));
        assert!(name.ends_with(".bak"));
        assert_eq!(std::fs::read(&backup).unwrap(), b"{not json");
    }

    #[test]
    fn backup_never_clobbers_an_earlier_backup() {
        let dir = tempdir().unwrap();
        let store = dir.path().join("secrets.json");

        std::fs::write(&store, b"first").unwrap();
        let first = backup_corrupt_store(&store).unwrap();
        std::fs::write(&store, b"second").unwrap();
        let second = backup_corrupt_store(&store).unwrap();

        assert_ne!(first, second);
        assert_eq!(std::fs::read(&first).unwrap(), b"first");
        assert_eq!(std::fs::read(&second).unwrap(), b"second");
    }

    #[test]
    fn backup_errors_on_missing_file() {
        let dir = tempdir().unwrap();
        let missing = dir.path().join("secrets.json");
        assert!(backup_corrupt_store(&missing).is_err());
    }
}
