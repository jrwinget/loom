// resolution of the onedir sidecar launcher. the backend ships as
// a pyinstaller --onedir tree under tauri's resource dir
// (loom-backend/loom-backend + loom-backend/_internal/); externalBin
// cannot carry a directory, so the shell resolves and spawns the
// inner binary itself. pure functions here, probing wrapper at the
// call site — tests cover the layout contract without an AppHandle.

use std::path::{Path, PathBuf};

// the directory name the ci stage step copies the dist tree to, and
// the binary name pyinstaller emits inside it. the deb layout assert
// and the smoke invocation in .github/workflows/desktop.yml assume
// the same pair — change together.
pub const SIDECAR_DIR: &str = "loom-backend";

pub fn sidecar_binary_name() -> &'static str {
    if cfg!(windows) {
        "loom-backend.exe"
    } else {
        "loom-backend"
    }
}

pub fn sidecar_path_in(resource_dir: &Path) -> PathBuf {
    resource_dir.join(SIDECAR_DIR).join(sidecar_binary_name())
}

// first existing candidate wins; the error names every probed path
// so a boot failure in the error panel says exactly where the shell
// looked instead of a bare "not found".
pub fn resolve_from_candidates(
    candidates: &[PathBuf],
) -> Result<PathBuf, String> {
    for candidate in candidates {
        if candidate.is_file() {
            return Ok(candidate.clone());
        }
    }
    let probed: Vec<String> = candidates
        .iter()
        .map(|c| c.display().to_string())
        .collect();
    Err(format!(
        "loom-backend binary not found; probed: {}",
        probed.join(", ")
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn joins_the_onedir_layout_under_the_resource_dir() {
        let path = sidecar_path_in(Path::new("/usr/lib/Loom"));
        let expected: PathBuf = if cfg!(windows) {
            ["/usr/lib/Loom", "loom-backend", "loom-backend.exe"]
                .iter()
                .collect()
        } else {
            ["/usr/lib/Loom", "loom-backend", "loom-backend"]
                .iter()
                .collect()
        };
        assert_eq!(path, expected);
    }

    #[test]
    fn tolerates_spaces_in_the_resource_dir() {
        let path = sidecar_path_in(Path::new("/Applications/My Apps/r"));
        assert!(path.starts_with("/Applications/My Apps/r"));
        assert!(path.ends_with(
            Path::new(SIDECAR_DIR).join(sidecar_binary_name())
        ));
    }

    #[test]
    fn resolves_the_first_existing_candidate() {
        let dir = tempdir().unwrap();
        let tree = dir.path().join(SIDECAR_DIR);
        std::fs::create_dir_all(&tree).unwrap();
        let real = tree.join(sidecar_binary_name());
        std::fs::write(&real, b"#!/bin/sh\n").unwrap();

        let missing = dir.path().join("elsewhere").join("loom-backend");
        let resolved = resolve_from_candidates(&[
            missing.clone(),
            sidecar_path_in(dir.path()),
        ])
        .expect("existing candidate must resolve");
        assert_eq!(resolved, real);
    }

    #[test]
    fn error_names_every_probed_path() {
        let a = PathBuf::from("/nope/one/loom-backend");
        let b = PathBuf::from("/nope/two/loom-backend");
        let err = resolve_from_candidates(&[a, b]).unwrap_err();
        assert!(err.contains("/nope/one/loom-backend"), "got: {err}");
        assert!(err.contains("/nope/two/loom-backend"), "got: {err}");
    }
}
