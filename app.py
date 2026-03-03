"""
==============================================================================
Cold Email Sender for DevOps Job Applications
Author  : Satvik Dubey
Email   : satvikdubey268@gmail.com
Version : 2.0 (Production-Ready)
==============================================================================

Usage:
    python send_emails.py                  # Normal mode
    python send_emails.py --dry-run        # Dry-run (no emails sent)
    python send_emails.py --resume path/to/resume.pdf

Environment Variables Required:
    SENDER_EMAIL   - Your Gmail address
    GMAIL_APP_PASS - Your Gmail App Password (16-character)
"""

import os
import sys
import time
import smtplib
import logging
import argparse
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = 587
DELAY_SECONDS   = 10          # Delay between each company's email batch
RETRY_LIMIT     = 3           # Max retries per email on failure
RETRY_DELAY     = 5           # Seconds to wait before retrying
DEFAULT_RESUME  = "Satvik_Dubey_DevOps_Resume.pdf"
LOG_FILE        = "email_log.txt"

EMAIL_SUBJECT = "DevOps Engineer (1 Year Experience) – Application for Opportunities"

EMAIL_BODY_TEMPLATE = """\
Dear {greeting},
I am a DevOps Engineer with close to one year of hands-on experience across internship and trainee roles, and I am exploring DevOps or Linux-focused opportunities at {company}.

At NCS Pvt. Ltd., I worked on optimizing a multi-region Kafka architecture on Amazon MSK, improving disaster recovery reliability by replacing MSK Connect + MM2 with MSK Replicator for dynamic partition replication. I also executed a zero-downtime migration from CloudBees CI to Jenkins Community Edition and contributed to modernizing Kubernetes traffic management using Gateway API, Route 53 weighted routing, and cert-manager in a Primary–Secondary–DR setup.

Previously, at LinuxWorld and Netlink Software, I deployed Docker-based production environments, built Kafka–Zookeeper clusters, configured MongoDB high-availability setups, and automated CI/CD pipelines using Jenkins and Kubernetes.

My core stack includes Docker, Kubernetes, AWS, Terraform, Jenkins, Ansible, Linux (RedHat/Debian), Bash, Python, and GitHub Workflows.

I am particularly interested in contributing to {company} where scalable infrastructure, automation, and reliability engineering are key priorities. I would welcome the opportunity to discuss how I can support your DevOps initiatives.

My resume is attached for your review.

Thank you for your time and consideration.

Best regards,
Satvik Dubey
+91 7987285470
"""

# ─────────────────────────────────────────────
#  HR DATA
#  Format: domain -> list of email addresses
# ─────────────────────────────────────────────

HR_DATA: dict[str, list[str]] = {

    "chicmicstudios.in": [
        "neha.rawat@chicmicstudios.in",
    ],

    "startappss.com": [
        "hr@startappss.com",
        "ayushi.khandelwal@startappss.com",
    ],

    "nexturn.com": [
        "vidya.annapragada@nexturn.com",
        "sirisha.reddy@nexturn.com",
    ],

    "adeevatechnologies.in": [
        "hr@adeevatechnologies.in",
    ],

    "technource.com": [
        "career@technource.com",
    ],

    "abhiyantrikitech.com": [
        "hr@abhiyantrikitech.com",
    ],

    "richestsoft.in": [
        "chetan.chhabra@richestsoft.in",
    ],

    "thinkquotient.com": [
        "career@thinkquotient.com",
    ],
    "appsandwebsolutions.com": [
        "hr@appsandwebsolutions.com",
    ],

    "shiwansh.com": [
        "admin@shiwansh.com",
    ],

    "kunalbearings.com": [
        "info@kunalbearings.com",
    ],

    "ibotix.in": [
        "vanshika.sharma@ibotix.in",
    ],

    "lancesoft.com": [
        "negi.manish@lancesoft.com",
    ],

    "cybersrcc.com": [
        "pooja@cybersrcc.com",
    ],

    "thewitslab.com": [
        "nimisha.srivastava@thewitslab.com",
    ],

    "ecodesoft.com": [
        "hr@ecodesoft.com",
    ],

    "team.proofhub.com": [
        "sakshi.choudhry@team.proofhub.com",
    ],

    "sourcebae.com": [
        "swarna@sourcebae.com",
    ],
}
# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    """
    Configure dual-output logging:
      - Console  : INFO level, colored-friendly format
      - File     : DEBUG level, timestamped, written to LOG_FILE
    """
    logger = logging.getLogger("EmailSender")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # File handler
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


# ─────────────────────────────────────────────
#  HELPER UTILITIES
# ─────────────────────────────────────────────

def get_company_display_name(domain: str) -> str:
    """
    Convert a domain string into a human-readable company name.
    Example: 'nttdata.com' -> 'NTT Data'  (best-effort title-case)
    """
    name = domain.split(".")[0]           # drop TLD
    name = name.replace("-", " ")        # hyphens → spaces
    return name.title()


def derive_hr_name(email: str) -> str | None:
    """
    Attempt to derive a first name from a personal-looking email address.
    Returns None for generic addresses like hr@, careers@, apply.now@, etc.

    Examples:
        natasha.joshi@calsoftinc.com  -> 'Natasha'
        hr@calsoftinc.com             -> None
    """
    GENERIC_PREFIXES = {
        "hr", "careers", "career", "apply", "apply.now",
        "ta", "info", "contact", "jobs", "recruitment",
        "platformhiring",
    }
    local_part = email.split("@")[0].lower()

    if local_part in GENERIC_PREFIXES:
        return None

    # Extract first token split by '.' or '_'
    first = local_part.replace("_", ".").split(".")[0]

    # Filter out tokens that look like IDs / numbers
    if first.isdigit() or len(first) < 3:
        return None

    return first.capitalize()


def build_greeting(email: str) -> str:
    """Return 'Dear <Name>,' if name can be inferred, else 'Dear HR,'."""
    name = derive_hr_name(email)
    return name if name else "HR"


# ─────────────────────────────────────────────
#  RESUME ATTACHMENT
# ─────────────────────────────────────────────

def attach_resume(message: MIMEMultipart, resume_path: str, logger: logging.Logger) -> bool:
    """
    Attach the PDF resume to the email message.

    Args:
        message     : MIMEMultipart email object to attach to.
        resume_path : Filesystem path to the resume PDF.
        logger      : Logger instance for diagnostics.

    Returns:
        True on success, False if the file cannot be attached.
    """
    if not os.path.isfile(resume_path):
        logger.error("Resume not found at path: %s", resume_path)
        return False

    try:
        with open(resume_path, "rb") as fp:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fp.read())

        encoders.encode_base64(part)
        filename = os.path.basename(resume_path)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        message.attach(part)
        logger.debug("Resume attached: %s", filename)
        return True

    except OSError as exc:
        logger.error("Failed to read resume file '%s': %s", resume_path, exc)
        return False


# ─────────────────────────────────────────────
#  EMAIL CONSTRUCTION
# ─────────────────────────────────────────────

def build_email(
    sender: str,
    recipient: str,
    company: str,
    resume_path: str,
    logger: logging.Logger,
) -> MIMEMultipart | None:
    """
    Construct a complete MIMEMultipart email ready for dispatch.

    Args:
        sender      : Sender Gmail address.
        recipient   : Recipient email address.
        company     : Human-readable company name for personalisation.
        resume_path : Path to the resume PDF.
        logger      : Logger instance.

    Returns:
        A MIMEMultipart object, or None if the resume could not be attached.
    """
    greeting = build_greeting(recipient)
    body     = EMAIL_BODY_TEMPLATE.format(greeting=greeting, company=company)

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = EMAIL_SUBJECT

    msg.attach(MIMEText(body, "plain"))

    if not attach_resume(msg, resume_path, logger):
        return None  # Abort – no resume attached

    return msg


# ─────────────────────────────────────────────
#  SINGLE EMAIL SEND  (with retry)
# ─────────────────────────────────────────────

def send_email(
    smtp_conn: smtplib.SMTP,
    sender: str,
    recipient: str,
    company: str,
    resume_path: str,
    dry_run: bool,
    logger: logging.Logger,
) -> bool:
    """
    Send a single email to one recipient, with up to RETRY_LIMIT attempts.

    Args:
        smtp_conn   : An authenticated SMTP connection.
        sender      : Sender Gmail address.
        recipient   : Recipient email address.
        company     : Company display name for body personalisation.
        resume_path : Path to resume PDF.
        dry_run     : If True, skip actual transmission.
        logger      : Logger instance.

    Returns:
        True if the email was sent (or dry-run simulated), False otherwise.
    """
    msg = build_email(sender, recipient, company, resume_path, logger)
    if msg is None:
        logger.error("[SKIP] Could not build email for %s → %s (resume issue)", company, recipient)
        return False

    if dry_run:
        logger.info("[DRY-RUN] Would send to %-40s  company=%s", recipient, company)
        return True

    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            smtp_conn.sendmail(sender, recipient, msg.as_string())
            logger.info("[SUCCESS] Sent to %-40s  company=%s  attempt=%d", recipient, company, attempt)
            return True

        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning(
                "[REFUSED] Recipient refused (%s): %s — attempt %d/%d",
                recipient, exc, attempt, RETRY_LIMIT,
            )
        except smtplib.SMTPServerDisconnected as exc:
            logger.warning(
                "[DISCONNECTED] SMTP disconnected (%s): %s — attempt %d/%d",
                recipient, exc, attempt, RETRY_LIMIT,
            )
        except smtplib.SMTPException as exc:
            logger.warning(
                "[SMTP ERROR] (%s): %s — attempt %d/%d",
                recipient, exc, attempt, RETRY_LIMIT,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[UNEXPECTED ERROR] (%s): %s — attempt %d/%d",
                recipient, exc, attempt, RETRY_LIMIT,
            )

        if attempt < RETRY_LIMIT:
            logger.debug("Waiting %ds before retry...", RETRY_DELAY)
            time.sleep(RETRY_DELAY)

    logger.error("[FAILED] All %d attempts exhausted for %s", RETRY_LIMIT, recipient)
    return False


# ─────────────────────────────────────────────
#  MAIN ORCHESTRATOR
# ─────────────────────────────────────────────

def main() -> None:
    """
    Entry-point:
      1. Parse CLI arguments.
      2. Validate environment variables & resume file.
      3. Open an authenticated SMTP session.
      4. Iterate HR_DATA and dispatch emails with inter-company delay.
      5. Print a run summary.
    """

    # ── CLI Arguments ──────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Cold Email Sender – DevOps Job Applications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate sending without actually dispatching emails.",
    )
    parser.add_argument(
        "--resume",
        default=DEFAULT_RESUME,
        metavar="PATH",
        help=f"Path to resume PDF (default: {DEFAULT_RESUME})",
    )
    args = parser.parse_args()

    logger = setup_logging()

    logger.info("=" * 60)
    logger.info("Cold Email Sender — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if args.dry_run:
        logger.info("*** DRY-RUN MODE — no emails will be sent ***")
    logger.info("Resume : %s", args.resume)
    logger.info("=" * 60)

    # ── Validate Resume ────────────────────────────────────────────────────
    if not os.path.isfile(args.resume):
        logger.critical(
            "Resume file not found: '%s'. "
            "Place your resume PDF in the same directory or use --resume <path>.",
            args.resume,
        )
        sys.exit(1)

    # ── Read Credentials from Environment ─────────────────────────────────
    sender_email = os.environ.get("SENDER_EMAIL", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASS", "").strip()

    if not sender_email or not app_password:
        logger.critical(
            "Environment variables SENDER_EMAIL and/or GMAIL_APP_PASS are not set.\n"
            "  Linux/macOS : export SENDER_EMAIL='you@gmail.com'\n"
            "                export GMAIL_APP_PASS='xxxx xxxx xxxx xxxx'\n"
            "  Windows CMD : set SENDER_EMAIL=you@gmail.com\n"
            "                set GMAIL_APP_PASS=xxxx xxxx xxxx xxxx"
        )
        sys.exit(1)

    # ── Counters ───────────────────────────────────────────────────────────
    total_sent    = 0
    total_failed  = 0
    total_skipped = 0

    # ── SMTP Session ───────────────────────────────────────────────────────
    try:
        logger.info("Connecting to SMTP server %s:%d …", SMTP_HOST, SMTP_PORT)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()          # Upgrade to TLS
            smtp.ehlo()
            smtp.login(sender_email, app_password)
            logger.info("Authenticated successfully as %s", sender_email)
            logger.info("-" * 60)

            # ── Iterate Companies ──────────────────────────────────────────
            for idx, (domain, recipients) in enumerate(HR_DATA.items(), start=1):
                company = get_company_display_name(domain)
                logger.info(
                    "[%d/%d] Processing: %s (%d recipient(s))",
                    idx, len(HR_DATA), company, len(recipients),
                )

                for recipient in recipients:
                    success = send_email(
                        smtp_conn   = smtp,
                        sender      = sender_email,
                        recipient   = recipient,
                        company     = company,
                        resume_path = args.resume,
                        dry_run     = args.dry_run,
                        logger      = logger,
                    )
                    if success:
                        total_sent += 1
                    else:
                        total_failed += 1

                # Delay between companies (skip delay after last entry)
                if idx < len(HR_DATA):
                    logger.debug("Sleeping %ds before next company…", DELAY_SECONDS)
                    if not args.dry_run:
                        time.sleep(DELAY_SECONDS)

    except smtplib.SMTPAuthenticationError:
        logger.critical(
            "SMTP Authentication Failed! "
            "Verify SENDER_EMAIL and GMAIL_APP_PASS are correct, "
            "and that 2-Step Verification + App Passwords are enabled on your Google Account."
        )
        sys.exit(1)
    except smtplib.SMTPConnectError as exc:
        logger.critical("Cannot connect to SMTP server: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")

    # ── Summary ────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("RUN COMPLETE")
    logger.info("  Sent    : %d", total_sent)
    logger.info("  Failed  : %d", total_failed)
    logger.info("  Skipped : %d", total_skipped)
    logger.info("  Log     : %s", os.path.abspath(LOG_FILE))
    logger.info("=" * 60)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    main()
