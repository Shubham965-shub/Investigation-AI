"""
PromptRegistry — YAML-backed prompt versioning.

Prompts live in src/prompts/<group>/<name>.yaml.
Each file holds all versions; one version is marked active.
The registry caches active templates in memory and provides
read/write methods used by both nodes and the API.

Git history of the YAML files is the full audit trail.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class _PromptDumper(yaml.SafeDumper):
    """Plain yaml.dump() picks PyYAML's default scalar style for every
    string, which for anything containing a newline is a double-quoted,
    backslash-wrapped mess — not the clean `template: |` block style every
    hand-authored prompt file in this directory actually uses. Multi-line
    strings are dumped in literal block style here so a saved file reads
    the same way regardless of whether it was hand-written or written by
    this module (2026-09-02 — found after a migration went through
    create_version()/_save_file() and produced escaped, line-wrapped
    prompt text instead of matching the existing convention)."""


def _str_presenter(dumper: yaml.Dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_PromptDumper.add_representer(str, _str_presenter)


def _prompt_path(name: str) -> Path:
    """Map 'group/prompt_name' → src/prompts/group/prompt_name.yaml"""
    return PROMPTS_DIR / f"{name}.yaml"


def _load_file(name: str) -> dict:
    path = _prompt_path(name)
    if not path.exists():
        raise KeyError(f"Prompt file not found: {path}")
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _save_file(name: str, data: dict) -> None:
    path = _prompt_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f, Dumper=_PromptDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)


class PromptRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}  # name -> active template

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Pre-warm the cache for every YAML file found under src/prompts/."""
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        for yaml_path in PROMPTS_DIR.rglob("*.yaml"):
            name = yaml_path.relative_to(PROMPTS_DIR).with_suffix("").as_posix()
            try:
                self._load_into_cache(name)
            except Exception as e:
                logger.warning(f"Could not load prompt '{name}': {e}")
        logger.info(f"PromptRegistry ready — {len(self._cache)} prompts cached")

    # ------------------------------------------------------------------
    # Read (used by nodes)
    # ------------------------------------------------------------------

    def get(self, name: str) -> str:
        """Return the active template for *name*. Raises KeyError if missing."""
        if name not in self._cache:
            self._load_into_cache(name)
        return self._cache[name]

    def _load_into_cache(self, name: str) -> None:
        data = _load_file(name)
        active_key = data.get("active")
        versions = data.get("versions", {})
        if not active_key or active_key not in versions:
            raise KeyError(f"Prompt '{name}' has no valid active version (active={active_key!r})")
        self._cache[name] = versions[active_key]["template"]

    def _invalidate(self, name: str) -> None:
        self._cache.pop(name, None)

    # ------------------------------------------------------------------
    # Read (used by API)
    # ------------------------------------------------------------------

    def list_prompts(self) -> list[dict]:
        results = []
        for yaml_path in sorted(PROMPTS_DIR.rglob("*.yaml")):
            name = yaml_path.relative_to(PROMPTS_DIR).with_suffix("").as_posix()
            data = _load_file(name)
            versions = data.get("versions", {})
            results.append({
                "name": name,
                "active_version": data.get("active"),
                "total_versions": len(versions),
            })
        return results

    def list_versions(self, name: str) -> list[dict]:
        data = _load_file(name)
        active_key = data.get("active")
        return [
            {
                "version": key,
                "description": v.get("description", ""),
                "created_at": v.get("created_at", ""),
                "is_active": key == active_key,
                "template": v["template"],
            }
            for key, v in data.get("versions", {}).items()
        ]

    def get_version(self, name: str, version: str) -> dict:
        data = _load_file(name)
        versions = data.get("versions", {})
        if version not in versions:
            raise KeyError(f"Prompt '{name}' version '{version}' not found")
        v = versions[version]
        return {
            "name": name,
            "version": version,
            "description": v.get("description", ""),
            "created_at": v.get("created_at", ""),
            "is_active": data.get("active") == version,
            "template": v["template"],
        }

    # ------------------------------------------------------------------
    # Write (used by API)
    # ------------------------------------------------------------------

    def create_version(
        self, name: str, template: str, description: Optional[str] = None
    ) -> dict:
        """Append a new version (not yet active). Version key = vN+1."""
        # Trailing whitespace on any line silently defeats _PromptDumper's
        # literal block style — PyYAML's emitter refuses `|` style for a
        # scalar with trailing space on a line and falls back to a
        # double-quoted, backslash-wrapped mess instead (found 2026-09-02,
        # after a migration produced 6 such files out of 35). Trailing
        # whitespace has no effect on an LLM's reading of the prompt, so
        # stripping it per-line here is safe and keeps every saved prompt
        # in the same clean block style regardless of what was pasted in.
        template = "\n".join(line.rstrip() for line in template.split("\n"))
        try:
            data = _load_file(name)
        except KeyError:
            data = {"active": None, "versions": {}}

        versions = data.get("versions", {})
        # Derive next version number from existing keys (v1, v2, …)
        existing_nums = [
            int(k[1:]) for k in versions if k.startswith("v") and k[1:].isdigit()
        ]
        next_num = max(existing_nums, default=0) + 1
        new_key = f"v{next_num}"

        versions[new_key] = {
            "description": description or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "template": template,
        }
        data["versions"] = versions
        _save_file(name, data)
        logger.info(f"Created prompt '{name}' {new_key}")
        return self.get_version(name, new_key)

    def activate_version(self, name: str, version: str) -> None:
        """Set *version* as the active one and update the YAML file."""
        data = _load_file(name)
        if version not in data.get("versions", {}):
            raise KeyError(f"Prompt '{name}' version '{version}' not found")
        data["active"] = version
        _save_file(name, data)
        self._invalidate(name)
        logger.info(f"Activated prompt '{name}' {version}")
