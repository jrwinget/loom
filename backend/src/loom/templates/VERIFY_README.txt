HOW TO VERIFY THIS EVIDENCE BUNDLE
==================================

Every file in this bundle was fingerprinted with SHA-256 when the
bundle was produced. The fingerprints are recorded in the file
MANIFEST.sha256. If any file is later altered, even by a single
byte, its fingerprint will no longer match.

You can check this yourself in a few minutes. You do NOT need to
install Loom (the software that produced the bundle), and none of
the options below send anything over the internet.

OPTION 1 — IN YOUR WEB BROWSER (NO INSTALLATION)
------------------------------------------------
1. Extract the bundle zip to a folder if you have not already.
2. Double-click verify.html (it opens in your web browser).
3. Click "Select the extracted bundle folder" and pick the folder.
4. Read the result: a green VERIFIED banner means every listed
   file matches; a red banner lists exactly which files are
   missing or altered.

The page works offline and uploads nothing. Any current version of
Chrome, Edge, Firefox, or Safari can check the file fingerprints.
Checking the optional cryptographic signature (see below) in the
browser additionally requires Chrome/Edge 137 or newer, Firefox
130 or newer, or Safari 17 or newer — older browsers will tell you
to use option 2 instead.

OPTION 2 — WITH PYTHON (ANY COMPUTER WITH PYTHON 3)
---------------------------------------------------
From a command prompt or terminal, run:

    python3 verify.py <path to the bundle folder or zip>

It prints one line per file and an overall OK or FAILED verdict.
It uses only what ships with Python — no packages to install.

OPTION 3 — STANDARD COMMAND-LINE TOOLS
--------------------------------------
From inside the extracted folder:

    sha256sum -c MANIFEST.sha256        (Linux)
    shasum -a 256 -c MANIFEST.sha256    (macOS)

ABOUT THE SIGNATURE (MANIFEST.sha256.sig)
-----------------------------------------
If the file MANIFEST.sha256.sig is present, the preparer also
signed the manifest with a private key. With the preparer's public
key (a small .pem file provided separately), you can confirm the
manifest itself was not replaced:

    openssl pkeyutl -verify -pubin -inkey <public-key.pem> \
        -rawin -in MANIFEST.sha256 -sigfile MANIFEST.sha256.sig

verify.html and verify.py can also check the signature (verify.py
needs the python "cryptography" package for this one step; it
prints the openssl command above if that package is missing).
A missing signature file is not an error — signing is optional.

WHAT THE RESULTS MEAN
---------------------
- All files match: the bundle contents are exactly as produced.
- MISMATCH: that file's bytes changed after the bundle was made.
- MISSING: a file listed in the manifest is not in the folder.
- UNLISTED: a file is present that the manifest does not cover
  (often harmless system files such as Thumbs.db, but review it).
