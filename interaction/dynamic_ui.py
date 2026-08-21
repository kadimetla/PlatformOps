"""Validated dynamic UI specs compiled to A2UI.

This is the safe middle ground between hard-coded frontend HTML and
unbounded LLM-generated DOM. A workflow may produce a small, typed UI
intent; PlatformOps validates it and compiles it into the known A2UI
basic catalog components the browser already supports.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class DynamicChoice(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=120)


class DynamicCardSpec(BaseModel):
    """A constrained card-like UI intent.

    The spec carries content and choice semantics only. It cannot name
    arbitrary components, set CSS, inject HTML, or attach executable code.
    """

    title: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1200)
    help_texts: list[str] = Field(default_factory=list, max_length=8)
    choices: list[DynamicChoice] = Field(default_factory=list, max_length=8)
    choice_response_field: str = Field(default="selected_choice", min_length=1, max_length=80)

    @model_validator(mode="after")
    def reject_html_like_text(self) -> "DynamicCardSpec":
        # The compiler only emits A2UI Text components, but the source of
        # these strings may later be an LLM. Keep this deliberately
        # conservative until we have a documented markdown sanitizer.
        values = [self.title, self.message, *self.help_texts]
        values.extend(choice.label for choice in self.choices)
        if any("<" in value or ">" in value for value in values):
            raise ValueError("dynamic UI text must not contain raw HTML")
        return self


def compile_dynamic_card(spec: DynamicCardSpec, *, surface_id: str) -> list[dict]:
    """Compile a DynamicCardSpec into A2UI basic-catalog components."""

    components: list[dict] = [
        {"id": "root", "component": "Card", "child": "content"},
        {"id": "title", "component": "Text", "text": spec.title, "variant": "h3"},
        {"id": "message", "component": "Text", "text": spec.message},
    ]
    content_children = ["title", "message"]

    for index, text in enumerate(spec.help_texts):
        component_id = f"help-{index}"
        components.append({"id": component_id, "component": "Text", "text": text})
        content_children.append(component_id)

    for index, choice in enumerate(spec.choices):
        label_id = f"choice-{index}-label"
        button_id = f"choice-{index}"
        components.append({"id": label_id, "component": "Text", "text": choice.label})
        components.append(
            {
                "id": button_id,
                "component": "Button",
                "child": label_id,
                "action": {
                    "event": {
                        "name": surface_id,
                        "context": {spec.choice_response_field: choice.value},
                    }
                },
            }
        )
        content_children.append(button_id)

    content = {
        "id": "content",
        "component": "Column",
        "children": content_children,
    }
    return [components[0], content, *components[1:]]
