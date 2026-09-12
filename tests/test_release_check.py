from pathlib import Path

from scripts.check_release import ROOT_DIRS, ROOT_FILES, RULES, candidates


def scaffold(root):
    for name in ROOT_FILES:
        (root / name).touch()
    for name in ROOT_DIRS:
        (root / name).mkdir()


def test_candidate_list_excludes_private_and_personal_directories(tmp_path):
    scaffold(tmp_path)
    for name in (".secrets", ".acl-backups", ".idea", "data", ".venv"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "do-not-read.txt").touch()
    (tmp_path / "app" / "safe.py").touch()
    (tmp_path / "docs" / "private-notes").mkdir()
    (tmp_path / "docs" / "private-notes" / "README.original.md").touch()
    files, findings = candidates(tmp_path)
    assert not findings
    assert {p.relative_to(tmp_path).as_posix() for p in files} == {*ROOT_FILES, "app/safe.py"}


def test_unexpected_candidate_file_is_reported(tmp_path):
    scaffold(tmp_path)
    (tmp_path / "docs" / "accidental.key").touch()
    _, findings = candidates(tmp_path)
    assert findings == [{"path": "docs/accidental.key", "rule": "unexpected_candidate_file"}]


def test_obvious_secret_shapes_match_without_real_credentials():
    assert RULES["provider_key_pattern"].search("sk-" + "a" * 32)
    assert RULES["literal_secret_setting"].search('DEEPSEEK_API_KEY = "' + 'a' * 32 + '"')
    assert RULES["personal_windows_profile"].search(str(Path("C:/" + "Users/example/file")))
