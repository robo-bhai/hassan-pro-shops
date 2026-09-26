"""
Email Helper — Complete OTP + Notification + Order System
===========================================================
Default sender: info@uqn88.store
Fully responsive HTML email layout with Dark Mode & Outlook compatibility.
"""

import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


# ============================================
# BASE HTML TEMPLATE (Modern & Bulletproof)
# ============================================

def get_html_template(title, content, action_link=None, button_text="View Details", accent_color="#ffb703"):
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
                            <td align="center" bgcolor="{accent_color}" style="border-radius: 6px;">
                                <a href="{action_link}" target="_blank" style="font-size: 14px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-weight: 700; color: #111827; text-decoration: none; padding: 13px 32px; border-radius: 6px; border: 1px solid {accent_color}; display: inline-block;">
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
            .responsive-table th, .responsive-table td {{ padding: 8px 6px !important; font-size: 13px !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <div style="background-color: #f3f4f6; padding: 30px 10px;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 0 auto;" class="email-container">
            <tr>
                <td align="center" style="padding: 0;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e5e7eb; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                        
                        <!-- Header -->
                        <tr>
                            <td class="header-padding" style="background-color: #111827; padding: 24px 32px; text-align: left; border-bottom: 3px solid {accent_color};">
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
                                <p style="margin: 0 0 4px 0; font-weight: 500;">This is an automated email from <strong>uqn88 Store</strong>.</p>
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
# MAIN SENDER CORE ENGINE
# ============================================

def send_notification_email(recipient_email, subject, body_html, body_text=None, action_link=None, button_text="View Details"):
    """
    System notifications bhejta hai (info@uqn88.store se).
    """
    sender_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'info@uqn88.store')
    from_header = f"UQN88 Store <{sender_email}>"
    
    to_list = [recipient_email] if isinstance(recipient_email, str) else recipient_email

    if not to_list:
        logger.warning("Email send skipped: No recipient email provided.")
        return False

    plain_content = body_text if body_text else "Please view this email in an HTML-compatible client."

    if "<html>" not in body_html.lower():
        full_html = get_html_template(title=subject, content=body_html, action_link=action_link, button_text=button_text)
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

        # Tracking Headers Override
        email.extra_headers['X-Mailin-custom'] = '{"click_tracking": 0}'
        email.extra_headers['X-SMTPAPI'] = '{"tracking_settings": {"click_tracking": {"enable": false}}}'
        email.extra_headers['o:tracking-clicks'] = 'no'
        email.extra_headers['X-No-Track'] = '1'

        email.send(fail_silently=False)
        logger.info(f"✅ Email sent to {to_list}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_list}: {str(e)}")
        return False


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

        email.extra_headers['X-Mailin-custom'] = '{"click_tracking": 0}'
        email.extra_headers['X-SMTPAPI'] = '{"tracking_settings": {"click_tracking": {"enable": false}}}'
        email.extra_headers['o:tracking-clicks'] = 'no'
        email.extra_headers['X-No-Track'] = '1'

        email.send(fail_silently=False)
        logger.info(f"✅ Custom email sent to {to_list}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send user email via {from_header}: {str(e)}")
        return False


# ============================================
# 1. OTP EMAIL TEMPLATE
# ============================================

def send_otp_email(recipient_email, otp_code, customer_name="Customer", purpose="verification", verify_url=None):
    """
    Customer ko OTP email + Instant Verification Link bhejta hai.
    """
    subject = f"🔐 Your OTP Code - {otp_code}"
    
    purpose_text = {
        'register': 'Account Registration',
        'login': 'Login Verification',
        'order': 'Order Verification',
        'forgot_password': 'Password Reset',
        'email_verification': 'Email Verification',
    }.get(purpose, 'Verification')
    
    verify_button_html = ""
    if verify_url:
        verify_button_html = f"""
        <div style="margin: 28px 0; text-align: center;">
            <p style="font-size: 13px; color: #6b7280; font-weight: 600; margin-bottom: 12px;">
                — OR CLICK THE BUTTON BELOW —
            </p>
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                    <td align="center">
                        <table border="0" cellpadding="0" cellspacing="0">
                            <tr>
                                <td align="center" bgcolor="#2563eb" style="border-radius: 8px;">
                                    <a href="{verify_url}" target="_blank" style="font-size: 14px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-weight: 700; color: #ffffff; text-decoration: none; padding: 13px 26px; border-radius: 8px; border: 1px solid #2563eb; display: inline-block;">
                                        ⚡ Verify & Proceed Instantly
                                    </a>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
            <p style="font-size: 12px; color: #6b7280; margin-top: 14px; word-break: break-all;">
                Direct Link: <a href="{verify_url}" target="_blank" style="color: #2563eb; font-family: monospace;">{verify_url}</a>
            </p>
        </div>
        """

    body_content = f"""
    <div style="text-align: left;">
        <p style="font-size: 15px; color: #111827; margin-top: 0; margin-bottom: 12px;">
            Assalam o Alaikum <strong>{customer_name}</strong>,
        </p>
        
        <p style="font-size: 14px; color: #4b5563; margin-top: 0; margin-bottom: 20px;">
            Aap ka <strong>{purpose_text}</strong> ke liye One-Time Password (OTP) neeche diya gaya hai:
        </p>
        
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin: 24px 0;">
            <tr>
                <td align="center" class="otp-box" style="background-color: #f9fafb; border: 2px dashed #ffb703; border-radius: 10px; padding: 22px 16px;">
                    <span class="otp-code" style="font-size: 38px; font-weight: 800; color: #111827; letter-spacing: 8px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace; display: block; line-height: 1;">
                        {otp_code}
                    </span>
                </td>
            </tr>
        </table>
        
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px;">
            <tr>
                <td align="center">
                    <span style="font-size: 12px; color: #dc2626; font-weight: 700; background-color: #fef2f2; padding: 6px 14px; border-radius: 20px; border: 1px solid #fee2e2; display: inline-block;">
                        ⏰ Valid for 5 minutes only
                    </span>
                </td>
            </tr>
        </table>

        {verify_button_html}
        
        <p style="font-size: 13px; color: #6b7280; margin-bottom: 24px; text-align: center;">
            Agar aap ne OTP request nahi ki, to is email ko ignore karein.
        </p>
        
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

    return send_notification_email(
        recipient_email=recipient_email,
        subject=subject,
        body_html=body_content
    )


# ============================================
# 2. CUSTOMER ORDER CONFIRMATION EMAIL
# ============================================

def send_customer_order_email(recipient_email, order_no, customer_name, order_summary, total_amount, payment_method="COD", address="N/A"):
    """
    Customer ko Order Confirmation Email bhejta hai with detailed Itemized Breakdown.
    """
    subject = f"🛍️ Order Confirmed #{order_no} - uqn88 Store"

    items_rows = ""
    for item in order_summary:
        items_rows += f"""
        <tr>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; color: #111827; font-weight: 500;">{item['name']}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: center; color: #4b5563;">{item['qty']}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: right; color: #4b5563;">Rs. {item['price']:,.2f}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: right; color: #111827; font-weight: 600;">Rs. {item['total']:,.2f}</td>
        </tr>
        """

    content = f"""
    <p style="font-size: 15px; color: #111827; margin-top: 0;">
        Assalam o Alaikum <strong>{customer_name}</strong>,
    </p>
    <p style="font-size: 14px; color: #4b5563;">
        Shukriya! Aap ka order <strong>#{order_no}</strong> successfully receive ho gaya hai. Hum jald hi isse dispatch karenge.
    </p>

    <!-- Order Info Card -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb; margin: 20px 0;">
        <tr>
            <td style="padding: 16px;">
                <p style="margin: 0 0 6px 0; font-size: 13px; color: #4b5563;"><strong>Order Number:</strong> #{order_no}</p>
                <p style="margin: 0 0 6px 0; font-size: 13px; color: #4b5563;"><strong>Payment Method:</strong> <span style="background-color: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px;">{str(payment_method).upper()}</span></p>
                <p style="margin: 0; font-size: 13px; color: #4b5563;"><strong>Shipping Address:</strong> {address}</p>
            </td>
        </tr>
    </table>

    <!-- Items Table -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%" class="responsive-table" style="margin-top: 15px; font-size: 14px;">
        <thead>
            <tr style="background-color: #f3f4f6;">
                <th style="padding: 10px 12px; text-align: left; font-weight: 700; color: #374151; border-bottom: 2px solid #d1d5db;">Item</th>
                <th style="padding: 10px 12px; text-align: center; font-weight: 700; color: #374151; border-bottom: 2px solid #d1d5db;">Qty</th>
                <th style="padding: 10px 12px; text-align: right; font-weight: 700; color: #374151; border-bottom: 2px solid #d1d5db;">Price</th>
                <th style="padding: 10px 12px; text-align: right; font-weight: 700; color: #374151; border-bottom: 2px solid #d1d5db;">Total</th>
            </tr>
        </thead>
        <tbody>
            {items_rows}
            <tr>
                <td colspan="3" style="padding: 12px; text-align: right; font-weight: 700; color: #111827; border-top: 2px solid #111827;">Grand Total:</td>
                <td style="padding: 12px; text-align: right; font-weight: 800; color: #16a34a; font-size: 16px; border-top: 2px solid #111827;">Rs. {total_amount:,.2f}</td>
            </tr>
        </tbody>
    </table>
    """

    return send_notification_email(
        recipient_email=recipient_email,
        subject=subject,
        body_html=content
    )


# ============================================
# 3. ADMIN NEW ORDER ALERT EMAIL
# ============================================

def send_admin_order_notification(admin_emails, order_no, customer_name, customer_phone, total_amount, items_count, payment_method="COD", order_link=None):
    """
    Admin ko naye order placement par instant alert Email bhejta hai.
    """
    subject = f"🚨 NEW ORDER #{order_no} - Rs. {total_amount:,.2f}"

    content = f"""
    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 14px 16px; border-radius: 0 6px 6px 0; margin-bottom: 20px;">
        <p style="margin: 0; color: #991b1b; font-weight: 700; font-size: 15px;">
            🛒 Web Store par Naya Order Aaya Hai!
        </p>
    </div>

    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 20px;">
        <tr>
            <td style="padding: 16px;">
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;"><strong>Order ID:</strong> #{order_no}</p>
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;"><strong>Customer:</strong> {customer_name}</p>
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;"><strong>Phone:</strong> {customer_phone}</p>
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;"><strong>Items Count:</strong> {items_count}</p>
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;"><strong>Payment:</strong> <span style="background-color: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 12px;">{str(payment_method).upper()}</span></p>
                <p style="margin: 0; font-size: 16px; color: #16a34a; font-weight: 800;"><strong>Total Value:</strong> Rs. {total_amount:,.2f}</p>
            </td>
        </tr>
    </table>
    """

    return send_notification_email(
        recipient_email=admin_emails,
        subject=subject,
        body_html=content,
        action_link=order_link,
        button_text="⚙️ Manage Order in Admin Panel"
    )


# ============================================
# 4. ORDER STATUS UPDATE EMAIL
# ============================================

def send_order_status_update_email(recipient_email, order_no, customer_name, new_status, tracking_url=None):
    """
    Order Status Change hone par Customer ko Email notification bheje ga.
    """
    status_config = {
        'confirmed': ('Order Confirmed', '✅', '#16a34a'),
        'processing': ('Processing & Packing', '⚙️', '#2563eb'),
        'ready': ('Ready to Ship', '📦', '#8b5cf6'),
        'dispatched': ('Out for Delivery', '🚚', '#0284c7'),
        'delivered': ('Delivered Successfully', '🎉', '#16a34a'),
        'cancelled': ('Order Cancelled', '❌', '#dc2626'),
    }

    status_label, emoji, status_color = status_config.get(new_status.lower(), ('Status Update', '📢', '#ffb703'))

    subject = f"{emoji} Order #{order_no} Update: {status_label}"

    content = f"""
    <p style="font-size: 15px; color: #111827; margin-top: 0;">
        Assalam o Alaikum <strong>{customer_name}</strong>,
    </p>
    <p style="font-size: 14px; color: #4b5563;">
        Aap ke Order <strong>#{order_no}</strong> ka status update kar diya gaya hai:
    </p>

    <div style="text-align: center; margin: 24px 0;">
        <span style="font-size: 16px; font-weight: 800; color: #ffffff; background-color: {status_color}; padding: 10px 24px; border-radius: 30px; display: inline-block;">
            {emoji} {status_label.upper()}
        </span>
    </div>
    """

    return send_notification_email(
        recipient_email=recipient_email,
        subject=subject,
        body_html=content,
        action_link=tracking_url,
        button_text="🔍 Track Your Order"
    )


# ============================================
# ALIASES (Backward Compatibility)
# ============================================

send_system_email = send_notification_email
send_customer_otp = send_otp_email
