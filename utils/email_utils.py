import os
import logging
import aiosmtplib
from email.message import EmailMessage
from email_validator import validate_email, EmailNotValidError # Import validator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# --- Load and Validate Email Environment Variables --- 
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_PORT_STR = os.getenv("MAIL_PORT", "587")
MAIL_STARTTLS_STR = os.getenv("MAIL_STARTTLS", "True")
MAIL_SSL_TLS_STR = os.getenv("MAIL_SSL_TLS", "False")

required_vars = {
    "MAIL_USERNAME": MAIL_USERNAME,
    "MAIL_PASSWORD": MAIL_PASSWORD,
    "MAIL_FROM": MAIL_FROM,
    "MAIL_SERVER": MAIL_SERVER,
    "MAIL_PORT": MAIL_PORT_STR
}

missing_vars = [name for name, value in required_vars.items() if not value]
if missing_vars:
    raise EnvironmentError(f"Missing required email environment variables: {', '.join(missing_vars)}. Please check your .env file.")

try:
    MAIL_PORT = int(MAIL_PORT_STR)
except ValueError:
    raise EnvironmentError(f"Invalid MAIL_PORT value: '{MAIL_PORT_STR}'. Must be an integer.")

# --- Parse Boolean Env Vars --- 
# Handles "True", "true", "1", "yes" as True, otherwise False
MAIL_STARTTLS = MAIL_STARTTLS_STR.lower() in ('true', '1', 'yes')
MAIL_SSL_TLS = MAIL_SSL_TLS_STR.lower() in ('true', '1', 'yes')
# --- End Configuration Loading --- 

async def send_verification_email(to_email: str, token: str, base_url: str):
    """Sends a verification email using aiosmtplib, restricted by domain."""
    
    # 1. Validate Email Format and Domain
    try:
        # Basic validation
        validation = validate_email(to_email, check_deliverability=False) # Don't check MX records here
        email_normalized = validation.normalized
        
        # Domain Check
        if not email_normalized.endswith("@mamba.agency"):
            logger.warning(f"Attempted to send verification email to non-approved domain: {to_email}")
            # Decide action: Silently ignore or raise an error?
            # Raising an error might expose domain restriction externally.
            # Let's silently ignore for now.
            # return 
            raise ValueError(f"Email domain not allowed: {to_email}. Must end with @mamba.agency")
            
    except EmailNotValidError as e:
        logger.error(f"Invalid email format provided: {to_email}. Error: {e}")
        raise ValueError(f"Invalid email format: {to_email}") from e

    # 2. Construct Email
    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = email_normalized
    message["Subject"] = "Verify Your Email Address for Mamba Agency"
    
    verification_link = f"{base_url}/verify-email?token={token}"
    
    # Basic HTML Body
    html_content = f"""
    <html>
        <body>
            <h2>Welcome to Mamba Agency!</h2>
            <p>Please click the link below to verify your email address:</p>
            <p><a href="{verification_link}">Verify Email</a></p>
            <p>If you did not request this, please ignore this email.</p>
            <p>Link: {verification_link}</p>
        </body>
    </html>
    """
    message.set_content("Please enable HTML to view this email.") # Fallback for non-HTML clients
    message.add_alternative(html_content, subtype='html')

    # 3. Send Email using aiosmtplib
    try:
        smtp_client = aiosmtplib.SMTP(
            hostname=MAIL_SERVER,
            port=MAIL_PORT,
            use_tls=MAIL_SSL_TLS # use_tls is for implicit TLS (usually port 465)
        )
        async with smtp_client:
            # Handle STARTTLS if not using implicit TLS (usually port 587)
            if not MAIL_SSL_TLS and MAIL_STARTTLS:
                await smtp_client.starttls()
            
            # Login
            await smtp_client.login(MAIL_USERNAME, MAIL_PASSWORD)
            
            # Send
            await smtp_client.send_message(message)
            logger.info(f"Verification email successfully sent to {email_normalized}")
            
    except aiosmtplib.SMTPException as e:
        logger.error(f"SMTP Error sending email to {email_normalized}: {e.code} {e.message}")
        # Raise a more generic error to avoid leaking details potentially
        raise RuntimeError(f"Failed to send verification email due to SMTP error: {e.code}") from e
    except OSError as e:
        logger.error(f"Network Error sending email to {email_normalized}: {e}")
        raise RuntimeError(f"Failed to send verification email due to network error.") from e
    except Exception as e:
        logger.error(f"Unexpected Error sending email to {email_normalized}: {e}", exc_info=True)
        raise RuntimeError(f"An unexpected error occurred while sending the verification email.") from e 