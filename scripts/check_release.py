"""Read-only candidate scan. Never traverse secrets, databases, or editor settings.

Heuristic checks are not a guarantee that every secret will be detected.
Only paths, rule names and line numbers are printed for findings, not contents.
"""
import argparse
import json
import re
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "README.en.md", "requirements.txt", "requirements-dev.txt", ".gitignore")
ROOT_DIRS = ("app", "tests", "scripts", "docs")
EXTENSIONS = {".py", ".ps1", ".js", ".cjs", ".css", ".html", ".md", ".svg", ".png"}
RULES = {
    "provider_key_pattern": re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,})\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "literal_secret_setting": re.compile(r'''(?:DEEPSEEK_API_KEY|GEMINI_API_KEY|AI_SECURE_DATA_KEY)\s*[:=]\s*["']([A-Za-z0-9_+/=-]{20,})["']'''),
    "personal_windows_profile": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\s\\/]+", re.I),
    "personal_windows_sid": re.compile(r"S-1-5-21-(?:\d+-){3}\d+"),
}


def candidates(root):
    result, problems = [], []
    def visit(path):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or path.is_junction():
            problems.append({"path": relative, "rule": "linked_path"})
            return
        if path.is_dir():
            if path.name in {"__pycache__", ".pytest_cache", "node_modules", ".secrets", ".acl-backups", "data", ".git"} or relative == "docs/private-notes":
                return
            for child in sorted(path.iterdir()):
                visit(child)
        elif path.is_file():
            if path.suffix in {".pyc", ".pyo"}:
                return
            if relative not in ROOT_FILES and path.suffix not in EXTENSIONS:
                problems.append({"path": relative, "rule": "unexpected_candidate_file"})
            else:
                result.append(path)
        else:
            problems.append({"path": relative, "rule": "missing_path"})
    for name in (*ROOT_FILES, *ROOT_DIRS):
        visit(root / name)
    return result, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List proposed publish files (no staging or upload)")
    args = parser.parse_args()
    files, findings = candidates(PROJECT)
    images = []
    for path in files:
        relative = path.relative_to(PROJECT).as_posix()
        if path.suffix == ".png":
            images.append(relative)  # Requires human visual review, no OCR guarantee.
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            findings.append({"path": relative, "rule": "unreadable_text"})
            continue
        for number, line in enumerate(content.splitlines(), 1):
            for rule, pattern in RULES.items():
                if pattern.search(line):
                    findings.append({"path": relative, "line": number, "rule": rule})
    output = {"candidate_count": len(files), "findings": findings,
              "images_requiring_visual_review": images,
              "scope": "Allowlisted working-tree candidates only; not git history, environment, secrets, or ignored data"}
    if args.list:
        output["candidates"] = [p.relative_to(PROJECT).as_posix() for p in files]
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
