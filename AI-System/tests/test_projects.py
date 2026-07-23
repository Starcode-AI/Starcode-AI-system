import pytest

from app.services.projects import parse_project_json, safe_relative_path


def test_project_json_parser_accepts_complete_object():
    data = parse_project_json('{"summary":"ok","files":[{"path":"README.md","content":"ready"}]}')
    assert data["files"][0]["path"] == "README.md"


@pytest.mark.parametrize("path", ["../secret.txt", "/root/file", ".env", "folder/.git/config"])
def test_unsafe_project_paths_are_blocked(path):
    with pytest.raises(ValueError):
        safe_relative_path(path)
