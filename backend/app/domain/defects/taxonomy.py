"""Extensible defect type taxonomy and default severity mapping.

Defect types are stored as VARCHAR; the registry is the single place to add
new types. See docs/development/adding-new-defect-type.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefectTypeDef:
    code: str
    display_name: str
    default_severity: int
    applicable_asset_types: tuple[str, ...]


_REGISTRY: dict[str, DefectTypeDef] = {}


def register_defect_type(definition: DefectTypeDef) -> None:
    _REGISTRY[definition.code] = definition


def get_defect_type(code: str) -> DefectTypeDef | None:
    return _REGISTRY.get(code)


def is_known_defect_type(code: str) -> bool:
    return code in _REGISTRY


def all_defect_types() -> list[DefectTypeDef]:
    return list(_REGISTRY.values())


register_defect_type(
    DefectTypeDef("missing_cover", "Отсутствующая крышка колодца", 5, ("telecom_well",))
)
register_defect_type(
    DefectTypeDef("damaged_cover", "Повреждённая крышка колодца", 4, ("telecom_well",))
)
register_defect_type(DefectTypeDef("well_subsidence", "Просадка колодца", 4, ("telecom_well",)))
register_defect_type(
    DefectTypeDef("cabinet_damage", "Повреждение корпуса шкафа", 3, ("telecom_cabinet",))
)
register_defect_type(
    DefectTypeDef("cabinet_door_open", "Открытая дверца шкафа", 3, ("telecom_cabinet",))
)
register_defect_type(DefectTypeDef("pole_tilt", "Наклон опоры", 4, ("pole",)))
register_defect_type(DefectTypeDef("pole_damage", "Повреждение опоры", 4, ("pole",)))
register_defect_type(DefectTypeDef("cable_break", "Обрыв кабеля", 5, ("cable_line", "pole")))
register_defect_type(
    DefectTypeDef("cable_sag", "Провисание кабельной линии", 3, ("cable_line", "pole"))
)
register_defect_type(DefectTypeDef("other", "Прочий дефект", 2, ()))
