"""O × da lista "Arquivos avulsos" (web_api/standalone.py)."""

from gf_ui_editor.project import Project
from gf_ui_editor.web_shell import WebApi

from test_standalone_document import files  # noqa: F401  (fixture)


def test_close_active_opens_next_standalone_then_project_file(files):  # noqa: F811
    game, projects, source, path = files
    project = Project.create("Project", source, game, projects, light=True)
    api = WebApi("pt_BR", False, default_ui_directory=game / "UI")
    api.open_project(str(project.root))
    other = path.with_name("Second.xml")
    other.write_bytes(path.read_bytes())
    state = api.open_dropped_xmls([str(path), str(other)])["state"]
    assert state["open_path"] == str(other)

    state = api.standalone_close(str(path))  # não é o aberto: só sai da lista
    assert state["standalone_paths"] == [str(other)] and state["open_path"] == str(other)

    api.open_dropped_xmls([str(path)])
    state = api.standalone_close(str(path))  # era o aberto: volta ao outro avulso
    assert state["standalone_paths"] == [str(other)] and state["open_path"] == str(other)

    state = api.standalone_close(str(other))  # último avulso: volta ao XML do projeto
    assert state["standalone_paths"] == []
    assert state["open_path"] in (None, str(project.ui_dir / "Window.xml"))


def test_close_without_project_leaves_nothing_open(files):  # noqa: F811
    game, _projects, _source, path = files
    api = WebApi("pt_BR", False, default_ui_directory=game / "UI")
    api.open_dropped_xmls([str(path)])
    state = api.standalone_close(str(path))
    assert state["standalone_paths"] == [] and state["open_path"] is None
