from app.services.conversion_catalog import catalog


def test_resolves_english_ingredient_alias() -> None:
    assert catalog.get_ingredient_key("flour") == "white_flour"


def test_resolves_hebrew_ingredient_alias() -> None:
    assert catalog.get_ingredient_key("\u05e7\u05de\u05d7") == "white_flour"


def test_resolves_english_unit_alias() -> None:
    assert catalog.get_unit_key("cups") == "cup"


def test_resolves_hebrew_unit_alias() -> None:
    assert catalog.get_unit_key("\u05db\u05d5\u05e1") == "cup"


def test_unknown_ingredient_returns_none() -> None:
    assert catalog.get_ingredient_key("not_a_real_ingredient") is None


def test_unknown_unit_returns_none() -> None:
    assert catalog.get_unit_key("not_a_real_unit") is None


def test_display_name_exists_for_known_ingredient() -> None:
    display_name = catalog.get_display_name("white_flour")
    assert display_name is not None
    assert display_name.strip() != ""


def test_ingredient_lookup_is_case_insensitive() -> None:
    assert catalog.get_ingredient_key("FLOUR") == "white_flour"


def test_unit_lookup_trims_whitespace() -> None:
    assert catalog.get_unit_key("  cups  ") == "cup"
