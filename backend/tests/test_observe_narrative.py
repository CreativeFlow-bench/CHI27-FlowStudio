from app.api.sandbox import (
    _humanize_observe_fallback,
    _is_mesh_jargon,
    _is_object_state_narrative,
    _scrub_observe_narrative,
)


def test_observe_fallback_describes_the_object_not_camera_actions() -> None:
    assert _humanize_observe_fallback("Mball.005", "Santa Head", ["Mball.005", "Cube.001"]) == "This is a Santa Head."
    assert _humanize_observe_fallback(None, "Santa Head", ["hat", "beard"]) == "This is a Santa Head."
    assert _humanize_observe_fallback("Sphere", "Sphere", ["Sphere"]) == "This is a 3D model."


def test_user_action_sentences_are_not_object_state() -> None:
    assert not _is_object_state_narrative(
        "You are holding the Santa head model and observing it carefully before taking any action."
    )
    assert _is_object_state_narrative(
        "This is a cute Santa Claus head with rounded, wrinkled clay-like features."
    )
    assert not _is_object_state_narrative(
        "This is a Christmas Santa Head with this part this part, Sphere."
    )


def test_observe_user_content_attaches_preview_image() -> None:
    from app.api.sandbox import _observe_user_content

    prompt = "Write one sentence."
    assert _observe_user_content(prompt, None) == prompt
    image = "data:image/jpeg;base64,abc"
    content = _observe_user_content(prompt, image)
    assert content[0]["text"] == prompt
    assert content[1]["image_url"]["url"] == image


def test_mesh_jargon_and_scrub_hide_blender_names() -> None:
    assert _is_mesh_jargon("Mball.005")
    assert _is_mesh_jargon("Cube.001")
    assert _is_mesh_jargon("Sphere")
    assert not _is_mesh_jargon("Santa hat")
    assert _scrub_observe_narrative("Santa Head Mball.005") == "Santa Head this part"
