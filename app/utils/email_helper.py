from django.core.mail import EmailMessage
import logging

logger = logging.getLogger(__name__)

def send_custom_user_email(username, recipient_email, subject, body_html, body_text=None):
    """
    User ke dynamic username@uqn88.store address se email bhejne ka helper.
    """
    sender_email = f"{username.lower()}@uqn88.store"
    from_header = f"{username} <{sender_email}>"
    
    # Single string email ko list mein convert karein agar zaroorat ho
    to_list = [recipient_email] if isinstance(recipient_email, str) else recipient_email

    email = EmailMessage(
        subject=subject,
        body=body_html,
        from_email=from_header,
        to=to_list,
    )
    email.content_subtype = "html"
    
    if body_text:
        email.body = body_text

    try:
        email.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send user email via {from_header}: {str(e)}")
        return False


def send_system_email(recipient_emails, subject, body_html, sender_prefix="info", sender_name="uqn88 System", body_text=None):
    """
    Official system emails (e.g. info@uqn88.store) se saved users ko email bhejne ka helper.
    Single email (string) aur Multiple emails (list) dono ko support karta hai.
    """
    sender_email = f"{sender_prefix.lower()}@uqn88.store"
    from_header = f"{sender_name} <{sender_email}>"
    
    # Agar recipient single email string ho to usko list banayein
    if isinstance(recipient_emails, str):
        to_list = [recipient_emails]
    else:
        to_list = list(recipient_emails)

    if not to_list:
        logger.warning("Email send cancelled: recipient_emails list is empty.")
        return False

    email = EmailMessage(
        subject=subject,
        body=body_html,
        from_email=from_header,
        to=to_list,
    )
    email.content_subtype = "html"

    if body_text:
        email.body = body_text

    try:
        email.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send system email via {from_header}: {str(e)}")
        return False
