from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _normalize(value: str | None) -> str:
    """Normalize lookup inputs for stable alias matching."""
    if value is None:
        return ""
    return value.strip().lower()


class ConversionCatalog:
    """Loads and resolves bilingual ingredient/unit aliases from catalog JSON."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self._catalog_path = catalog_path or (base_dir / "data" / "conversions_bilingual.json")
        self._raw: dict[str, Any] = self._load_catalog()
        self._ingredient_aliases: dict[str, str] = {}
        self._unit_aliases: dict[str, str] = {}
        self._ingredient_data: dict[str, dict[str, Any]] = self._raw.get("ingredients", {})
        self._build_alias_maps()

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw

    def _load_catalog(self) -> dict[str, Any]:
        try:
            with self._catalog_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Conversion catalog file not found: {self._catalog_path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Malformed conversion catalog JSON: {self._catalog_path}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                f"Invalid conversion catalog structure (expected object): {self._catalog_path}"
            )
        return data

    def _map_alias(self, aliases: dict[str, str], alias: str | None, canonical: str) -> None:
        normalized = _normalize(alias)
        if normalized:
            aliases[normalized] = canonical

    def _build_alias_maps(self) -> None:
        ingredients = self._raw.get("ingredients", {})
        if isinstance(ingredients, dict):
            for key, entry in ingredients.items():
                if not isinstance(key, str):
                    continue
                self._map_alias(self._ingredient_aliases, key, key)
                if not isinstance(entry, dict):
                    continue

                self._map_alias(self._ingredient_aliases, entry.get("display_name_he"), key)
                self._map_alias(self._ingredient_aliases, entry.get("display_name_en"), key)

                for alias in entry.get("aliases_he", []):
                    self._map_alias(self._ingredient_aliases, alias, key)
                for alias in entry.get("aliases_en", []):
                    self._map_alias(self._ingredient_aliases, alias, key)

        aliases_units = self._raw.get("meta", {}).get("aliases_units", {})
        if isinstance(aliases_units, dict):
            for lang_map in aliases_units.values():
                if not isinstance(lang_map, dict):
                    continue
                for alias, canonical in lang_map.items():
                    if not isinstance(canonical, str):
                        continue
                    self._map_alias(self._unit_aliases, canonical, canonical)
                    if isinstance(alias, str):
                        self._map_alias(self._unit_aliases, alias, canonical)

    def get_ingredient_key(self, name: str) -> str | None:
        return self._ingredient_aliases.get(_normalize(name))

    def get_unit_key(self, unit: str) -> str | None:
        return self._unit_aliases.get(_normalize(unit))

    def get_ingredient_data(self, key: str) -> dict[str, Any] | None:
        data = self._ingredient_data.get(key)
        if isinstance(data, dict):
            return data
        return None

    def get_display_name(self, key: str) -> str | None:
        ingredient = self.get_ingredient_data(key)
        if ingredient is None:
            return None

        display_name_he = ingredient.get("display_name_he")
        if isinstance(display_name_he, str) and display_name_he.strip():
            return display_name_he

        display_name_en = ingredient.get("display_name_en")
        if isinstance(display_name_en, str) and display_name_en.strip():
            return display_name_en
        return None

    def has_ingredient(self, name: str) -> bool:
        return self.get_ingredient_key(name) is not None

    def has_unit(self, unit: str) -> bool:
        return self.get_unit_key(unit) is not None


catalog = ConversionCatalog()
