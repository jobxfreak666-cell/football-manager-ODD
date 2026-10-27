from http import HTTPStatus
from io import BytesIO
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
import json

import pytest

import fm_odds_web as web
from tools.api_routing import RouteRegistry
from tools.domain_errors import ValidationError


def handler_for(method, path):
    handler = web.Handler.__new__(web.Handler)
    handler.command = method
    handler.path = path
    handler.headers = {"Content-Length": "2"}
    handler.rfile = BytesIO(b"{}")
    handler._bind_request_scope = lambda: None
    responses = []
    handler._json = lambda status, payload: responses.append((status, payload))
    return handler, responses


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_registered_json_request_dispatches_once(monkeypatch, method):
    routes = RouteRegistry()
    calls = []

    def action(handler, payload, query):
        calls.append((payload, query))
        return {"result": "registered"}

    routes.add(method, "/api/unit", action, status=HTTPStatus.ACCEPTED)
    monkeypatch.setattr(web, "API_ROUTES", routes)
    handler, responses = handler_for(method, "/api/unit?q=1")
    (handler._do_GET if method == "GET" else handler.do_POST)()
    assert responses == [(HTTPStatus.ACCEPTED, {"result": "registered"})]
    assert calls == [({}, {"q": ["1"]} if method == "GET" else {})]


@pytest.mark.parametrize("method,path", [("GET", "/api/health"), ("POST", "/api/funds")])
def test_missing_registration_cannot_fall_through_to_a_second_implementation(monkeypatch, method, path):
    monkeypatch.setattr(web, "API_ROUTES", RouteRegistry())
    handler, responses = handler_for(method, path)
    (handler._do_GET if method == "GET" else handler.do_POST)()
    assert int(responses[0][0]) == 404
    assert responses[0][1]["error_code"] == "not_found"


def test_static_resource_fallback_still_bypasses_json_routes(monkeypatch):
    monkeypatch.setattr(web, "API_ROUTES", RouteRegistry())
    handler, responses = handler_for("GET", "/index.html")
    assets = []
    handler._static = assets.append
    handler._do_GET()
    assert assets == ["/index.html"]
    assert not responses


def test_post_dispatch_marks_memory_acquisitions_as_foreground(monkeypatch):
    events = []

    class RequestAwareLock:
        @contextmanager
        def foreground_request(self):
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

    routes = RouteRegistry()

    def action(_handler, _payload, _query):
        events.append("dispatch")
        return {"ok": True}

    routes.add("POST", "/api/unit", action)
    monkeypatch.setattr(web, "API_ROUTES", routes)
    handler, responses = handler_for("POST", "/api/unit")
    handler.state = SimpleNamespace(memory_lock=RequestAwareLock())
    handler.do_POST()

    assert responses == [(HTTPStatus.OK, {"ok": True})]
    assert events == ["enter", "dispatch", "exit"]


@pytest.mark.parametrize("path", ["/api/bets", "/api/inventory/use"])
def test_authored_business_validation_errors_allow_specific_ui_detail(path):
    payload = web.Handler._post_error_payload(path, ValueError("具体失败原因"))

    assert payload["error"] == "具体失败原因"
    assert payload["message_key"] == "error.invalid_request"
    assert payload["error_detail_safe"] is True


@pytest.mark.parametrize("path", ["/api/bets", "/api/inventory/use"])
def test_post_dispatch_preserves_specific_business_reason_for_shared_request_ui(
    monkeypatch, path,
):
    routes = RouteRegistry()

    def reject(_handler, _payload, _query):
        raise ValueError("盘口或道具的具体失败原因")

    routes.add("POST", path, reject)
    monkeypatch.setattr(web, "API_ROUTES", routes)
    handler, responses = handler_for("POST", path)

    handler.do_POST()

    status, payload = responses[0]
    assert status == HTTPStatus.BAD_REQUEST
    assert payload["message_key"] == "error.invalid_request"
    assert payload["message"] == "The request is invalid."
    assert payload["error"] == "盘口或道具的具体失败原因"
    assert payload["error_detail_safe"] is True


@pytest.mark.parametrize(
    "error",
    [
        TypeError("internal type detail"),
        KeyError("internal key detail"),
        RuntimeError("internal runtime detail"),
        json.JSONDecodeError("internal JSON detail", "{", 1),
        ValidationError("semantic detail", message_key="error.resource_not_found"),
    ],
)
def test_untrusted_or_semantic_errors_do_not_override_localized_messages(error):
    payload = web.Handler._post_error_payload("/api/bets", error)

    assert "error_detail_safe" not in payload


@pytest.mark.parametrize("failed_compensation", ["rollback", "refund"])
def test_counseling_compensation_error_is_nonretryable_and_json_safe(monkeypatch, failed_compensation):
    from dataclasses import replace
    from test_psychological_counseling_application import direct_io, direct_runtime, economy_state
    from tools import club_economy
    from tools.counseling_application import CounselingApplicationService

    io, _effect, _calls = direct_io()
    runtime, _player = direct_runtime()
    monkeypatch.setattr(club_economy, "load_economy", lambda: economy_state())
    monkeypatch.setattr(club_economy, "account_transaction", nullcontext)
    monkeypatch.setattr(club_economy, "read_persisted_document", lambda *_args, **_kwargs: economy_state())

    def fail_save(_payload):
        raise OSError("save failed at 0xDEADBEEF")

    def restore(_effect):
        if failed_compensation == "rollback":
            raise RuntimeError("restore failed at 0xABCDEF")

    def payment(amount, _kind, **_metadata):
        if amount > 0:
            raise OSError("refund failed at 0xBADBAD")

    monkeypatch.setattr(club_economy, "save_economy", fail_save)
    service = CounselingApplicationService(runtime, replace(
        io, perform_counseling=club_economy.perform_psychological_counseling,
        restore_effect=restore, adjust_balance=payment,
    ))
    routes = RouteRegistry()
    routes.add("POST", "/api/activity/counseling", lambda _h, _p, _q: service.counsel({"player_id": 2}))
    monkeypatch.setattr(web, "API_ROUTES", routes)
    handler, responses = handler_for("POST", "/api/activity/counseling")

    handler.do_POST()

    status, payload = responses[0]
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert payload["error_code"] == f"{failed_compensation}_incomplete"
    assert payload["error_phase"] == failed_compensation
    assert payload["retryable"] is False
    assert payload["message_key"] == "error.request_failed"
    assert "0x" not in json.dumps(payload)
    assert "_restores" not in json.dumps(payload)


def test_counseling_unknown_commit_handler_preserves_nonretryable_state(monkeypatch, tmp_path):
    from test_psychological_counseling_application import run_persisted_counseling

    run = run_persisted_counseling(tmp_path, verification="unreadable")
    routes = RouteRegistry()

    def action(_handler, _payload, _query):
        raise run["error"]

    routes.add("POST", "/api/activity/counseling", action)
    monkeypatch.setattr(web, "API_ROUTES", routes)
    handler, responses = handler_for("POST", "/api/activity/counseling")
    handler.do_POST()

    status, payload = responses[0]
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert (payload["error_code"], payload["error_phase"], payload["retryable"]) == (
        "commit_unknown", "commit", False,
    )
    assert payload["details"]["refund_attempted"] is False
    assert payload["message_key"] == "error.request_failed"
    assert "0x" not in json.dumps(payload)
    assert "_restores" not in json.dumps(payload)


def test_committed_counseling_with_persistent_signature_failure_returns_partial_success(monkeypatch, tmp_path):
    from test_psychological_counseling_application import run_persisted_counseling

    statuses = []

    def invoke(service):
        routes = RouteRegistry()
        routes.add("POST", "/api/activity/counseling", lambda _h, _p, _q: service.counsel({"player_id": 2}))
        monkeypatch.setattr(web, "API_ROUTES", routes)
        handler, responses = handler_for("POST", "/api/activity/counseling")
        handler.do_POST()
        statuses.append(responses[0][0])
        return responses[0][1]

    run = run_persisted_counseling(tmp_path, verification="persistent_signature", invoke=invoke)

    assert statuses == [HTTPStatus.OK]
    assert run["error"] is None
    response = run["response"]
    assert set(response) == {"counseling", "state_refresh_required"}
    assert response["state_refresh_required"] is True
    assert response["counseling"]["outcome"] == "unlocked"
    assert run["persisted"]["documents"]["economy"]["activity_history"][-1]["id"] == response["counseling"]["id"]
    assert run["persisted"]["documents"]["wallet"]["balance"] == 50_000.0
    assert run["events"] == [("wallet", -100_000.0), "apply"]
    assert run["native"]["unhappy"] is False
    assert run["signature_failures"] >= 3
    assert run["projection_reads"] == ["economy", "welfare"]
    assert "0x" not in json.dumps(response)
    assert "_restores" not in json.dumps(response)


@pytest.mark.parametrize("failed_projection", ["economy", "welfare", "both"])
def test_counseling_projection_failure_returns_success_without_repeating_side_effects(monkeypatch, failed_projection):
    from dataclasses import replace
    from test_psychological_counseling_application import direct_io, direct_runtime
    from tools.counseling_application import CounselingApplicationService

    io, _effect, calls = direct_io()
    runtime, player = direct_runtime()
    read_projections = []

    def project(name, value):
        read_projections.append(name)
        if failed_projection in {name, "both"}:
            raise RuntimeError("projection failed at 0xDEADBEEF")
        return value

    service = CounselingApplicationService(runtime, replace(
        io, public_economy=lambda: project("economy", {"wallet": 150_000.0}),
        welfare_status=lambda: project("welfare", {"treatments": {}}),
    ))
    routes = RouteRegistry()
    routes.add("POST", "/api/activity/counseling", lambda _h, _p, _q: service.counsel({"player_id": 2}))
    monkeypatch.setattr(web, "API_ROUTES", routes)
    handler, responses = handler_for("POST", "/api/activity/counseling")

    handler.do_POST()

    status, response = responses[0]
    assert status == HTTPStatus.OK
    assert response["counseling"]["outcome"] == "unlocked"
    assert response["state_refresh_required"] is True
    for name in ("economy", "welfare"):
        assert (name in response) == (failed_projection not in {name, "both"})
    assert read_projections == ["economy", "welfare"]
    assert len(calls["adjust"]) == 1
    assert calls["adjust"][0][0] == -100_000.0
    assert calls["restore"] == []
    assert player["has_unhappiness"] is False
    assert "0x" not in json.dumps(response)
    assert "_restores" not in json.dumps(response)
