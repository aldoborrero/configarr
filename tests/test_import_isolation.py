import ast
import pathlib
import sys

# The nix-only generated API clients are bare top-level packages with these names;
# configarr talks to each service's HTTP API directly via requests and must never
# import them. (The provider modules live under configarr.providers.*, so a real
# `import radarr` is unambiguous.)
FORBIDDEN = {"radarr", "sonarr", "prowlarr", "bazarr", "sabnzbd"}
_PKG = pathlib.Path(__file__).parent.parent / "configarr"


def _forbidden_root(name: str | None) -> bool:
    return bool(name) and name.split(".")[0] in FORBIDDEN


def test_source_never_imports_generated_clients():
    # Static AST scan of the whole package — catches lazy/in-function imports that a
    # runtime sys.modules check (which only sees eagerly-imported modules) would miss.
    offenders: list[str] = []
    for py in _PKG.rglob("*.py"):
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{py.relative_to(_PKG)}: import {a.name}"
                    for a in node.names
                    if _forbidden_root(a.name)
                ]
            elif isinstance(node, ast.ImportFrom) and _forbidden_root(node.module):
                offenders.append(f"{py.relative_to(_PKG)}: from {node.module}")
    assert not offenders, f"configarr imports generated clients: {offenders}"


def test_importing_cli_does_not_pull_generated_clients():
    # Runtime backstop: importing the entrypoint must not eagerly load them either.
    import configarr.__main__  # noqa: F401

    leaked = FORBIDDEN & set(sys.modules)
    assert not leaked, f"configarr pulled forbidden modules: {sorted(leaked)}"
