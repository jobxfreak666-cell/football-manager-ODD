from __future__ import annotations

from tools.domain_errors import ValidationError
from tools.i18n_runtime import (
    DEFAULT_LOCALE,
    LocalizedMessage,
    MAIL_TEMPLATE_KEYS,
    mail_template_fields,
    normalize_locale,
    SUPPORTED_LOCALES,
)

import io
import json
import re
import fm_odds_web
from tools.i18n_runtime import MESSAGE_CATALOGS
from tools.preferred_moves import PreferredMoveStateError
from tools.player_departure_messages import MESSAGES as PLAYER_DEPARTURE_MESSAGES


def _handler(locale: str | None = None, *, app_locale: str | None = None) -> fm_odds_web.Handler:
    handler = fm_odds_web.Handler.__new__(fm_odds_web.Handler)
    handler.headers = {}
    if locale:
        handler.headers["Accept-Language"] = locale
    if app_locale:
        handler.headers["X-FMODD-Locale"] = app_locale
    return handler


def test_unknown_locale_and_missing_key_fall_back_to_authoritative_english() -> None:
    assert normalize_locale("it-IT,it;q=0.9") == DEFAULT_LOCALE
    assert LocalizedMessage("error.resource_not_found", {"resource": "Club"}).render(
        "it-IT",
    ) == "Club was not found."
    assert LocalizedMessage("error.unknown").render("zh-CN") == (
        "The request could not be completed."
    )
    assert normalize_locale("en") == "en-GB"
    assert normalize_locale("en_GB") == "en-GB"
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh_CN") == "zh-CN"
    assert normalize_locale("zh-Hans") == "zh-CN"
    for removed_locale in (
        "zh-TW", "zh-TW,zh;q=0.9", "zh-Hant", "zh-Hant-TW", "zh_Hant_TW",
        "ko-KR", "de-DE", "es-ES",
        "fr-FR", "ru-RU", "ja-JP", "pt-BR", "pt-PT",
    ):
        assert normalize_locale(removed_locale) == DEFAULT_LOCALE


def test_api_catalog_keys_and_parameters_match_across_locales() -> None:
    assert set(SUPPORTED_LOCALES) == {"en-GB", "zh-CN"}
    assert set(MESSAGE_CATALOGS) == set(SUPPORTED_LOCALES)
    key_sets = {locale: set(catalog) for locale, catalog in MESSAGE_CATALOGS.items()}
    assert all(keys == key_sets["en-GB"] for keys in key_sets.values())
    for key in key_sets["en-GB"]:
        placeholders = {
            locale: set(re.findall(r"\{([A-Za-z0-9_]+)\}", catalog[key]))
            for locale, catalog in MESSAGE_CATALOGS.items()
        }
        assert all(value == placeholders["en-GB"] for value in placeholders.values()), key


def test_localized_message_interpolates_factual_parameters() -> None:
    assert LocalizedMessage(
        "error.resource_not_found", {"resource": "Team Aurora"},
    ).render("en-GB") == "Team Aurora was not found."


def test_removed_locale_messages_render_in_english() -> None:
    assert LocalizedMessage("error.service_unavailable").render("ko-KR") == (
        "The local service is temporarily unavailable. Please try again."
    )
    assert LocalizedMessage("error.service_unavailable").render("zh-TW") == (
        "The local service is temporarily unavailable. Please try again."
    )


def test_player_departure_messages_only_publish_supported_locales() -> None:
    assert set(PLAYER_DEPARTURE_MESSAGES) == {"en-GB", "zh-CN"}


def test_explicit_app_locale_overrides_browser_accept_language() -> None:
    handler = _handler("zh-CN", app_locale="ko-KR")
    payload = handler._localized_error_payload(
        RuntimeError("diagnostic only"), operation="/api/funds",
    )
    assert payload["message"] == (
        "The local service is temporarily unavailable. Please try again."
    )


def test_localized_api_error_preserves_legacy_fields() -> None:
    error = ValidationError(
        "原有客户端错误文本", code="invalid_money", phase="validate_money",
        details={"field": "amount"},
    )

    payload = _handler()._localized_error_payload(error, operation="/api/funds")

    assert payload["error"] == "原有客户端错误文本"
    assert payload["error_code"] == "invalid_money"
    assert payload["error_phase"] == "validate_money"
    assert payload["retryable"] is False
    assert payload["details"] == {"field": "amount"}
    assert payload["message"] == "The request is invalid."
    assert payload["message_key"] == "error.invalid_request"
    assert payload["message_params"] == {}


def test_localized_message_never_renders_raw_exception_text() -> None:
    raw_exception = RuntimeError("database password=do-not-expose")

    payload = _handler("ko-KR")._localized_error_payload(
        raw_exception, operation="/api/funds",
    )

    assert payload["error"] == "database password=do-not-expose"
    assert "database password" not in payload["message"]
    assert "database password" not in payload["message_key"]
    assert "database password" not in str(payload["message_params"])
    assert payload["message"] == "The local service is temporarily unavailable. Please try again."


def test_domain_errors_carry_semantic_message_metadata() -> None:
    error = ValidationError(
        "legacy diagnostic", message_key="error.resource_not_found",
        message_params={"resource": "Club"},
    )
    payload = error.payload()
    assert payload["message_key"] == "error.resource_not_found"
    assert payload["message_params"] == {"resource": "Club"}


def test_preferred_move_state_uses_stable_codes_and_localized_messages() -> None:
    error = PreferredMoveStateError("learn")
    payload = _handler(app_locale="ko-KR")._localized_error_payload(
        error, operation="/api/training/run",
    )

    assert error.already_satisfied is True
    assert payload["error_code"] == "preferred_move_already_known"
    assert payload["error_phase"] == "validate_state"
    assert payload["details"] == {"operation": "learn", "already_satisfied": True}
    assert payload["message_key"] == "training.preferred_move.already_known"
    assert payload["message"] == "The player already has this preferred move."


def test_new_mail_metadata_uses_stable_versioned_semantic_keys() -> None:
    fields = mail_template_fields(
        "manager_salary", {"date": "2028-02-01", "amount": 1250.0},
    )

    assert fields == {
        "title_key": "mail.type.manager_salary.title",
        "message_key": "mail.type.manager_salary.message",
        "template_key": "mail.type.manager_salary.message",
        "template_version": 1,
        "template_params": {"date": "2028-02-01", "amount": 1250.0},
    }
    assert "sponsorship_payment" in MAIL_TEMPLATE_KEYS
    assert mail_template_fields("legacy_unknown", {"value": 1}) == {}


def test_legacy_handcrafted_http_errors_gain_safe_localized_metadata() -> None:
    handler = _handler("en-GB", app_locale="ko-KR")
    handler.command = "GET"
    handler.headers["Accept-Encoding"] = ""
    handler.wfile = io.BytesIO()
    handler.send_response = lambda _status: None
    handler.send_header = lambda _name, _value: None
    handler.end_headers = lambda: None

    handler._json(fm_odds_web.HTTPStatus.NOT_FOUND, {"error": "내부 raw 中文"})

    payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert payload["error"] == "내부 raw 中文"
    assert payload["message"] == "The requested resource was not found."
    assert payload["message_key"] == "error.not_found"
