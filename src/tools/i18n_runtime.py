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
        "training.error.submission_id_too_long": "The training request reference is too long.",
        "training.error.game_date_missing": "The current game date has not been read yet. Refresh and try again.",
        "training.error.account_missing": "FMODD has not identified the current account yet. Refresh and try again.",
        "training.error.current_team_missing": "FMODD has not identified your current club team. Refresh My Team and try again.",
        "training.error.current_team_only": "Training can only be arranged for your current club team.",
        "training.error.current_team_mismatch": "This request belongs to another team. Refresh My Team and submit the training again.",
        "training.error.first_team_only": "Only current first-team players can take this training.",
        "training.error.player_not_in_current_team": "The selected player does not belong to your current team. Refresh My Team and try again.",
        "training.error.player_not_in_current_club": "The selected player does not belong to your current club. Refresh My Team and try again.",
        "training.error.goalkeeper_equipment_only": "This training equipment is only available to goalkeepers.",
        "training.error.defender_equipment_only": "This training equipment is only available to defenders.",
        "training.error.staff_project_only": "This training project only supports coaching-licence courses.",
        "training.error.position_project_only": "The position training area only supports position familiarity training.",
        "training.error.habit_operation_required": "Choose whether to learn or unlearn this preferred move.",
        "training.error.habit_unsupported": "This training project does not support preferred-move training.",
        "training.error.attribute_direction_required": "Choose whether to increase or decrease the attribute.",
        "training.error.submission_id_required": "The training ground has been updated. Refresh the page and submit the training again.",
        "training.error.submission_id_conflict": "This training request reference was already used for another arrangement. Submit the training again.",
        "training.error.coach_not_in_current_club": "The selected coach does not belong to your current club. Refresh My Team and try again.",
        "training.error.staff_not_coach": "The selected staff member cannot take coaching-licence courses.",
        "training.error.coaching_license_maxed": "This coach already holds the highest coaching licence.",
        "training.error.coaching_license_changed": "The coach's licence has changed. Open the coaching desk again.",
        "training.error.coach_address_missing": "The coach or club address is unavailable. Refresh My Team and try again.",
        "training.error.position_unavailable": "The player's current position familiarity could not be read. Refresh and try again.",
        "training.error.position_maxed": "This position familiarity is already 20. No further training is needed.",
        "training.error.preferred_move_unverified": "This preferred-move reference has not been verified for the current game version.",
        "training.error.attribute_not_in_project": "The selected attribute is not available for this training equipment.",
        "training.error.attribute_missing": "The player does not have the selected training attribute.",
        "training.error.attribute_maxed": "This attribute is already 20 and cannot be trained further.",
        "training.error.attribute_minimum": "This attribute is already 1 and cannot be reduced further.",
        "training.error.attribute_id_unverified": "The selected attribute has not been verified for growth in this game version.",
        "training.error.attribute_changed": "{attribute} has changed. Reopen the training panel.",
        "training.error.ca_over_limit": "This training needs {ca_cost} CA and would push CA above 200.",
        "training.error.ca_over_pa_confirmation": "This training would push CA above PA and may trigger attribute reallocation. Confirm to continue.",
        "training.error.insufficient_funds": "Your bank and betting wallet do not have enough funds to pay for this training.",
        "training.error.growth_hook_sync_failed": "The training task was created, but the growth hook could not be synchronized. Refresh and try again.",
        "training.error.cancel_focus_required": "Select the training task to cancel.",
        "training.error.task_not_found": "This training task no longer exists. Refresh the training ground.",
        "training.error.task_not_active": "This person is no longer using this training equipment.",
        "training.error.equipment_route_retired": "The training ground has been redesigned. Buying, unlocking, placing, storing or selling training equipment is no longer supported. Refresh the training ground.",
        "training.error.project_not_found": "This training project does not exist. Refresh the training ground.",
        "training.error.project_retired": "This training project is no longer available. Refresh the training ground.",
        "training.error.project_mismatch": "The training project does not match the selected equipment. Refresh the training ground and try again.",
        "training.error.project_invalid": "The training project is invalid.",
        "training.error.duration_mode_invalid": "Choose a valid training duration.",
        "training.error.position_key_invalid": "The selected training position is invalid.",
        "training.error.player_task_exists": "This player already has an active training task.",
        "training.error.coach_task_exists": "This coach already has an active coaching course or combined training task.",
        "training.error.request_invalid": "The training request is invalid. Refresh the training ground and try again.",
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
        "training.error.submission_id_too_long": "训练请求编号过长。",
        "training.error.game_date_missing": "尚未读取当前游戏日期，请刷新后重试。",
        "training.error.account_missing": "尚未识别当前账户，请刷新后重试。",
        "training.error.current_team_missing": "尚未识别当前执教的俱乐部球队，请刷新我的队伍。",
        "training.error.current_team_only": "只能为当前执教的俱乐部球队安排训练。",
        "training.error.current_team_mismatch": "该请求属于其他球队，请刷新我的队伍后重新提交训练。",
        "training.error.first_team_only": "只能为当前一线队球员安排该训练，请刷新我的队伍。",
        "training.error.player_not_in_current_team": "所选球员不属于当前队伍，请刷新我的队伍。",
        "training.error.player_not_in_current_club": "所选球员不属于当前执教球队，请刷新我的队伍。",
        "training.error.goalkeeper_equipment_only": "门将训练器材只适用于门将。",
        "training.error.defender_equipment_only": "后卫训练器材只适用于后卫。",
        "training.error.staff_project_only": "该训练项目只支持教练考证。",
        "training.error.position_project_only": "位置训练场只支持位置熟练度训练。",
        "training.error.habit_operation_required": "请选择学习或戒除个人习惯。",
        "training.error.habit_unsupported": "该训练项目不支持个人习惯训练。",
        "training.error.attribute_direction_required": "请选择增加或减少属性。",
        "training.error.submission_id_required": "训练场已改版，请刷新页面后重新提交训练安排。",
        "training.error.submission_id_conflict": "训练请求编号已用于其他安排，请重新提交。",
        "training.error.coach_not_in_current_club": "所选教练不属于当前执教俱乐部，请刷新我的队伍。",
        "training.error.staff_not_coach": "所选职员当前不是可参加考证的教练。",
        "training.error.coaching_license_maxed": "该教练已经取得最高等级证书。",
        "training.error.coaching_license_changed": "教练证书已发生变化，请重新打开学习桌。",
        "training.error.coach_address_missing": "教练或俱乐部地址不可用，请刷新我的队伍。",
        "training.error.position_unavailable": "无法读取球员当前的位置熟练度，请刷新后重试。",
        "training.error.position_maxed": "该位置熟练度已经达到20，无需继续训练。",
        "training.error.preferred_move_unverified": "该个人习惯编号尚未在当前版本验证。",
        "training.error.attribute_not_in_project": "所选属性不属于该训练器材。",
        "training.error.attribute_missing": "该球员没有所选训练属性。",
        "training.error.attribute_maxed": "该属性已经达到20，无法继续专项训练。",
        "training.error.attribute_minimum": "该属性已经达到1，无法继续降低。",
        "training.error.attribute_id_unverified": "所选属性尚未验证成长编号。",
        "training.error.attribute_changed": "{attribute} 已发生变化，请重新打开面板。",
        "training.error.ca_over_limit": "本次训练预计需要{ca_cost}点 CA，完成后 CA 将超过200。",
        "training.error.ca_over_pa_confirmation": "接下来的锻炼会导致 CA 超过 PA，可能触发属性重新分配。请确认后继续。",
        "training.error.insufficient_funds": "银行与钱包余额合计不足，无法支付本次训练费用。",
        "training.error.growth_hook_sync_failed": "训练任务已建立，但成长 Hook 同步失败，请刷新页面后重试。",
        "training.error.cancel_focus_required": "请选择需要取消的训练人员。",
        "training.error.task_not_found": "训练记录不存在，请刷新训练场。",
        "training.error.task_not_active": "该人员已不在使用此器材。",
        "training.error.equipment_route_retired": "训练场已改版，不再支持购买、解锁楼层、摆放、收纳或出售训练器材，请刷新训练场后使用球员训练、位置训练或职员训练。",
        "training.error.project_not_found": "训练项目不存在，请刷新训练场。",
        "training.error.project_retired": "训练项目已下架，请刷新训练场。",
        "training.error.project_mismatch": "训练项目不匹配，请刷新训练场后重试。",
        "training.error.project_invalid": "训练模块无效。",
        "training.error.duration_mode_invalid": "请选择有效的训练时长。",
        "training.error.position_key_invalid": "所选训练位置无效。",
        "training.error.player_task_exists": "该球员已有进行中的专项训练。",
        "training.error.coach_task_exists": "该教练已有进行中的考证课程或综合训练指导任务。",
        "training.error.request_invalid": "训练请求无效，请刷新训练场后重试。",
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
