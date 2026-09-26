from pathlib import Path


COMPOSE = Path(__file__).parents[1] / "docker-compose.qa-targets.yml"


def test_authorized_target_images_are_explicitly_versioned():
    source = COMPOSE.read_text(encoding="utf-8")
    assert "bkimminich/juice-shop:v20.2.0" in source
    assert "webgoat/webgoat:v2026.4" in source
    assert "webgoat/webgoat:2026" not in source
