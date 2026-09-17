"""i18n simplificado. Strings completas migradas dos str_*.pm (Fase 4).

Aqui ficam apenas os rótulos da lógica central (categorias de parada, unidades);
o restante da interface será carregado de fontes de tradução no futuro.
"""

from __future__ import annotations

from typing import Dict

from tms.core.stopcodes import CATEGORY_KEYS, CATEGORY_LABELS

SUPPORTED_LANGUAGES = ("en", "pt", "ja", "zh-cn", "zh-tw", "ko")


def available_languages() -> list[str]:
    return list(SUPPORTED_LANGUAGES)


def category_label(key: str, lang: str = "en") -> str:
    labels = CATEGORY_LABELS.get(lang, CATEGORY_LABELS["en"])
    return labels.get(key, key)


def all_category_labels(lang: str = "en") -> Dict[str, str]:
    return {k: category_label(k, lang) for k in CATEGORY_KEYS}