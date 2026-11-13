# Fix (production incident): Layer A guard that the Docker image contains every runtime package.
# The app failed in production because quality/ and prompts/ were never copied into the image, and the
# health check couldn't notice. This test catches a missing package before anything is pushed.

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_ENTRY = ROOT / "app.py"
DATA_DIRS = {"prompts"}  # runtime data folders (not Python packages) the app reads


def _copied_paths() -> set[str]:
    """Top-level files/dirs copied by the Dockerfile AND allow-listed in .dockerignore."""
    copied = set()
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("COPY ") and "requirements" not in line:
            copied.update(p.rstrip("/") for p in line.split()[1:-1])
    allowed = {m.group(1).rstrip("/") for m in re.finditer(r"^!(\S+)", (ROOT / ".dockerignore").read_text(
        encoding="utf-8"), flags=re.M)}
    return copied & allowed


def _local_runtime_imports() -> set[str]:
    """Top-level local modules/packages reachable from app.py by following imports."""
    local = {p.stem for p in ROOT.glob("*.py")} | {p.name for p in ROOT.iterdir() if (p / "__init__.py").exists()}
    seen, todo = set(), [APP_ENTRY]
    while todo:
        path = todo.pop()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else []
            for name in names:
                top = name.split(".")[0]
                if top in local and name not in seen:
                    seen.add(name)
                    target = ROOT / (name.replace(".", "/") + ".py")
                    pkg = ROOT / name.replace(".", "/") / "__init__.py"
                    todo += [p for p in (target, pkg) if p.exists()]
    return {n.split(".")[0] for n in seen}


def test_every_runtime_package_is_in_the_image():
    copied = _copied_paths()
    needed = {m if (ROOT / m).is_dir() else f"{m}.py" for m in _local_runtime_imports()} | DATA_DIRS
    missing = sorted(needed - copied)
    assert not missing, f"Missing from the Docker image (Dockerfile COPY + .dockerignore '!'): {missing}"


def test_image_never_contains_secrets_or_dev_folders():
    copied = _copied_paths()
    assert not copied & {".env", "tests", "evals", "plan", "deploy", ".git"}
