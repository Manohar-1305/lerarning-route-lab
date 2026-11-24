
import os
import uuid
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from flask import (
    Blueprint,
    jsonify,
    request,
    session,
    current_app,
    redirect,
)

from psycopg2.extras import RealDictCursor

from files.config import get_db
from files.subscription_db import init_subscription_tables
from files.payments import (
    CashfreeError,
    create_cashfree_order,
    fetch_cashfree_order,
)
from files.subscription_emails import (
    send_trial_activated_email,
    send_payment_success_email,
)


bp = Blueprint("subscriptions", __name__, url_prefix="/subscriptions")

LABS = ("linux", "jenkins", "bash", "ansible")

PLAN_PRICES = {
    3: Decimal("25.00"),
    7: Decimal("65.00"),
    15: Decimal("125.00"),
    30: Decimal("250.00"),
}


def api_error(message, status_code=400):
    return jsonify({
        "success": False,
        "message": message,
        "error": message,
    }), status_code


def is_admin():
    return session.get("is_admin") is True


def current_user_id():
    value = session.get("user_id")

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)


def initialize():
    init_subscription_tables()


def get_user_email(conn, user_id, supplied_email=None):
    if supplied_email:
        supplied_email = supplied_email.strip()

        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", supplied_email):
            return supplied_email

    with get_cursor(conn) as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'users'
            ) AS table_exists
        """)

        result = cur.fetchone()
        table_exists = result["table_exists"]

        if not table_exists:
            return None

        cur.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'users'
                  AND column_name = 'email'
            ) AS column_exists
        """)

        result = cur.fetchone()

        if not result["column_exists"]:
            return None

        cur.execute(
            "SELECT email FROM users WHERE id = %s",
            (user_id,),
        )

        user = cur.fetchone()

        if user and user["email"]:
            return user["email"].strip()

    return None


def get_trial(cur, user_id):
    cur.execute(
        """
        SELECT *
        FROM ll_account_trials
        WHERE user_id = %s
        """,
        (user_id,),
    )

    return cur.fetchone()


def get_active_subscription(cur, user_id, lab):
    cur.execute(
        """
        SELECT *
        FROM ll_lab_subscriptions
        WHERE user_id = %s
          AND lab_name IN (%s, 'all')
          AND status = 'ACTIVE'
          AND started_at <= NOW()
          AND expires_at > NOW()
        ORDER BY expires_at DESC
        LIMIT 1
        """,
        (user_id, lab),
    )

    return cur.fetchone()


def get_access(cur, user_id, lab):
    trial = get_trial(cur, user_id)

    if trial and trial["expires_at"] > datetime.now(timezone.utc):
        return True, "trial", trial["expires_at"]

    subscription = get_active_subscription(cur, user_id, lab)

    if subscription:
        return True, "subscription", subscription["expires_at"]

    return False, None, None


@bp.before_app_request
def enforce_lab_subscription_access():
    if is_admin():
        return None

    path_parts = request.path.strip("/").split("/", 1)
    requested_lab = path_parts[0].lower()

    if requested_lab not in LABS:
        return None

    user_id = current_user_id()

    if user_id is None:
        return None

    conn = None

    try:
        initialize()
        conn = get_db()

        with get_cursor(conn) as cur:
            allowed, _, _ = get_access(
                cur,
                user_id,
                requested_lab,
            )

        if not allowed:
            return redirect("/?subscription=required")

        return None

    except Exception:
        current_app.logger.exception(
            "Unable to verify subscription access for lab: %s",
            requested_lab,
        )
        return api_error(
            "Unable to verify your subscription. Please try again.",
            503,
        )

    finally:
        if conn:
            conn.close()


def plans_payload():
    return [
        {
            "days": days,
            "amount": float(amount),
            "currency": "INR",
        }
        for days, amount in PLAN_PRICES.items()
    ]


@bp.route("/health", methods=["GET"])
def health():
    try:
        initialize()

        return jsonify({
            "success": True,
            "message": "Subscription API is running",
        })

    except Exception:
        current_app.logger.exception("Subscription API health check failed")
        return api_error("Subscription database is unavailable.", 503)


@bp.route("/plans", methods=["GET"])
def plans():
    return jsonify({
        "success": True,
        "labs": list(LABS),
        "plans": plans_payload(),
    })


@bp.route("/status", methods=["GET"])
def status():
    user_id = current_user_id()

    if user_id is None:
        return api_error("Please log in to continue.", 401)

    if is_admin():
        return jsonify({
            "success": True,
            "is_admin": True,
            "admin_access": True,
            "trial_used": False,
            "trial_active": False,
            "trial_expires_at": None,
            "labs": {
                lab: {
                    "has_access": True,
                    "access_type": "admin",
                    "expires_at": None,
                }
                for lab in LABS
            },
            "plans": plans_payload(),
        })

    conn = None

    try:
        initialize()
        conn = get_db()

        with get_cursor(conn) as cur:
            trial = get_trial(cur, user_id)
            now = datetime.now(timezone.utc)

            trial_used = trial is not None
            trial_active = bool(
                trial and trial["expires_at"] > now
            )

            lab_status = {}

            for lab in LABS:
                allowed, access_type, expiry = get_access(
                    cur, user_id, lab
                )

                lab_status[lab] = {
                    "has_access": allowed,
                    "access_type": access_type,
                    "expires_at": expiry.isoformat() if expiry else None,
                }

        return jsonify({
            "success": True,
            "trial_used": trial_used,
            "trial_active": trial_active,
            "trial_expires_at": (
                trial["expires_at"].isoformat() if trial else None
            ),
            "labs": lab_status,
            "plans": plans_payload(),
        })

    except Exception:
        current_app.logger.exception("Subscription status failed")
        return api_error("Unable to retrieve subscription status.", 500)

    finally:
        if conn:
            conn.close()


@bp.route("/trial/start", methods=["POST"])
@bp.route("/enroll/trial", methods=["POST"])
def start_trial():
    user_id = current_user_id()

    if user_id is None:
        return api_error("Please log in to start your free trial.", 401)

    if is_admin():
        return jsonify({
            "success": True,
            "is_admin": True,
            "admin_access": True,
            "trial_used": False,
            "trial_active": False,
            "message": "Admin accounts have unlimited access.",
            "labs": list(LABS),
        })

    conn = None

    try:
        initialize()
        conn = get_db()

        with get_cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO ll_account_trials (
                    user_id,
                    started_at,
                    expires_at
                )
                VALUES (
                    %s,
                    NOW(),
                    NOW() + INTERVAL '24 hours'
                )
                ON CONFLICT (user_id) DO NOTHING
                RETURNING *
                """,
                (user_id,),
            )

            trial = cur.fetchone()

            if not trial:
                existing = get_trial(cur, user_id)
                conn.commit()

                active = bool(
                    existing
                    and existing["expires_at"] > datetime.now(timezone.utc)
                )

                return jsonify({
                    "success": False,
                    "trial_used": True,
                    "trial_active": active,
                    "message": (
                        "Your free trial has already been used. "
                        "Please choose a subscription plan."
                    ),
                }), 409

        conn.commit()

        email = get_user_email(conn, user_id)

        if email:
            send_trial_activated_email(email)

        return jsonify({
            "success": True,
            "trial_used": True,
            "trial_active": True,
            "message": "Your free trial is activated for 24 hours.",
            "expires_at": trial["expires_at"].isoformat(),
        })

    except Exception:
        if conn:
            conn.rollback()

        current_app.logger.exception("Free trial activation failed")
        return api_error("Unable to activate your free trial.", 500)

    finally:
        if conn:
            conn.close()


@bp.route("/enroll/<lab>", methods=["GET", "POST"])
def enroll(lab):
    user_id = current_user_id()

    if user_id is None:
        return api_error("Please log in to continue.", 401)

    lab = lab.lower().strip()

    if lab not in LABS:
        return api_error("Invalid lab.", 404)

    if is_admin():
        return jsonify({
            "success": True,
            "is_admin": True,
            "admin_access": True,
            "has_access": True,
            "access_type": "admin",
            "expires_at": None,
            "trial_used": False,
            "trial_available": False,
            "needs_subscription": False,
            "lab": lab,
            "message": "Admin accounts have unlimited access.",
        })

    conn = None

    try:
        initialize()
        conn = get_db()

        with get_cursor(conn) as cur:
            allowed, access_type, expiry = get_access(
                cur, user_id, lab
            )

            trial = get_trial(cur, user_id)

        if allowed:
            return jsonify({
                "success": True,
                "has_access": True,
                "access_type": access_type,
                "expires_at": expiry.isoformat() if expiry else None,
                "message": "You already have access to this lab.",
            })

        trial_used = trial is not None

        return jsonify({
            "success": True,
            "has_access": False,
            "trial_used": trial_used,
            "trial_available": not trial_used,
            "needs_subscription": trial_used,
            "lab": lab,
            "plans": plans_payload(),
            "message": (
                "Your free trial has expired. Choose a subscription "
                "to continue practising."
                if trial_used
                else "Start your free 24-hour trial."
            ),
        })

    except Exception:
        current_app.logger.exception("Lab enrollment failed")
        return api_error("Unable to retrieve enrollment details.", 500)

    finally:
        if conn:
            conn.close()


@bp.route("/access/<lab>", methods=["GET"])
def check_access(lab):
    user_id = current_user_id()

    if user_id is None:
        return api_error("Please log in to continue.", 401)

    lab = lab.lower().strip()

    if lab not in LABS:
        return api_error("Invalid lab.", 404)

    if is_admin():
        return jsonify({
            "success": True,
            "is_admin": True,
            "admin_access": True,
            "lab": lab,
            "has_access": True,
            "access_type": "admin",
            "expires_at": None,
        })

    conn = None

    try:
        initialize()
        conn = get_db()

        with get_cursor(conn) as cur:
            allowed, access_type, expiry = get_access(
                cur, user_id, lab
            )

        return jsonify({
            "success": True,
            "lab": lab,
            "has_access": allowed,
            "access_type": access_type,
            "expires_at": expiry.isoformat() if expiry else None,
        })

    except Exception:
        current_app.logger.exception("Lab access check failed")
        return api_error("Unable to check lab access.", 500)

    finally:
        if conn:
            conn.close()


@bp.route("/payment/create", methods=["POST"])
def create_payment():
    user_id = current_user_id()

    if user_id is None:
        return api_error("Please log in to subscribe.", 401)

    if is_admin():
        return jsonify({
            "success": True,
            "is_admin": True,
            "admin_access": True,
            "has_access": True,
            "message": "Admin accounts do not require payment.",
            "labs": list(LABS),
        })

    data = request.get_json(silent=True) or {}

    try:
        days = int(data.get("days", data.get("plan_days", 0)))
    except (TypeError, ValueError):
        return api_error("Invalid subscription duration.")

    if days not in PLAN_PRICES:
        return api_error("Invalid subscription plan.")

    conn = None

    try:
        initialize()
        conn = get_db()

        email = get_user_email(
            conn,
            user_id,
            data.get("email"),
        )

        phone = str(
            data.get("phone") or data.get("customer_phone") or ""
        ).strip()

        if not email:
            return api_error(
                "Your account email could not be found. "
                "Please provide your email.",
                400,
            )

        if not re.fullmatch(r"[6-9]\d{9}", phone):
            return api_error(
                "A valid 10-digit Indian mobile number is required.",
                400,
            )

        order_id = "LL" + uuid.uuid4().hex[:20]
        amount = PLAN_PRICES[days]

        with get_cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO ll_lab_subscriptions (
                    user_id,
                    lab_name,
                    plan_days,
                    amount,
                    currency,
                    status,
                    order_id
                )
                VALUES (%s, 'all', %s, %s, 'INR', 'PENDING', %s)
                """,
                (user_id, days, amount, order_id),
            )

        conn.commit()

        return_url = f"https://learninglabs.study/subscriptions/payment/return?order_id={{order_id}}"
        cashfree_result = create_cashfree_order(
            order_id=order_id,
            amount=amount,
            user_id=user_id,
            email=email,
            phone=phone,
            return_url=return_url,
        )

        with get_cursor(conn) as cur:
            cur.execute(
                """
                UPDATE ll_lab_subscriptions
                SET cf_order_id = %s,
                    payment_session_id = %s,
                    updated_at = NOW()
                WHERE order_id = %s
                """,
                (
                    str(cashfree_result.get("cf_order_id", "")),
                    cashfree_result["payment_session_id"],
                    order_id,
                ),
            )

        conn.commit()

        return jsonify({
            "success": True,
            "order_id": order_id,
            "payment_session_id": cashfree_result["payment_session_id"],
            "cashfree_environment": (
                "production"
                if os.getenv("CASHFREE_ENV", "sandbox").lower()
                == "production"
                else "sandbox"
            ),
            "amount": float(amount),
            "currency": "INR",
            "access": "all",
            "labs": list(LABS),
            "days": days,
        })

    except CashfreeError as exc:
        if conn:
            conn.rollback()

        current_app.logger.exception("Cashfree order creation failed")
        return api_error(str(exc), 502)

    except Exception:
        if conn:
            conn.rollback()

        current_app.logger.exception("Payment creation failed")
        return api_error("Unable to create payment order.", 500)

    finally:
        if conn:
            conn.close()


def verify_order(order_id, user_id=None):
    conn = None

    try:
        initialize()
        conn = get_db()

        with get_cursor(conn) as cur:
            cur.execute(
                """
                SELECT *
                FROM ll_lab_subscriptions
                WHERE order_id = %s
                """,
                (order_id,),
            )

            subscription = cur.fetchone()

        if not subscription:
            return {
                "success": False,
                "message": "Subscription order not found.",
            }, 404

        if (
            user_id is not None
            and int(subscription["user_id"]) != int(user_id)
        ):
            return {
                "success": False,
                "message": "This order does not belong to your account.",
            }, 403

        if subscription["status"] == "ACTIVE":
            return {
                "success": True,
                "message": "Subscription is already active.",
                "labs": list(LABS),
                "starts_at": subscription["started_at"].isoformat(),
                "expires_at": subscription["expires_at"].isoformat(),
            }, 200

        cashfree_order = fetch_cashfree_order(order_id)

        if cashfree_order.get("order_status") != "PAID":
            return {
                "success": False,
                "message": "Payment has not been confirmed.",
                "payment_status": cashfree_order.get("order_status"),
            }, 402

        try:
            paid_amount = Decimal(str(cashfree_order["order_amount"]))
            expected_amount = Decimal(str(subscription["amount"]))
        except (KeyError, InvalidOperation, TypeError):
            return {
                "success": False,
                "message": "Unable to verify payment amount.",
            }, 400

        if paid_amount != expected_amount:
            return {
                "success": False,
                "message": "Payment amount does not match the order.",
            }, 400

        if cashfree_order.get("order_currency") != "INR":
            return {
                "success": False,
                "message": "Payment currency does not match the order.",
            }, 400

        with get_cursor(conn) as cur:
            cur.execute(
                """
                UPDATE ll_lab_subscriptions AS subscription
                SET status = 'ACTIVE',
                    started_at = GREATEST(
                        NOW(),
                        COALESCE(
                            (
                                SELECT trial.expires_at
                                FROM ll_account_trials AS trial
                                WHERE trial.user_id = subscription.user_id
                            ),
                            NOW()
                        )
                    ),
                    expires_at = GREATEST(
                        NOW(),
                        COALESCE(
                            (
                                SELECT trial.expires_at
                                FROM ll_account_trials AS trial
                                WHERE trial.user_id = subscription.user_id
                            ),
                            NOW()
                        )
                    ) + (subscription.plan_days * INTERVAL '1 day'),
                    payment_id = %s,
                    updated_at = NOW()
                WHERE subscription.order_id = %s
                  AND subscription.status = 'PENDING'
                RETURNING *
                """,
                (
                    str(cashfree_order.get("cf_order_id", "")),
                    order_id,
                ),
            )

            activated = cur.fetchone()

        conn.commit()

        if activated:
            email = get_user_email(conn, activated["user_id"])

            if email:
                send_payment_success_email(
                    email,
                    "all",
                    activated["plan_days"],
                    activated["amount"],
                    activated["expires_at"].isoformat(),
                )

            expiry = activated["expires_at"]
            starts_at = activated["started_at"]

        else:
            with get_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ll_lab_subscriptions
                    WHERE order_id = %s
                    """,
                    (order_id,),
                )

                current = cur.fetchone()

            if not current or current["status"] != "ACTIVE":
                return {
                    "success": False,
                    "message": "Subscription could not be activated.",
                }, 409

            expiry = current["expires_at"]
            starts_at = current["started_at"]

        return {
            "success": True,
            "message": (
                "Payment verified. Your subscription will start after "
                "your free trial expires."
                if starts_at > datetime.now(timezone.utc)
                else "Payment verified. All four labs are now active."
            ),
            "labs": list(LABS),
            "starts_at": starts_at.isoformat(),
            "expires_at": expiry.isoformat(),
        }, 200

    except CashfreeError:
        if conn:
            conn.rollback()

        current_app.logger.exception("Cashfree verification failed")

        return {
            "success": False,
            "message": "Unable to verify payment with Cashfree.",
        }, 502

    except Exception:
        if conn:
            conn.rollback()

        current_app.logger.exception("Payment verification failed")

        return {
            "success": False,
            "message": "Unable to verify payment.",
        }, 500

    finally:
        if conn:
            conn.close()


@bp.route("/payment/verify/<order_id>", methods=["GET", "POST"])
def verify_payment(order_id):
    user_id = current_user_id()

    if user_id is None:
        return api_error("Please log in to verify payment.", 401)

    result, status_code = verify_order(order_id, user_id)

    return jsonify(result), status_code


@bp.route("/payment/return", methods=["GET"])
def payment_return():
    order_id = request.args.get("order_id")
    user_id = current_user_id()

    if not order_id or user_id is None:
        return redirect("/?payment=failed")

    result, status_code = verify_order(order_id, user_id)

    if status_code == 200 and result.get("success"):
        return redirect("/?payment=success")

    return redirect("/?payment=failed")
