import logging
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def get_html_template(title, content, action_link=None, button_text="View Details"):
    """
    Generates a responsive HTML email layout with styled container, header,
    typography, and a CTA button.
    """
    button_html = ""
    if action_link:
        button_html = f"""
        <div style="text-align: center; margin: 30px 0 20px 0;">
            <a href="{action_link}" style="background-color: #ffb703; color: #111111; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 14px; display: inline-block; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                {button_text}
            </a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f4f6f9; padding: 20px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border: 1px solid #e5e7eb;">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: #111827; padding: 24px 30px; text-align: left;">
                            <h1 style="color: #ffb703; margin: 0; font-size: 20px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;">uqn88 Store</h1>
                        </td>
                    </tr>
                    
                    <!-- Content Area -->
                    <tr>
                        <td style="padding: 30px; text-align: left; color: #374151; font-size: 15px; line-height: 1.6;">
                            <h2 style="color: #111827; font-size: 18px; margin-top: 0; margin-bottom: 16px; font-weight: 600;">{title}</h2>
                            <div style="color: #4b5563; font-size: 14px; margin-bottom: 20px;">
                                {content}
                            </div>
                            {button_html}
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f9fafb; padding: 20px 30px; text-align: center; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 12px;">
                            <p style="margin: 0 0 6px 0;">This is an automated notification from <strong>uqn88 Store</strong>.</p>
                            <p style="margin: 0;">&copy; uqn88.store — All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def send_notification_email(recipient_email, subject, body_html, body_text=None, action_link=None):
    """
    Hamesha info@uqn88.store se user ke saved personal email par email bhejta hai.
    Wrapper layout automatic apply hota hai agar simple HTML string pass ho.
    """
    sender_email = "info@uqn88.store"
    from_header = f"UQN Info <{sender_email}>"
    
    to_list = [recipient_email] if isinstance(recipient_email, str) else recipient_email

    if not to_list:
        logger.warning("Email send skipped: No recipient email provided.")
        return False

    plain_content = body_text if body_text else "Please view this email in an HTML-compatible client."

    # Wrap in responsive layout if raw content passed
    if "<html>" not in body_html.lower():
        full_html = get_html_template(title=subject, content=body_html, action_link=action_link)
    else:
        full_html = body_html

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_content,
            from_email=from_header,
            to=to_list,
        )
        if full_html:
            email.attach_alternative(full_html, "text/html")

        email.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_list} from {from_header}: {str(e)}")
        return False


def send_custom_user_email(username, recipient_email, subject, body_html, body_text=None, action_link=None):
    """
    User ke in-app compose mail system ke liye (Jab user manual email compose kare).
    """
    sender_email = f"{username.lower()}@uqn88.store"
    from_header = f"{username} <{sender_email}>"
    
    to_list = [recipient_email] if isinstance(recipient_email, str) else recipient_email

    if not to_list:
        logger.warning("Custom email send skipped: No recipient email provided.")
        return False

    plain_content = body_text if body_text else "Please view this email in an HTML-compatible client."

    if "<html>" not in body_html.lower():
        full_html = get_html_template(title=subject, content=body_html, action_link=action_link)
    else:
        full_html = body_html

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_content,
            from_email=from_header,
            to=to_list,
        )
        if full_html:
            email.attach_alternative(full_html, "text/html")

        email.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send user email via {from_header}: {str(e)}")
        return False


# Backward compatibility alias for models.py import
send_system_email = send_notification_email
