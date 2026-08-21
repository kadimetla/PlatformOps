import pytest
from pydantic import ValidationError

from interaction.dynamic_ui import DynamicCardSpec, DynamicChoice, compile_dynamic_card


def test_compiles_dynamic_card_to_allowed_a2ui_components():
    spec = DynamicCardSpec(
        title="Input needed",
        message="Provide static website details.",
        help_texts=["Example: s3://releases/invoices-ui.tar.gz"],
        choices=[DynamicChoice(label="Use CloudFront URL", value="cloudfront")],
    )

    components = compile_dynamic_card(spec, surface_id="surface-1")

    assert [component["component"] for component in components] == [
        "Card",
        "Column",
        "Text",
        "Text",
        "Text",
        "Text",
        "Button",
    ]
    root = components[0]
    assert root == {"id": "root", "component": "Card", "child": "content"}
    button = next(component for component in components if component["component"] == "Button")
    assert button["action"] == {
        "event": {"name": "surface-1", "context": {"selected_choice": "cloudfront"}}
    }


def test_dynamic_card_rejects_raw_html_like_text():
    with pytest.raises(ValidationError, match="raw HTML"):
        DynamicCardSpec(
            title="Input needed",
            message="<script>alert(1)</script>",
        )
