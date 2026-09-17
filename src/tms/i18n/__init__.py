"""Internacionalização.

Catálogos migrados dos `common/str_*.pm` legados para
`i18n/translations/<lang>.json` (UTF-8). Cada catálogo tem três seções:

- ``ui``               — `load_str` (rótulos de interface)
- ``stop_cause_jat710`` — `load_stop_cause_str_jat710`
- ``stop_cause_lwt710``  — `load_stop_cause_str_lwt710`

O comportamento de fallback reproduz o legado (`common/TMSstr.pm`):

- idioma desconhecido/ausente → inglês;
- chave de UI inexistente → ``!!CHAVE!!``;
- código de parada inexistente → ``OTHER_STOP`` do tipo; tipo desconhecido →
  ``Undefined Message``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from tms.core.stopcodes import CATEGORY_KEYS, CATEGORY_LABELS

SUPPORTED_LANGUAGES = ("en", "zh-cn", "zh-tw", "ko", "ja", "pt")

DEFAULT_LANGUAGE = "en"

_TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"

_SECTION_KEYS = ("ui", "stop_cause_jat710", "stop_cause_lwt710")

# Categoria agregada → chave do catálogo de UI legado.
CATEGORY_LABEL_KEYS: Dict[str, str] = {
    "WARP_TOP_MISS": "WARP_TOP_MISS",
    "WARP_MISS": "WARP_MISS",
    "FALSE_SELVAGE_MISS": "FALSE_SELVAGE_MISS",
    "LENO_L_MISS": "LENO_L_MISS",
    "LENO_R_MISS": "LENO_R_MISS",
    "WEFT_MISS": "WEFT_MISS",
    "WARP_OUT": "WARP_OUT",
    "CLOTH_DOFFING": "CLOTH_DOFFING",
    "MANUAL_STOP": "MANUAL_STOP",
    "POWER_OFF": "POWER_OFF",
    "OTHER_STOP": "OTHER_STOP",
    "CC_BACK": "CC_REAR_MISS",
}

_STOP_CAUSE_SECTION = {
    "JAT": "stop_cause_jat710",
    "JAT710": "stop_cause_jat710",
    "LWT": "stop_cause_lwt710",
    "LWT710": "stop_cause_lwt710",
}


def available_languages() -> List[str]:
    return list(SUPPORTED_LANGUAGES)


def normalize_language(lang: str | None) -> str:
    if lang in SUPPORTED_LANGUAGES:
        return lang  # type: ignore[return-value]
    return DEFAULT_LANGUAGE


@lru_cache(maxsize=None)
def load_catalog(lang: str = DEFAULT_LANGUAGE) -> Dict[str, Dict[str, str]]:
    """Carrega (e cacheia) o catálogo do idioma, com fallback para inglês."""
    lang = normalize_language(lang)
    path = _TRANSLATIONS_DIR / f"{lang}.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return {section: data.get(section, {}) for section in _SECTION_KEYS}


def get_str(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Rótulo de interface. Ausente → ``!!KEY!!`` (como `TMSstr::get_str`)."""
    value = load_catalog(lang)["ui"].get(key)
    if value is not None:
        return value
    return f"!!{key}!!"


def category_label(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    lang = normalize_language(lang)
    lookup = CATEGORY_LABEL_KEYS.get(key, key)
    value = load_catalog(lang)["ui"].get(lookup)
    if value is not None:
        return value
    fallback = CATEGORY_LABELS.get(lang, CATEGORY_LABELS[DEFAULT_LANGUAGE])
    return fallback.get(key, key)


def all_category_labels(lang: str = DEFAULT_LANGUAGE) -> Dict[str, str]:
    return {k: category_label(k, lang) for k in CATEGORY_KEYS}


def stop_cause(code: str, mac_type: str = "JAT", lang: str = DEFAULT_LANGUAGE) -> str:
    """Texto do código de parada, espelhando `TMSstr::get_stop_cause`."""
    section = _STOP_CAUSE_SECTION.get((mac_type or "").upper())
    if section is None:
        return "Undefined Message"
    table = load_catalog(lang)[section]
    if code:
        value = table.get(code.lower())
        if value is not None:
            return value
    return table.get("OTHER_STOP", "Undefined Message")
