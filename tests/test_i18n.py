from tms.i18n import (
    SUPPORTED_LANGUAGES,
    all_category_labels,
    available_languages,
    get_str,
    load_catalog,
    normalize_language,
    stop_cause,
)


def test_supported_languages():
    assert available_languages() == list(SUPPORTED_LANGUAGES)
    assert set(SUPPORTED_LANGUAGES) == {"en", "pt", "ja", "zh-cn", "zh-tw", "ko"}


def test_normalize_language():
    assert normalize_language("pt") == "pt"
    assert normalize_language("xx") == "en"
    assert normalize_language(None) == "en"


def test_get_str_fallbacks_like_legacy():
    assert get_str("SHIFT_REPORT", "en") == "Shift Report"
    assert get_str("MENU", "pt") == "Menu"
    assert get_str("_DOES_NOT_EXIST_", "en") == "!!_DOES_NOT_EXIST_!!"


def test_catalogs_have_all_sections():
    for lang in SUPPORTED_LANGUAGES:
        catalog = load_catalog(lang)
        assert set(catalog) == {"ui", "stop_cause_jat710", "stop_cause_lwt710"}
        assert catalog["ui"]
        assert catalog["stop_cause_jat710"]
        assert catalog["stop_cause_lwt710"]


def test_category_labels_all_languages():
    for lang in SUPPORTED_LANGUAGES:
        labels = all_category_labels(lang)
        assert len(labels) == 12
        assert all(v and not v.startswith("!!") for v in labels.values())


def test_stop_cause_known_and_fallback():
    assert stop_cause("0000", "JAT710", "en") == "WARP STOP"
    assert stop_cause("0001", "JAT710", "en") == "WASTE-SELVAGE STOP"
    # desconhecido cai em OTHER_STOP do tipo
    assert stop_cause("9999", "JAT", "en") == "Other Stop"
    # tipo desconhecido
    assert stop_cause("0000", "XYZ", "en") == "Undefined Message"


def test_stop_cause_localized():
    assert stop_cause("0000", "JAT", "ja") != stop_cause("0000", "JAT", "en")
    assert stop_cause("2100", "LWT710", "pt") != "Undefined Message"
