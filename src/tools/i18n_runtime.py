"""Small, dependency-free runtime helpers for stable API localization.

The API keeps its legacy ``error`` field while clients migrate to the
semantic ``message_key`` and ``message_params`` contract.  Rendered messages
always come from this registry; diagnostic error text is never interpolated
into a user-facing template.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


DEFAULT_LOCALE = "en-GB"
SUPPORTED_LOCALES = ("en-GB", "zh-CN")


MESSAGE_CATALOGS: dict[str, dict[str, str]] = {
    "en-GB": {
        "error.invalid_request": "The request is invalid.",
        "error.not_found": "The requested resource was not found.",
        "error.service_unavailable": "The local service is temporarily unavailable. Please try again.",
        "error.internal_error": "The server could not complete the request.",
        "error.numeric_overflow": "The supplied value is outside the supported range.",
        "error.request_failed": "The request could not be completed.",
        "error.resource_not_found": "{resource} was not found.",
        "integrity.waiver.mail_not_found": "This disciplinary penalty is no longer available. Refresh your mail and try again.",
        "integrity.waiver.unavailable": "This penalty can no longer be waived by payment.",
        "integrity.waiver.not_delivered": "This disciplinary notice has not been delivered yet.",
        "integrity.waiver.expired": "The payment deadline for this penalty has passed.",
        "integrity.waiver.insufficient_funds": "Your bank and betting wallet do not have enough funds to pay {amount}.",
        "referee_debt.mail_not_found": "This referee payment request is no longer available. Refresh your mail and try again.",
        "referee_debt.payment_unavailable": "This referee payment can no longer be completed because the penalty has already been enforced.",
        "referee_debt.payment_expired": "The deadline for this referee payment has passed.",
        "referee_debt.insufficient_funds": "Your bank and betting wallet do not have enough funds to pay {amount}.",
        "storage.migration.invalid_target": "The selected folder contains conflicting FMODD data or overlaps the current data folder. Choose another folder.",
        "storage.migration.failed": "FMODD could not copy your saved data. The original data is unchanged. Choose another folder or try again.",
        "storage.migration.busy": "FMODD is refreshing data. Wait for it to finish, then change the storage location.",
        "training.preferred_move.already_known": "The player already has this preferred move.",
        "training.preferred_move.not_known": "The player does not have this preferred move.",
    },
    "zh-CN": {
        "error.invalid_request": "请求无效。",
        "error.not_found": "未找到请求的资源。",
        "error.service_unavailable": "本地服务暂时不可用，请稍后重试。",
        "error.internal_error": "服务器无法完成该请求。",
        "error.numeric_overflow": "提供的数值超出了支持范围。",
        "error.request_failed": "无法完成该请求。",
        "error.resource_not_found": "未找到{resource}。",
        "integrity.waiver.mail_not_found": "该纪律处罚已不存在，请刷新邮件后重试。",
        "integrity.waiver.unavailable": "该处罚已不能通过缴款免除。",
        "integrity.waiver.not_delivered": "该纪律处罚通知尚未送达。",
        "integrity.waiver.expired": "该处罚的缴款期限已过。",
        "integrity.waiver.insufficient_funds": "银行与投注钱包余额不足，无法缴纳 {amount}。",
        "referee_debt.mail_not_found": "该裁判追债邮件已不存在，请刷新邮件后重试。",
        "referee_debt.payment_unavailable": "裁判追债处罚已经执行，无法再付款。",
        "referee_debt.payment_expired": "裁判追债的付款期限已过。",
        "referee_debt.insufficient_funds": "银行与投注钱包余额不足，无法支付 {amount}。",
        "storage.migration.invalid_target": "所选文件夹包含冲突的 FMODD 数据，或与当前数据目录重叠。请选择其他文件夹。",
        "storage.migration.failed": "FMODD 无法复制存档数据，原数据未被改动。请选择其他文件夹或重试。",
        "storage.migration.busy": "FMODD 正在刷新数据。请等待刷新完成后再更改存储位置。",
        "training.preferred_move.already_known": "球员已经拥有该个人习惯。",
        "training.preferred_move.not_known": "球员没有该个人习惯。",
    },
}


from tools.player_departure_messages import MESSAGES as DEPARTURE_MESSAGES
for _departure_locale, _departure_catalog in DEPARTURE_MESSAGES.items():
    MESSAGE_CATALOGS[_departure_locale].update(_departure_catalog)


ERROR_MESSAGE_KEYS = {
    "invalid_request": "error.invalid_request",
    "not_found": "error.not_found",
    "service_unavailable": "error.service_unavailable",
    "internal_error": "error.internal_error",
    "numeric_overflow": "error.numeric_overflow",
}

STATUS_MESSAGE_KEYS = {
    400: "error.invalid_request",
    404: "error.not_found",
    413: "error.invalid_request",
    503: "error.service_unavailable",
    500: "error.internal_error",
}


MAIL_TEMPLATE_KEYS: dict[str, dict[str, str]] = {
    "bet_profit": {
        "title_key": "mail.type.bet_profit.title",
        "message_key": "mail.type.bet_profit.message",
    },
    "manager_salary": {
        "title_key": "mail.type.manager_salary.title",
        "message_key": "mail.type.manager_salary.message",
    },
    "club_dividend": {
        "title_key": "mail.type.club_dividend.title",
        "message_key": "mail.type.club_dividend.message",
    },
    "bet_schedule_refund": {
        "title_key": "mail.type.schedule_refund.title",
        "message_key": "mail.type.schedule_refund.message",
    },
    "youth_plan_refund": {
        "title_key": "mail.type.youth_refund.title",
        "message_key": "mail.type.youth_refund.message",
    },
    "youth_plan_completed": {
        "title_key": "mail.type.youth_complete.title",
        "message_key": "mail.type.youth_complete.message",
    },
    "virus_rejection": {
        "title_key": "mail.type.virus_rejection.title",
        "message_key": "mail.type.virus_rejection.message",
    },
    "bankruptcy_relief": {
        "title_key": "mail.type.relief.title",
        "message_key": "mail.relief_paid",
    },
    "version_update_reward": {
        "title_key": "mail.type.reward.title",
        "message_key": "mail.type.reward.message",
    },
    "match_integrity": {
        "title_key": "mail.type.integrity.title",
        "message_key": "mail.type.integrity.message",
        "body_key": "mail.type.integrity.body",
    },
    "referee_integrity": {
        "title_key": "mail.type.referee_integrity.title",
        "message_key": "mail.type.referee_integrity.message",
        "body_key": "mail.type.referee_integrity.body",
    },
    "doping_integrity": {
        "title_key": "mail.type.doping_integrity.title",
        "message_key": "mail.type.doping_integrity.message",
        "body_key": "mail.type.doping_integrity.body",
    },
    "referee_apology": {
        "title_key": "mail.type.referee_apology.title",
        "message_key": "mail.type.referee_apology.message",
        "body_key": "mail.type.referee_apology.body",
    },
    "credit_default": {
        "title_key": "mail.type.credit_default.title",
        "message_key": "mail.type.credit_default.message",
    },
    "referee_debt": {
        "title_key": "mail.type.referee_debt.title",
        "message_key": "mail.type.referee_debt.message",
        "body_key": "mail.type.referee_debt.body",
    },
    "sponsorship_offer": {
        "title_key": "mail.type.sponsor_offer.title",
        "message_key": "mail.type.sponsor_offer.message",
    },
    "sponsorship_contract": {
        "title_key": "mail.type.sponsor_contract.title",
        "message_key": "mail.type.sponsor_contract.message",
    },
    "sponsorship_payment": {
        "title_key": "mail.type.sponsor_payment.title",
        "message_key": "mail.type.sponsor_payment.message",
    },
}


def mail_template_fields(
    mail_type: str, params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return stable localization metadata for a newly-created mail record.

    Producers keep their rendered legacy fields for older clients.  New clients
    replay the semantic keys with locale-aware formatting, while records that
    predate this contract remain untouched and continue to use their stored text.
    """
    keys = MAIL_TEMPLATE_KEYS.get(str(mail_type or ""), {})
    if not keys:
        return {}
    result: dict[str, Any] = {
        **keys,
        "template_version": 1,
        "template_params": dict(params or {}),
    }
    if "message_key" in keys:
        result["template_key"] = keys["message_key"]
    return result


def normalize_locale(locale: str | None) -> str:
    """Return a supported locale, accepting common HTTP language forms."""
    requested = str(locale or "").split(",", 1)[0].split(";", 1)[0].strip()
    if not requested:
        return DEFAULT_LOCALE
    requested_lower = requested.replace("_", "-").lower()
    if requested_lower.startswith(("zh-tw", "zh-hant")):
        return DEFAULT_LOCALE
    if requested_lower.startswith(("zh-cn", "zh-hans")):
        return "zh-CN"
    for supported in SUPPORTED_LOCALES:
        if requested_lower == supported.lower():
            return supported
    language = requested_lower.split("-", 1)[0]
    for supported in SUPPORTED_LOCALES:
        if language == supported.split("-", 1)[0].lower():
            return supported
    return DEFAULT_LOCALE


def message_key_for_error(error_code: str | None) -> str:
    """Return the established template key without deriving text from errors."""
    return ERROR_MESSAGE_KEYS.get(str(error_code or ""), "error.request_failed")


def message_key_for_status(status: int) -> str:
    """Return a safe generic message for a legacy HTTP error response."""
    return STATUS_MESSAGE_KEYS.get(int(status), "error.request_failed")


@dataclass(frozen=True)
class LocalizedMessage:
    """A semantic user message that can be rendered on the server or client."""

    key: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def render(self, locale: str | None = None) -> str:
        catalog = MESSAGE_CATALOGS.get(normalize_locale(locale), {})
        template = catalog.get(self.key) or MESSAGE_CATALOGS[DEFAULT_LOCALE].get(
            self.key,
            MESSAGE_CATALOGS[DEFAULT_LOCALE]["error.request_failed"],
        )
        try:
            return template.format_map(dict(self.params))
        except (KeyError, ValueError, TypeError):
            # Template failures must not surface implementation details.
            return template

    def payload(self, locale: str | None = None) -> dict[str, Any]:
        return {
            "message": self.render(locale),
            "message_key": self.key,
            "message_params": dict(self.params),
        }


def localized_error_payload(
    payload: Mapping[str, Any], *, locale: str | None = None,
    message_key: str | None = None,
    message_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Add the non-breaking localized-message contract to an error payload.

    ``error`` and all diagnostic fields are deliberately retained verbatim for
    existing callers.  The new ``message`` is rendered only from catalogued
    keys and caller-supplied factual parameters, never from exception text.
    """
    result = dict(payload)
    # Older DomainError instances may not have supplied a phase.  HTTP clients
    # can nevertheless rely on the new structured payload always carrying one.
    result.setdefault("error_phase", "unknown")
    key = str(message_key or result.get("message_key") or "").strip()
    if not key:
        key = message_key_for_error(str(result.get("error_code") or ""))
    params = message_params
    if params is None:
        existing_params = result.get("message_params")
        params = existing_params if isinstance(existing_params, Mapping) else {}
    result.update(LocalizedMessage(key, params).payload(locale))
    return result
