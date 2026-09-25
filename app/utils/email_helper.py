"""
Email Helper — Complete OTP + Notification System
==================================================
Sab emails info@uqn88.store se bhejte hain.
"""

import logging
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


# ============================================
# HTML TEMPLATE (Enhanced & Rock-Solid Responsive)
# ============================================

def get_html_template(title, content, action_link=None, button_text="View Details"):
    """
    Professional responsive HTML email layout with Dark Mode & Outlook compatibility.
    """
    button_html = ""
    if action_link:
        button_html = f"""
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top: 28px; margin-bottom: 24px;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0">
                        <tr>
                            <td align="center" bgcolor="#ffb703" style="border-radius: 6px;">
                                <a href="{action_link}" target="_blank" style="font-size: 14px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-weight: 700; color: #111827; text-decoration: none; padding: 13px 32px; border-radius: 6px; border: 1px solid #ffb703; display: inline-block;">
                                    {button_text}
                                </a>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """

    return f"""<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="x-apple-disable-message-reformatting">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>{title}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style>
        :root {{ color-scheme: light dark; supported-color-schemes: light dark; }}
        body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        table {{ border-collapse: collapse !important; }}
        body {{ height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; background-color: #f3f4f6; }}
        
        @media screen and (max-width: 600px) {{
            .email-container {{ width: 100% !important; margin: auto !important; }}
            .content-padding {{ padding: 24px 20px !important; }}
            .header-padding {{ padding: 20px 20px !important; }}
            .otp-box {{ padding: 20px 10px !important; }}
            .otp-code {{ font-size: 32px !important; letter-spacing: 6px !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <div style="background-color: #f3f4f6; padding: 30px 10px;">
        <!-- Container -->
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 0 auto;" class="email-container">
            <tr>
                <td align="center" style="padding: 0;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e5e7eb; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                        
                        <!-- Header -->
                        <tr>
                            <td class="header-padding" style="background-color: #111827; padding: 24px 32px; text-align: left; border-bottom: 3px solid #ffb703;">
                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                    <tr>
                                        <td>
                                            <span style="color: #ffb703; font-size: 20px; font-weight: 800; letter-spacing: 0.8px; text-transform: uppercase; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">uqn88 Store</span>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        
                        <!-- Main Content Area -->
                        <tr>
                            <td class="content-padding" style="padding: 36px 32px; text-align: left; color: #374151; font-size: 15px; line-height: 1.6;">
                                <h2 style="color: #111827; font-size: 19px; margin-top: 0; margin-bottom: 18px; font-weight: 700; letter-spacing: -0.2px;">{title}</h2>
                                
                                <div style="color: #4b5563; font-size: 14px; line-height: 1.6;">
                                    {content}
                                </div>
                                
                                {button_html}
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #f9fafb; padding: 24px 32px; text-align: center; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; line-height: 1.5;">
                                <p style="margin: 0 0 4px 0; font-weight: 500;">This is an automated notification from <strong>uqn88 Store</strong>.</p>
                                <p style="margin: 0; color: #9ca3af;">&copy; uqn88.store — All rights reserved.</p>
                            </td>
                        </tr>
                        
                    </table>
                </td>
            </tr>
        </table>
    </div>
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
    from_header = f"UQN88 <{sender_email}>"
    
    to_list = [recipient_email] if isinstance(recipient_email, str) else recipient_email

    if not to_list:
        logger.warning("Email send skipped: No recipient email provided.")
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
# ✅ OTP EMAIL FUNCTION (ENHANCED UI)
# ============================================

def send_otp_email(recipient_email, otp_code, customer_name="Customer", purpose="verification"):
    """
    Customer ko high-converting & ultra-clean OTP email bhejta hai.
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
    <div style="text-align: left;">
        <p style="font-size: 15px; color: #111827; margin-top: 0; margin-bottom: 12px;">
            Assalam o Alaikum <strong>{customer_name}</strong>,
        </p>
        
        <p style="font-size: 14px; color: #4b5563; margin-top: 0; margin-bottom: 20px;">
            Aap ka <strong>{purpose_text}</strong> ke liye One-Time Password (OTP) neeche diya gaya hai:
        </p>
        
        <!-- OTP Card -->
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td align="center" class="otp-box" style="background-color: #f9fafb; border: 2px dashed #ffb703; border-radius: 10px; padding: 22px 16px;">
                    <span class="otp-code" style="font-size: 38px; font-weight: 800; color: #111827; letter-spacing: 8px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; display: block; line-height: 1;">
                        {otp_code}
                    </span>
                </td>
            </tr>
        </table>
        
        <!-- Expiry Badge -->
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px;">
            <tr>
                <td align="center">
                    <span style="font-size: 12px; color: #dc2626; font-weight: 700; background-color: #fef2f2; padding: 6px 14px; border-radius: 20px; border: 1px solid #fee2e2; display: inline-block;">
                        ⏰ Valid for 5 minutes only
                    </span>
                </td>
            </tr>
        </table>
        
        <p style="font-size: 13px; color: #6b7280; margin-bottom: 24px; text-align: center;">
            Agar aap ne OTP request nahi ki, to is email ko ignore karein.
        </p>
        
        <!-- Security Callout -->
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #fffbe3; border-left: 4px solid #ffb703; border-radius: 0 6px 6px 0;">
            <tr>
                <td style="padding: 12px 16px;">
                    <p style="font-size: 12px; color: #78350f; margin: 0; line-height: 1.5;">
                        <strong>⚠️ Security Warning:</strong> 
                        Yeh OTP kisi ke saath share na karein. uqn88 Store aap se kabhi bhi OTP nahi maangega.
                    </p>
                </td>
            </tr>
        </table>
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
