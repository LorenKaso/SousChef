from app.main import sample_recipes


def test_sample_recipes_cover_multiple_section_based_templates() -> None:
    recipes = sample_recipes()

    assert len(recipes) == 3

    titles = {recipe.title for recipe in recipes}
    assert titles == {
        "Basic Pancakes",
        "Birthday Chocolate Cake",
        "Mushroom Cream Pasta",
    }

    for recipe in recipes:
        assert recipe.sections
        assert all(section.name for section in recipe.sections)
        assert all(section.ingredients or section.steps for section in recipe.sections)


def test_sample_recipe_section_names_match_expected_templates() -> None:
    recipes_by_id = {recipe.id: recipe for recipe in sample_recipes()}

    assert [section.name for section in recipes_by_id["recipe-basic-pancakes"].sections] == [
        "Batter",
        "Cooking",
    ]
    assert [
        section.name for section in recipes_by_id["recipe-birthday-chocolate-cake"].sections
    ] == [
        "Cake",
        "Topping",
    ]
    assert [section.name for section in recipes_by_id["recipe-mushroom-cream-pasta"].sections] == [
        "Pasta",
        "Sauce and Serving",
    ]
