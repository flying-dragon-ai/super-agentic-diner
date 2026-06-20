from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings


class EvomapPaymentError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "evomap_payment_error",
        http_status: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details or {}


class EvomapPaymentConfigError(EvomapPaymentError):
    pass


def credits_for_order(_: Any = None) -> int:
    # Local ledger credit count for a Skill order. The real deduction amount on
    # the EvoMap Hub is the service listing's price_per_task, set via
    # EVOMAP_SERVICE_LISTING_ID; this value is bookkeeping metadata only.
    return max(1, int(settings.evomap_order_credits or 1))


def build_service_order_question(
    *,
    request_id: str,
    consumer_node_id: str,
    coffee_names: list[str],
    amount_credits: int,
) -> str:
    coffee_text = ", ".join(coffee_names)
    return (
        "Coffee order payment "
        f"request_id={request_id}; "
        f"consumer_node_id={consumer_node_id}; "
        f"coffees={coffee_text}; "
        f"credits={amount_credits}"
    )


def build_service_order_request(
    *,
    request_id: str,
    consumer_node_id: str,
    coffee_names: list[str],
    amount_credits: int,
) -> dict[str, Any]:
    listing_id = settings.evomap_service_listing_id.strip()
    question = build_service_order_question(
        request_id=request_id,
        consumer_node_id=consumer_node_id,
        coffee_names=coffee_names,
        amount_credits=amount_credits,
    )
    return {
        "sender_id": consumer_node_id,
        "listing_id": listing_id,
        "question": question,
    }


def place_service_order(
    *,
    request_id: str,
    consumer_node_id: str,
    node_secret: str,
    coffee_names: list[str],
    amount_credits: int,
) -> dict[str, Any]:
    if settings.evomap_payment_mode != "service_order":
        raise EvomapPaymentConfigError(
            f"Unsupported EvoMap payment mode: {settings.evomap_payment_mode}",
            code="evomap_payment_mode_unsupported",
            http_status=500,
        )

    listing_id = settings.evomap_service_listing_id.strip()
    if not listing_id:
        raise EvomapPaymentConfigError(
            "EVOMAP_SERVICE_LISTING_ID is required for EvoMap service-order payment",
            code="evomap_service_listing_missing",
            http_status=503,
        )
    if not node_secret.strip():
        raise EvomapPaymentError(
            "EvoMap node secret is required to spend user credits",
            code="evomap_node_secret_required",
            http_status=402,
        )

    body = build_service_order_request(
        request_id=request_id,
        consumer_node_id=consumer_node_id,
        coffee_names=coffee_names,
        amount_credits=amount_credits,
    )
    response = _post_json(
        f"{settings.evomap_hub_url.rstrip('/')}/a2a/service/order",
        body,
        node_secret=node_secret,
        correlation_id=request_id,
    )
    evomap_order_id = _extract_order_id(response)
    if not evomap_order_id:
        raise EvomapPaymentError(
            "EvoMap service order response did not include an order id",
            code="evomap_order_id_missing",
            http_status=502,
            details={"response": _redact_response(response)},
        )

    return {
        "evomap_order_id": evomap_order_id,
        "credits": amount_credits,
        "request_id": request_id,
        "consumer_node_id": consumer_node_id,
        "listing_id": listing_id,
        "status": str(response.get("status") or "created"),
        "question": body["question"],
        "raw_response": _redact_response(response),
    }


def _post_json(
    url: str,
    body: dict[str, Any],
    *,
    node_secret: str,
    correlation_id: str,
) -> dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {node_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CoffeeAIBoss/1.0 (+https://evomap.ai; service-order-client)",
            "x-correlation-id": correlation_id,
        },
    )
    try:
        with urlopen(
            request,
            timeout=float(settings.evomap_request_timeout_seconds),
        ) as response:
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        details = _read_error_body(exc)
        raise EvomapPaymentError(
            _message_for_status(exc.code, details),
            code=_code_for_status(exc.code, details),
            http_status=_http_status_for_upstream(exc.code),
            details=details,
        ) from exc
    except URLError as exc:
        raise EvomapPaymentError(
            f"EvoMap service order request failed: {exc.reason}",
            code="evomap_network_error",
            http_status=503,
        ) from exc
    except TimeoutError as exc:
        raise EvomapPaymentError(
            "EvoMap service order request timed out",
            code="evomap_timeout",
            http_status=504,
        ) from exc

    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise EvomapPaymentError(
            "EvoMap service order response was not JSON",
            code="evomap_invalid_json",
            http_status=502,
        ) from exc
    if not isinstance(data, dict):
        raise EvomapPaymentError(
            "EvoMap service order response had an unexpected shape",
            code="evomap_invalid_response",
            http_status=502,
        )
    return data


def _read_error_body(exc: HTTPError) -> dict[str, Any]:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return {"status": exc.code}
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"message": raw}
    if isinstance(data, dict):
        data.setdefault("status", exc.code)
        return _redact_response(data)
    return {"status": exc.code, "message": str(data)}


def _message_for_status(status: int, details: dict[str, Any]) -> str:
    upstream = details.get("error") or details.get("message") or details.get("detail")
    if status == 401:
        return "EvoMap rejected the node credentials"
    if status == 402:
        return "EvoMap credits are insufficient for this order"
    if status == 429:
        return "EvoMap rate limit exceeded"
    if upstream:
        return f"EvoMap service order failed: {upstream}"
    return f"EvoMap service order failed with HTTP {status}"


def _code_for_status(status: int, details: dict[str, Any]) -> str:
    upstream = str(details.get("error") or details.get("code") or "").strip()
    if upstream:
        return upstream
    return {
        401: "evomap_unauthorized",
        402: "evomap_insufficient_credits",
        429: "evomap_rate_limited",
    }.get(status, "evomap_http_error")


def _http_status_for_upstream(status: int) -> int:
    if status in {401, 402, 403, 429}:
        return status
    if status == 404:
        return 502
    if status >= 500:
        return 502
    return 400


def _extract_order_id(response: dict[str, Any]) -> str:
    candidates = (
        response.get("evomap_order_id"),
        response.get("order_id"),
        response.get("orderId"),
        response.get("task_id"),
        response.get("taskId"),
        response.get("id"),
    )
    for value in candidates:
        if value:
            return str(value)
    nested = response.get("order") or response.get("task") or response.get("payload")
    if isinstance(nested, dict):
        return _extract_order_id(nested)
    return ""


def _redact_response(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("secret", "token", "key", "authorization")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_response(item)
        return redacted
    if isinstance(value, list):
        return [_redact_response(item) for item in value]
    return value
