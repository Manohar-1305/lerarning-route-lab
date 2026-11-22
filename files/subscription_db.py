
from files.config import get_db
from psycopg2.extras import RealDictCursor


def init_subscription_tables():
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ll_account_trials (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL UNIQUE,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ll_lab_subscriptions (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    lab_name VARCHAR(30) NOT NULL,
                    plan_days INTEGER NOT NULL
                        CHECK (plan_days IN (1, 3, 7, 15, 30)),
                    amount NUMERIC(10, 2) NOT NULL,
                    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
                    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                    order_id VARCHAR(100) NOT NULL UNIQUE,
                    cf_order_id VARCHAR(100),
                    payment_session_id TEXT,
                    payment_id VARCHAR(150),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    expires_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ll_subscriptions_user_lab
                ON ll_lab_subscriptions(user_id, lab_name)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ll_subscriptions_status
                ON ll_lab_subscriptions(status, expires_at)
            """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def get_subscription_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)

