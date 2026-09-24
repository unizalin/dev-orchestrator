from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class ProjectIdentity:
    key: str
    label: str
    root: Path


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def resolve_project(cwd: Path) -> ProjectIdentity:
    resolved = cwd.expanduser().resolve()
    try:
        root = Path(run_git(resolved, "rev-parse", "--show-toplevel")).resolve()
        common = Path(
            run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve()
        label = run_git(root, "rev-parse", "--show-toplevel").rstrip("/").split("/")[-1]
        identity = f"git:{common}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        root = resolved
        label = root.name or "root"
        identity = f"path:{root}"
    return ProjectIdentity(sha256(identity.encode("utf-8")).hexdigest(), label, root)
