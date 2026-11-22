
import os
import smtplib
import mimetypes
import html

from datetime import datetime
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from email.utils import make_msgid

from files.config import get_db


BANNER_PATH = os.getenv(
    "MAIL_BANNER_PATH",
    "static/images/email-banner.png"
)


def get_username(email):
    conn = None
    cur = None

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT username FROM users WHERE email = %s LIMIT 1",
            (email,),
        )
        row = cur.fetchone()

        if not row:
            return "Learner"

        if isinstance(row, dict):
            return row.get("username") or "Learner"

        return row[0] or "Learner"

    except Exception:
        return "Learner"

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def format_indian_time(expiry):
    try:
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(
                expiry.replace("Z", "+00:00")
            )

        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=ZoneInfo("UTC"))

        expiry = expiry.astimezone(ZoneInfo("Asia/Kolkata"))

        return expiry.strftime("%d %B %Y, %I:%M %p IST")

    except (ValueError, TypeError):
        return str(expiry)


def send_subscription_email(to, subject, body, html_body=None):
    if not to:
        return False

    host = os.getenv("MAIL_HOST")
    port = int(os.getenv("MAIL_PORT", "587"))
    username = os.getenv("MAIL_USER")
    password = os.getenv("MAIL_PASSWORD")
    sender = os.getenv("MAIL_FROM") or username

    if not host or not sender:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

        if os.path.isfile(BANNER_PATH):
            mime_type, _ = mimetypes.guess_type(BANNER_PATH)

            if mime_type and mime_type.startswith("image/"):
                maintype, subtype = mime_type.split("/", 1)
                cid = make_msgid()

                with open(BANNER_PATH, "rb") as image_file:
                    image_data = image_file.read()

                html_part = message.get_payload()[-1]

                html_body = html_body.replace(
                    "cid:EMAIL_BANNER",
                    f"cid:{cid[1:-1]}"
                )

                html_part.set_content(html_body, subtype="html")

                html_part.add_related(
                    image_data,
                    maintype=maintype,
                    subtype=subtype,
                    cid=cid,
                    filename=os.path.basename(BANNER_PATH),
                    disposition="inline",
                )

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()

            if username and password:
                server.login(username, password)

            server.send_message(message)

        return True

    except Exception:
        return False


def email_template(name, heading, subtitle, content):
    safe_name = html.escape(str(name))
    safe_heading = html.escape(str(heading))

    banner = """
    <div style="background:linear-gradient(135deg,#172554 0%,#4338ca 55%,#7c3aed 100%);
                padding:35px 20px;text-align:center;color:#ffffff;">
        <div style="font-size:42px;line-height:1.5;">&#127881; &#128218;</div>
        <div style="font-size:28px;font-weight:800;letter-spacing:1px;">
            LEARNING LABS
        </div>
        <div style="font-size:14px;color:#e0e7ff;margin-top:8px;">
            Learn by Doing. Grow by Practising.
        </div>
    </div>
    """

    if os.path.isfile(BANNER_PATH):
        banner = """
        <img src="cid:EMAIL_BANNER"
             alt="Learning Labs"
             style="display:block;width:100%;height:auto;max-height:240px;object-fit:cover;">
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0;padding:25px 12px;background:#e9edff;
                 font-family:Arial,Helvetica,sans-serif;">

      <div style="max-width:620px;margin:auto;background:#ffffff;
                  border-radius:16px;overflow:hidden;
                  box-shadow:0 8px 30px rgba(30,41,100,0.15);">

        {banner}

        <div style="padding:35px 30px;color:#1f2937;">

          <div style="display:inline-block;background:#ede9fe;color:#5b21b6;
                      padding:8px 14px;border-radius:30px;font-size:12px;
                      font-weight:bold;letter-spacing:1px;">
              LEARNING JOURNEY
          </div>

          <h1 style="font-size:28px;line-height:1.3;color:#172554;
                     margin:20px 0 10px;">
              {safe_heading}
          </h1>

          <h2 style="font-size:21px;color:#4338ca;margin:12px 0;">
              Thank you, {safe_name}!
          </h2>

          <p style="font-size:15px;line-height:1.8;color:#4b5563;">
              {subtitle}
          </p>

          {content}

        </div>

        <div style="background:#172554;padding:28px 20px;text-align:center;
                    color:#ffffff;">

          <div style="font-size:19px;font-weight:bold;">
              Keep Building. Keep Growing.
          </div>

          <p style="font-size:13px;color:#c7d2fe;line-height:1.7;">
              Linux &nbsp; | &nbsp; Jenkins &nbsp; | &nbsp;
              Bash &nbsp; | &nbsp; Ansible
          </p>

          <p style="font-size:13px;color:#c7d2fe;margin-bottom:0;">
              Thank you for being part of Learning Labs.
          </p>

        </div>

      </div>

    </body>
    </html>
    """


def send_trial_activated_email(email):
    name = get_username(email)

    body = (
        f"Hi {name},\n\n"
        "Thank you for joining Learning Labs!\n\n"
        "Your 24-hour free trial is now active.\n"
        "You can practise Linux, Jenkins, Bash and Ansible.\n\n"
        "Explore the labs, experiment with commands and build practical skills.\n"
        "Want more time to practise? Upgrade to a longer subscription plan.\n\n"
        "Happy learning!\n"
        "Team Learning Labs"
    )

    content = """
    <div style="background:linear-gradient(135deg,#dbeafe,#ede9fe);
                border-radius:12px;padding:22px;margin:25px 0;
                text-align:center;">
        <div style="font-size:36px;">&#128640;</div>
        <h2 style="color:#312e81;margin:10px 0;">
            Your Free Trial Is LIVE!
        </h2>
        <p style="color:#3730a3;font-size:15px;margin-bottom:0;">
            Enjoy 24 hours of hands-on learning and practice.
        </p>
    </div>

    <h3 style="color:#172554;">Your Learning Playground</h3>

    <table style="width:100%;border-spacing:8px;">
      <tr>
        <td style="background:#eff6ff;padding:15px;border-radius:8px;
                   text-align:center;color:#1d4ed8;font-weight:bold;">
          Linux
        </td>
        <td style="background:#f5f3ff;padding:15px;border-radius:8px;
                   text-align:center;color:#6d28d9;font-weight:bold;">
          Jenkins
        </td>
      </tr>
      <tr>
        <td style="background:#ecfdf5;padding:15px;border-radius:8px;
                   text-align:center;color:#047857;font-weight:bold;">
          Bash
        </td>
        <td style="background:#fff7ed;padding:15px;border-radius:8px;
                   text-align:center;color:#c2410c;font-weight:bold;">
          Ansible
        </td>
      </tr>
    </table>

    <h3 style="color:#172554;margin-top:28px;">
        Don't Just Learn. Get Hands-On!
    </h3>

    <p style="color:#4b5563;line-height:1.8;">
        Practise real commands, explore practical scenarios and build
        the confidence to work with real-world technologies.
    </p>

    <div style="background:#172554;border-radius:12px;padding:22px;
                margin-top:25px;text-align:center;color:#ffffff;">
        <h2 style="margin:0 0 10px;color:#ffffff;">
            Ready for More?
        </h2>
        <p style="color:#e0e7ff;line-height:1.7;">
            Upgrade your subscription and give yourself more time
            to practise, experiment and improve.
        </p>
        <p style="color:#ffffff;font-weight:bold;margin-bottom:0;">
            Your next skill starts with your next practice session!
        </p>
    </div>
    """

    html_body = email_template(
        name,
        "Welcome to Your Learning Journey!",
        "Your free trial is activated. It's time to turn knowledge into practical skills!",
        content,
    )

    return send_subscription_email(
        email,
        "Your Learning Labs Free Trial Is LIVE!",
        body,
        html_body,
    )


def send_payment_success_email(email, lab, days, amount, expiry):
    name = get_username(email)
    formatted_expiry = format_indian_time(expiry)

    body = (
        f"Hi {name},\n\n"
        "Thank you for choosing Learning Labs!\n"
        "Your subscription payment was successful.\n\n"
        f"Lab: {lab.title()}\n"
        f"Plan: {days} days\n"
        f"Amount: Rs. {amount:.2f}\n"
        f"Expires: {formatted_expiry}\n\n"
        "Make the most of your subscription. Practise regularly in our labs,\n"
        "experiment with real-world tasks and strengthen your technical skills.\n\n"
        "Upgrade to a longer plan to continue your learning journey without interruption.\n\n"
        "Happy learning!\n"
        "Team Learning Labs"
    )

    content = f"""
    <div style="background:linear-gradient(135deg,#dcfce7,#dbeafe);
                border-radius:12px;padding:22px;margin:25px 0;
                text-align:center;">
        <div style="font-size:38px;">&#127881; &#9989;</div>
        <h2 style="color:#14532d;margin:10px 0;">
            Payment Successful!
        </h2>
        <p style="color:#166534;font-size:15px;margin-bottom:0;">
            Your subscription is active. Let the learning begin!
        </p>
    </div>

    <h3 style="color:#172554;">Your Subscription Details</h3>

    <div style="background:#f8fafc;border:1px solid #dbeafe;
                border-radius:12px;padding:20px;margin:15px 0;">

        <p style="margin:10px 0;color:#475569;">
            <strong>Lab</strong>
            <span style="float:right;color:#172554;">{html.escape(lab.title())}</span>
        </p>

        <hr style="border:0;border-top:1px solid #e2e8f0;">

        <p style="margin:10px 0;color:#475569;">
            <strong>Plan</strong>
            <span style="float:right;color:#172554;">{int(days)} days</span>
        </p>

        <hr style="border:0;border-top:1px solid #e2e8f0;">

        <p style="margin:10px 0;color:#475569;">
            <strong>Amount Paid</strong>
            <span style="float:right;color:#15803d;font-weight:bold;">
                Rs. {float(amount):.2f}
            </span>
        </p>

        <hr style="border:0;border-top:1px solid #e2e8f0;">

        <p style="margin:10px 0;color:#475569;">
            <strong>Access Expires</strong><br>
            <span style="color:#dc2626;font-weight:bold;">
                {html.escape(formatted_expiry)}
            </span>
        </p>
    </div>

    <h3 style="color:#172554;">Make Every Day Count!</h3>

    <p style="color:#4b5563;line-height:1.8;">
        You now have an opportunity to sharpen your skills through
        hands-on practice. Don't just read about technologies.
        Use the labs, execute commands, solve problems and gain confidence.
    </p>

    <div style="background:#172554;border-radius:12px;padding:24px;
                margin-top:25px;text-align:center;color:#ffffff;">

        <div style="font-size:30px;">&#128293;</div>

        <h2 style="color:#ffffff;margin:10px 0;">
            Your Growth Doesn't Stop Here!
        </h2>

        <p style="color:#e0e7ff;line-height:1.7;">
            Need more time to practise?
            Upgrade to a longer subscription plan and keep your
            hands-on learning journey going.
        </p>

        <p style="color:#fcd34d;font-weight:bold;font-size:16px;">
            Learn More. Practise More. Achieve More.
        </p>
    </div>
    """

    html_body = email_template(
        name,
        "You're All Set!",
        "Thank you for your purchase. Your Learning Labs subscription is now active!",
        content,
    )

    return send_subscription_email(
        email,
        "Payment Successful - Welcome to Learning Labs!",
        body,
        html_body,
    )

