from pathlib import Path

import yaml


def _frontmatter(path: Path):
    text = path.read_text()
    _, frontmatter, _ = text.split("---", 2)
    return yaml.safe_load(frontmatter)


def test_provision_infra_allowed_tools_uses_adk_string_schema():
    metadata = _frontmatter(Path("skills/provision-infra/SKILL.md"))

    allowed_tools = metadata["allowed-tools"]

    assert isinstance(allowed_tools, str)
    assert "mcp__aws_iac__validate_cloudformation_template" in allowed_tools.split()
