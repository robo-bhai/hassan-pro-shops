# ============================================
# ✅ CHAT NOTIFICATION EMAIL
# ============================================

def send_chat_notification_email(
    admin_email,
    customer_name,
    customer_phone,
    message_preview,
    chat_link,
    is_guest=False,
    unread_count=1
):
    """Admin ko chat message ka email bhejo"""
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    
    try:
        customer_type = "Guest User" if is_guest else "Customer"
        
        subject = f"💬 New Chat Message from {customer_name}"
        
        body_text = f"""
New chat message received!

Customer: {customer_name}
Type: {customer_type}
Phone: {customer_phone or 'N/A'}

Message:
{message_preview}

Reply now: {chat_link}

---
Automated notification from {getattr(settings, 'SITE_NAME', 'Your Store')} Live Chat
        """.strip()
        
        body_html = f"""
<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 0; font-family: -apple-system, sans-serif; background: #f1f5f9;">
    <div style="max-width: 600px; margin: 20px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
        
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; color: white;">
            <h1 style="margin: 0 0 4px; font-size: 20px; font-weight: 800;">💬 New Chat Message</h1>
            <p style="margin: 0; font-size: 13px; opacity: 0.9;">Someone needs your help!</p>
        </div>
        
        <div style="padding: 24px;">
            <div style="background: #f8fafc; border-radius: 10px; padding: 16px; margin-bottom: 20px;">
                <div style="font-weight: 800; color: #1a1d2e; font-size: 15px; margin-bottom: 4px;">{customer_name}</div>
                <div style="font-size: 12px; color: #64748b;">{customer_type}</div>
                {f'<div style="font-size: 13px; color: #475569; padding-top: 8px; border-top: 1px solid #e2e8f0; margin-top: 8px;"><strong>📞 Phone:</strong> {customer_phone}</div>' if customer_phone else ''}
            </div>
            
            <div style="background: white; border: 2px solid #e2e8f0; border-left: 4px solid #667eea; border-radius: 10px; padding: 16px; font-size: 15px; line-height: 1.6; color: #1a1d2e; margin-bottom: 20px;">
                {message_preview}
            </div>
            
            <div style="text-align: center; margin: 24px 0;">
                <a href="{chat_link}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 10px; font-weight: 800; font-size: 15px;">
                    💬 Reply Now →
                </a>
            </div>
            
            <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: #92400e;">
                <strong>⏰ Tip:</strong> Customer ko turant reply karne se sale complete hone ke chances zyada hote hain.
            </div>
        </div>
        
        <div style="background: #f8fafc; padding: 16px 24px; text-align: center; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 12px; color: #94a3b8;">
                {getattr(settings, 'SITE_NAME', 'Your Store')} Live Chat
            </p>
        </div>
        
    </div>
</body>
</html>
        """.strip()
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            to=[admin_email],
        )
        email.attach_alternative(body_html, "text/html")
        email.send(fail_silently=True)
        
        return True
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Chat notification email error: {e}")
        return False