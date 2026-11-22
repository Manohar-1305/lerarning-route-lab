
import os
import uuid
import requests


CASHFREE_API_VERSION = "2023-08-01"
CASHFREE_TIMEOUT = 30


class CashfreeError(Exception):
    pass


def _get_config():
    app_id = os.getenv("CASHFREE_APP_ID", "").strip()
    secret_key = os.getenv("CASHFREE_SECRET_KEY", "").strip()
    environment = os.getenv("CASHFREE_ENV", "sandbox").strip().lower()

    if not app_id or not secret_key:
        raise CashfreeError("Cashfree credentials are not configured.")

    if environment not in ("sandbox", "production"):
        raise CashfreeError(
            "Invalid CASHFREE_ENV. Use sandbox or production."
        )

    base_url = (
        "https://sandbox.cashfree.com/pg"
        if environment == "sandbox"
        else "https://api.cashfree.com/pg"
    )

    return app_id, secret_key, base_url


def _headers():
    app_id, secret_key, _ = _get_config()

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-client-id": app_id,
        "x-client-secret": secret_key,
        "x-api-version": CASHFREE_API_VERSION,
        "x-request-id": str(uuid.uuid4()),
    }


def _handle_response(response):
    if not response.ok:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text[:500]

        raise CashfreeError(
            f"Cashfree returned HTTP {response.status_code}: "
            f"{error_data}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise CashfreeError(
            "Cashfree returned an invalid JSON response."
        ) from exc


def create_cashfree_order(
    order_id,
    amount,
    user_id,
    email,
    phone,
    return_url,
):
    _, _, base_url = _get_config()

    payload = {
        "order_id": str(order_id),
        "order_amount": round(float(amount), 2),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(user_id),
            "customer_email": str(email),
            "customer_phone": str(phone),
        },
        "order_meta": {
            "return_url": return_url,
        },
    }

    try:
        response = requests.post(
            f"{base_url}/orders",
            headers=_headers(),
            json=payload,
            timeout=CASHFREE_TIMEOUT,
        )

        result = _handle_response(response)

        if not result.get("payment_session_id"):
            raise CashfreeError(
                "Cashfree did not return a payment session."
            )

        return result

    except requests.RequestException as exc:
        raise CashfreeError(
            f"Cashfree connection failed: {exc}"
        ) from exc


def fetch_cashfree_order(order_id):
    _, _, base_url = _get_config()

    try:
        response = requests.get(
            f"{base_url}/orders/{order_id}",
            headers=_headers(),
            timeout=CASHFREE_TIMEOUT,
        )

        return _handle_response(response)

    except requests.RequestException as exc:
        raise CashfreeError(
            f"Cashfree connection failed: {exc}"
        ) from exc

