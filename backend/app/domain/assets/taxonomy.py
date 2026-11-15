"""Extensible asset type taxonomy.

New asset types are added here (single registry) without DB schema changes:
the database stores asset_type as VARCHAR, validated against this registry
at the application boundary. See docs/development/adding-new-asset-type.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetTypeDef:
    code: str
    display_name: str
    impact_factor: float
    dedup_radius_m: float


_REGISTRY: dict[str, AssetTypeDef] = {}


def register_asset_type(definition: AssetTypeDef) -> None:
    _REGISTRY[definition.code] = definition


def get_asset_type(code: str) -> AssetTypeDef | None:
    return _REGISTRY.get(code)


def is_known_asset_type(code: str) -> bool:
    return code in _REGISTRY


def all_asset_types() -> list[AssetTypeDef]:
    return list(_REGISTRY.values())


register_asset_type(AssetTypeDef("telecom_well", "Кабельный колодец", 1.0, 10.0))
register_asset_type(AssetTypeDef("pole", "Опора", 0.8, 12.0))
register_asset_type(AssetTypeDef("telecom_cabinet", "Телекоммуникационный шкаф", 0.9, 8.0))
register_asset_type(AssetTypeDef("cable_line", "Кабельная линия", 0.7, 25.0))
register_asset_type(AssetTypeDef("other", "Прочий объект инфраструктуры", 0.5, 15.0))
