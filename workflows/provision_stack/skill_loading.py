"""Vendored from google.adk.skills (_utils.py + models.py, google-adk
2.4.0) -- confirmed by direct source inspection to be pure pathlib/YAML
parsing with zero ADK runtime coupling (no Agent/Runner/Session
touched anywhere), so it doesn't need to depend on google-adk at all.
Public API (Frontmatter, Skill, list_skills_in_dir, load_skill_from_dir)
matches google.adk.skills' names exactly so gateway/skill_matching.py's
two import lines are the only thing that changes at cutover -- its own
matching logic (find_matching_skill_path/resolve_skill_candidates)
already treats these as plain data and needs no changes.

Local-directory loading only -- the GCS variants (_list_skills_in_gcs_dir,
_load_skill_from_gcs_dir) and zip-bytes loading
(_load_skill_from_zip_bytes) aren't used anywhere in this project and
are intentionally not vendored.

See openspec/changes/migrate-to-langgraph/design.md's "Vendor
list_skills_in_dir/load_skill_from_dir" decision.
"""
from __future__ import annotations

import logging
import pathlib
import re
import unicodedata
from typing import Any, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_KEBAB_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Frontmatter(BaseModel):
    """L1 skill content: metadata parsed from SKILL.md for skill discovery."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    allowed_tools: Optional[str] = Field(
        default=None, alias="allowed-tools", serialization_alias="allowed-tools"
    )
    metadata: dict[str, Any] = {}

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "adk_additional_tools" in v and not isinstance(v["adk_additional_tools"], list):
            raise ValueError("adk_additional_tools must be a list of strings")
        if "adk_inject_state" in v and not isinstance(v["adk_inject_state"], bool):
            raise ValueError("adk_inject_state must be a bool")
        return v

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = unicodedata.normalize("NFKC", v)
        if len(v) > 64:
            raise ValueError("name must be at most 64 characters")
        if not _KEBAB_NAME_PATTERN.match(v):
            raise ValueError(
                "name must be lowercase kebab-case (a-z, 0-9, hyphens), with no "
                "leading, trailing, or consecutive delimiters"
            )
        return v

    @field_validator("description")
    @classmethod
    def _validate_description(cls, v: str) -> str:
        if not v:
            raise ValueError("description must not be empty")
        if len(v) > 1024:
            raise ValueError(f"description must be at most 1024 characters. Description length: {len(v)}")
        return v

    @field_validator("compatibility")
    @classmethod
    def _validate_compatibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 500:
            raise ValueError("compatibility must be at most 500 characters")
        return v


class Script(BaseModel):
    """Wrapper for script content."""

    src: str

    def __str__(self) -> str:
        return self.src


class Resources(BaseModel):
    """L3 skill content: additional instructions, assets, and scripts."""

    references: dict[str, Union[str, bytes]] = {}
    assets: dict[str, Union[str, bytes]] = {}
    scripts: dict[str, Script] = {}

    def get_reference(self, reference_id: str) -> Optional[Union[str, bytes]]:
        return self.references.get(reference_id)

    def get_asset(self, asset_id: str) -> Optional[Union[str, bytes]]:
        return self.assets.get(asset_id)

    def get_script(self, script_id: str) -> Optional[Script]:
        return self.scripts.get(script_id)

    def list_references(self) -> list[str]:
        return list(self.references.keys())

    def list_assets(self) -> list[str]:
        return list(self.assets.keys())

    def list_scripts(self) -> list[str]:
        return list(self.scripts.keys())


class Skill(BaseModel):
    """Complete skill representation: frontmatter, instructions, resources."""

    frontmatter: Frontmatter
    instructions: str
    resources: Resources = Resources()

    @property
    def name(self) -> str:
        return self.frontmatter.name

    @property
    def description(self) -> str:
        return self.frontmatter.description


def _load_dir(directory: pathlib.Path) -> dict[str, str]:
    files = {}
    if directory.exists() and directory.is_dir():
        for file_path in directory.rglob("*"):
            if "__pycache__" in file_path.parts:
                continue
            if file_path.is_file():
                relative_path = file_path.relative_to(directory)
                try:
                    files[str(relative_path)] = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
    return files


def _parse_skill_md_content(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter (---)")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md frontmatter not properly closed with ---")
    frontmatter_str = parts[1]
    body = parts[2].strip()
    try:
        parsed = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    return parsed, body


def _parse_skill_md(skill_dir: pathlib.Path) -> tuple[dict, str, pathlib.Path]:
    if not skill_dir.is_dir():
        raise FileNotFoundError(f"Skill directory '{skill_dir}' not found.")
    skill_md = None
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists():
            skill_md = path
            break
    if skill_md is None:
        raise FileNotFoundError(f"SKILL.md not found in '{skill_dir}'.")
    content = skill_md.read_text(encoding="utf-8")
    parsed, body = _parse_skill_md_content(content)
    return parsed, body, skill_md


def read_skill_properties(skill_dir: Union[str, pathlib.Path]) -> Frontmatter:
    """Lightweight alternative to load_skill_from_dir when only metadata
    is needed, not instructions/resources."""
    skill_dir = pathlib.Path(skill_dir).resolve()
    parsed, _, _ = _parse_skill_md(skill_dir)
    return Frontmatter.model_validate(parsed)


def list_skills_in_dir(skills_base_path: Union[str, pathlib.Path]) -> dict[str, Frontmatter]:
    """List skills in a local directory -- cheap, frontmatter-only."""
    skills_base_path = pathlib.Path(skills_base_path).resolve()
    skills: dict[str, Frontmatter] = {}
    if not skills_base_path.is_dir():
        logging.warning("Skills base path '%s' is not a directory.", skills_base_path)
        return skills
    for skill_dir in sorted(skills_base_path.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_id = skill_dir.name
        try:
            frontmatter = read_skill_properties(skill_dir)
            if skill_id != frontmatter.name:
                raise ValueError(
                    f"Skill name '{frontmatter.name}' does not match directory name '{skill_id}'."
                )
            skills[skill_id] = frontmatter
        except (FileNotFoundError, ValueError, ValidationError) as e:
            logging.warning("Skipping invalid skill '%s' in directory '%s': %s", skill_id, skills_base_path, e)
    return skills


def load_skill_from_dir(skill_dir: Union[str, pathlib.Path]) -> Skill:
    """Load a complete skill from a directory."""
    skill_dir = pathlib.Path(skill_dir).resolve()
    parsed, body, _ = _parse_skill_md(skill_dir)
    frontmatter = Frontmatter.model_validate(parsed)
    if skill_dir.name != frontmatter.name:
        raise ValueError(
            f"Skill name '{frontmatter.name}' does not match directory name '{skill_dir.name}'."
        )
    references = _load_dir(skill_dir / "references")
    assets = _load_dir(skill_dir / "assets")
    raw_scripts = _load_dir(skill_dir / "scripts")
    scripts = {name: Script(src=content) for name, content in raw_scripts.items()}
    resources = Resources(references=references, assets=assets, scripts=scripts)
    return Skill(frontmatter=frontmatter, instructions=body, resources=resources)
