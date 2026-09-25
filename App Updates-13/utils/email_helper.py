"""
Email Helper — Complete OTP + Notification System
==================================================
Sab emails info@uqn88.store se bhejte hain.
"""

import logging
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


# ============================================
# HTML TEMPLATE
# ============================================

def get_html_template(title, content, action_link=None, button_text="View Details"):
    """
    Professional responsive HTML email layout
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


# ============================================
# MAIN EMAIL SENDER
# ============================================

def send_notification_email(recipient_email, subject, body_html, body_text=None, action_link=None):
    """
    System notifications bhejta hai (info@uqn88.store se).
    """
    sender_email = "info@uqn88.store"
    from_header = f"uqn88 Info Desk <{sender_email}>"
    
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
        logger.info(f"✅ Email sent to {to_list}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_list}: {str(e)}")
        return False


# ============================================
# CUSTOM USER EMAIL
# ============================================

def send_custom_user_email(username, recipient_email, subject, body_html, body_text=None, action_link=None):
    """
    User-composed emails ke liye (username@uqn88.store se).
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
        logger.info(f"✅ Custom email sent to {to_list}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send user email via {from_header}: {str(e)}")
        return False


# ============================================
# ✅ OTP EMAIL FUNCTION (NAYA)
# ============================================

def send_otp_email(recipient_email, otp_code, customer_name="Customer", purpose="verification"):
    """
    Customer ko OTP email bhejta hai.
    
    Args:
        recipient_email: Customer ka email
        otp_code: 6-digit OTP
        customer_name: Customer ka naam
        purpose: 'register', 'login', 'order', 'forgot_password'
    
    Returns:
        bool: True agar send ho gayi
    """
    subject = f"🔐 Your OTP Code - {otp_code}"
    
    purpose_text = {
        'register': 'Account Registration',
        'login': 'Login Verification',
        'order': 'Order Verification',
        'forgot_password': 'Password Reset',
        'email_verification': 'Email Verification',
    }.get(purpose, 'Verification')
    
    body_html = f"""
    <div style="text-align: center; padding: 20px 0;">
        <p style="font-size: 16px; color: #374151;">
            Assalam o Alaikum <strong>{customer_name}</strong>,
        </p>
        
        <p style="font-size: 14px; color: #6b7280;">
            Aap ka <strong>{purpose_text}</strong> ke liye OTP code yeh hai:
        </p>
        
        <div style="background-color: #f8f9fa; border: 2px dashed #ffb703; 
                    border-radius: 12px; padding: 25px; margin: 25px 0;">
            <p style="font-size: 42px; font-weight: bold; color: #1a1d2e; 
                      letter-spacing: 8px; margin: 0; font-family: monospace;">
                {otp_code}
            </p>
        </div>
        
        <p style="font-size: 13px; color: #dc3545; font-weight: 600;">
            ⏰ Yeh OTP sirf 5 minute ke liye valid hai
        </p>
        
        <p style="font-size: 12px; color: #9ca3af; margin-top: 20px;">
            Agar aap ne OTP request nahi ki, to is email ko ignore karein.
        </p>
        
        <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; 
                    padding: 12px; margin-top: 20px; text-align: left; border-radius: 4px;">
            <p style="font-size: 12px; color: #856404; margin: 0;">
                <strong>⚠️ Security Warning:</strong> 
                Yeh OTP kisi ke saath share na karein. uqn88 Store kabhi 
                bhi aapse OTP nahi maangega.
            </p>
        </div>
    </div>
    """
    
    body_text = f"""
Assalam o Alaikum {customer_name},

Aap ka {purpose_text} ke liye OTP code: {otp_code}

Yeh OTP sirf 5 minute ke liye valid hai.

Agar aap ne OTP request nahi ki, to is email ko ignore karein.

Shukriya,
uqn88 Store
    """
    
    return send_notification_email(
        recipient_email=recipient_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
    )


# ============================================
# ALIASES (Backward Compatibility)
# ============================================

send_system_email = send_notification_email
send_customer_otp = send_otp_email