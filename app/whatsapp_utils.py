"""
WhatsApp Sender - Android & Desktop Compatible
All Features: Invoice, Reminder, PDF, Daily Summary, Order Status, Broadcast
"""
from datetime import datetime, date
from decimal import Decimal
from urllib.parse import quote
from django.db.models import Sum, F


class WhatsAppSender:
    """Single message sender"""
    
    @staticmethod
    def format_phone(phone):
        """Phone number ko +92 format mein convert karo"""
        phone = str(phone).replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if phone.startswith('+'):
            return phone
        elif phone.startswith('0'):
            return '+92' + phone[1:]
        elif phone.startswith('92'):
            return '+' + phone
        else:
            return '+92' + phone
    
    # ============================================
    # 1. TEXT INVOICE
    # ============================================
    
    @staticmethod
    def send_invoice(customer_phone, bill_no, total_amount, customer_name=""):
        """Text invoice WhatsApp link"""
        try:
            phone = WhatsAppSender.format_phone(customer_phone)
            
            message = f"🧾 *INVOICE*\n━━━━━━━━━━━━━━━━\n📋 Bill No: *{bill_no}*\n💰 Total: *Rs. {total_amount:,.2f}*\n📅 Date: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n━━━━━━━━━━━━━━━━\n🙏 Thank you for your business!"
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
                'phone': phone,
                'message': 'WhatsApp link generated!'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 2. PAYMENT REMINDER
    # ============================================
    
    @staticmethod
    def send_payment_reminder(customer_phone, customer_name, outstanding_amount):
        """Payment reminder link"""
        try:
            phone = WhatsAppSender.format_phone(customer_phone)
            
            message = f"⚠️ *PAYMENT REMINDER*\n━━━━━━━━━━━━━━━━\n👤 *{customer_name}*\n💸 Outstanding: *Rs. {outstanding_amount:,.2f}*\n📅 {datetime.now().strftime('%d-%m-%Y')}\n━━━━━━━━━━━━━━━━\n🙏 Please clear your dues.\n📞 Contact us for queries!"
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
                'phone': phone,
                'message': 'Reminder link generated!'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 3. ORDER CONFIRMATION
    # ============================================
    
    @staticmethod
    def send_order_confirmation(customer_phone, customer_name, order_no, items_count, total):
        """Order confirmation link"""
        try:
            phone = WhatsAppSender.format_phone(customer_phone)
            
            message = f"✅ *ORDER CONFIRMED*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order No: *{order_no}*\n📦 Items: *{items_count}*\n💰 Total: *Rs. {total:,.2f}*\n📅 {datetime.now().strftime('%d-%m-%Y %H:%M')}\n━━━━━━━━━━━━━━━━\n🔄 Order is being processed!"
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
                'phone': phone,
                'message': 'Confirmation link generated!'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 4. CUSTOM MESSAGE
    # ============================================
    
    @staticmethod
    def send_direct_message(phone, message):
        """Custom message link"""
        try:
            phone = WhatsAppSender.format_phone(phone)
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
                'phone': phone,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 5. PDF INVOICE
    # ============================================
    
    @staticmethod
    def send_pdf_invoice_link(sale_obj):
        """PDF invoice ka WhatsApp link"""
        try:
            phone = WhatsAppSender.format_phone(sale_obj.customer.contact_number)
            
            message = f"🧾 *INVOICE*\n━━━━━━━━━━━━━━━━\n📋 Bill: *{sale_obj.bill_no}*\n💰 Total: *Rs. {sale_obj.total_amount():,.2f}*\n📅 {sale_obj.sale_date.strftime('%d-%m-%Y')}\n━━━━━━━━━━━━━━━━\n\nThank you for your business! 🙏"
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            # PDF bhi save karo
            import tempfile, os
            from .admin import generate_invoice_pdf
            
            pdf_buffer = generate_invoice_pdf(sale_obj)
            temp_dir = tempfile.gettempdir()
            filename = f"Invoice_{sale_obj.bill_no}.pdf"
            filepath = os.path.join(temp_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            
            return {
                'success': True,
                'url': wa_url,
                'filepath': filepath,
                'filename': filename,
                'message': 'PDF invoice generated!'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 6. DAILY SUMMARY
    # ============================================
    
    @staticmethod
    def send_daily_summary(owner_phone):
        """Roz ka summary WhatsApp pe"""
        try:
            from .models import Sale, Purchase, Inventory, Customer
            
            today = date.today()
            
            # Aaj ki sales
            sales = Sale.objects.filter(sale_date__date=today)
            total_sales = sum(s.total_amount() for s in sales)
            total_profit = sum(s.total_profit() for s in sales)
            sale_count = sales.count()
            
            # Aaj ki purchases
            purchases = Purchase.objects.filter(pur_date__date=today)
            total_purchase = sum(p.total_amount() for p in purchases)
            purchase_count = purchases.count()
            
            # Low stock
            low_stock = Inventory.objects.filter(
                stock__lt=F('product__low_stock_threshold')
            ).count()
            
            # Outstanding
            total_outstanding = sum(
                c.adjusted_outstanding_balance() 
                for c in Customer.objects.all()
            )
            
            # Cash in/out
            cash_in = sales.aggregate(t=Sum('paid'))['t'] or Decimal('0')
            cash_out = purchases.aggregate(t=Sum('paid'))['t'] or Decimal('0')
            
            phone = WhatsAppSender.format_phone(owner_phone)
            
            message = f"""📊 *DAILY SUMMARY*
━━━━━━━━━━━━━━━━
📅 {today.strftime('%d-%m-%Y')} ({today.strftime('%A')})

💰 *SALES*
├─ Count: {sale_count}
├─ Amount: Rs. {total_sales:,.0f}
└─ Profit: Rs. {total_profit:,.0f}

📦 *PURCHASES*
├─ Count: {purchase_count}
└─ Amount: Rs. {total_purchase:,.0f}

💵 *CASH FLOW*
├─ Cash In: Rs. {cash_in:,.0f}
└─ Cash Out: Rs. {cash_out:,.0f}

⚠️ *ALERTS*
├─ Low Stock: {low_stock} items
└─ Outstanding: Rs. {total_outstanding:,.0f}
━━━━━━━━━━━━━━━━
🙏 Great work today!"""
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
                'message': 'Daily summary ready!'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 7. ORDER STATUS UPDATE
    # ============================================
    
    @staticmethod
    def send_order_status(customer_phone, customer_name, order_no, status):
        """Order status update bhejo"""
        try:
            phone = WhatsAppSender.format_phone(customer_phone)
            
            status_messages = {
                'confirmed': f"✅ *ORDER CONFIRMED*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nAapka order confirm ho gaya hai!\nJald process karte hain.",
                
                'processing': f"🔄 *ORDER PROCESSING*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nAapka order process ho raha hai...",
                
                'ready': f"📦 *ORDER READY*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nAapka order ready hai!\nJald delivery ke liye bhej rahe hain.",
                
                'partially_delivered': f"🚚 *PARTIALLY DELIVERED*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nKuch items deliver ho gaye hain.\nBaqi jald bhej rahe hain.",
                
                'delivered': f"🚚 *ORDER DELIVERED*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nAapka order deliver ho gaya!\nFeedback zaroor dena! 🙏",
                
                'invoiced': f"🧾 *INVOICE GENERATED*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nAapka invoice generate ho gaya hai.\nPayment jald clear karein.",
                
                'cancelled': f"❌ *ORDER CANCELLED*\n━━━━━━━━━━━━━━━━\n👤 {customer_name}\n📋 Order: *{order_no}*\n━━━━━━━━━━━━━━━━\nOrder cancel kar diya gaya.\nKisi pareshani ke liye maazrat.",
            }
            
            message = status_messages.get(status, f"📋 Order *{order_no}*\nStatus: {status}")
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
                'status': status,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 8. BIRTHDAY WISH
    # ============================================
    
    @staticmethod
    def send_birthday_wish(customer_phone, customer_name):
        """Birthday wish bhejo"""
        try:
            phone = WhatsAppSender.format_phone(customer_phone)
            message = f"🎂 *Happy Birthday {customer_name}!*\n\nAllah aapko lambi umar de aur dher sari khushiyan de! Ameen! 🤲\n\n🧁 - Team"
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # 9. GREETINGS
    # ============================================
    
    @staticmethod
    def send_eid_greeting(customer_phone, customer_name):
        """Eid greeting"""
        try:
            phone = WhatsAppSender.format_phone(customer_phone)
            message = f"🌙 *EID MUBARAK {customer_name}!*\n\nAllah aapki khushiyan aur barkatain naseeb farmaye! Ameen! 🤲"
            
            wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
            
            return {
                'success': True,
                'url': wa_url,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class WhatsAppBulkSender:
    """Multiple customers ke liye sender"""
    
    @staticmethod
    def get_outstanding_customers():
        """Outstanding customers ki list"""
        from .models import Customer
        
        customers_list = []
        for customer in Customer.objects.all():
            balance = customer.adjusted_outstanding_balance()
            if balance > 0 and customer.contact_number:
                customers_list.append({
                    'name': customer.name,
                    'phone': customer.contact_number,
                    'balance': balance
                })
        return customers_list
    
    @staticmethod
    def generate_reminder_links():
        """Sab outstanding customers ke liye reminder links"""
        customers = WhatsAppBulkSender.get_outstanding_customers()
        
        links = []
        for cust in customers:
            result = WhatsAppSender.send_payment_reminder(
                cust['phone'], cust['name'], cust['balance']
            )
            if result['success']:
                links.append({
                    'name': cust['name'],
                    'phone': cust['phone'],
                    'balance': cust['balance'],
                    'url': result['url']
                })
        return links
    
    @staticmethod
    def send_promotional_broadcast(message, customer_ids=None):
        """Sab ya selected customers ko broadcast"""
        from .models import Customer
        
        if customer_ids:
            customers = Customer.objects.filter(id__in=customer_ids)
        else:
            customers = Customer.objects.exclude(
                contact_number__isnull=True
            ).exclude(contact_number='')
        
        links = []
        for customer in customers:
            result = WhatsAppSender.send_direct_message(
                customer.contact_number,
                message
            )
            if result['success']:
                links.append({
                    'name': customer.name,
                    'phone': customer.contact_number,
                    'url': result['url']
                })
        
        return links
    
    @staticmethod
    def send_eid_to_all():
        """Sab customers ko Eid greeting"""
        from .models import Customer
        
        customers = Customer.objects.exclude(
            contact_number__isnull=True
        ).exclude(contact_number='')
        
        links = []
        for customer in customers:
            result = WhatsAppSender.send_eid_greeting(
                customer.contact_number,
                customer.name
            )
            if result['success']:
                links.append({
                    'name': customer.name,
                    'phone': customer.contact_number,
                    'url': result['url']
                })
        
        return links
    
    @staticmethod
    def get_all_customers_with_phones():
        """Phone number walay sab customers"""
        from .models import Customer
        
        return Customer.objects.exclude(
            contact_number__isnull=True
        ).exclude(contact_number='')

# ============================================
# 10. EMI REMINDER FOR INSTALLMENT PLANS
# ============================================

@staticmethod
def send_emi_reminder(customer_phone, customer_name, bill_no, emi_number, 
                       due_date, amount_due, remaining_balance, plan_name, late_fee_per_day):
    """EMI payment reminder for installment plans"""
    try:
        phone = WhatsAppSender.format_phone(customer_phone)
        
        today = date.today()
        days_left = (due_date - today).days
        
        if days_left < 0:
            emoji = "🔴"
            urgency = "OVERDUE"
            days_text = f"{abs(days_left)} days overdue"
        elif days_left == 0:
            emoji = "🔔"
            urgency = "DUE TODAY"
            days_text = "today"
        else:
            emoji = "📅"
            urgency = f"DUE IN {days_left} DAYS"
            days_text = f"in {days_left} days"
        
        message = f"""{emoji} *EMI PAYMENT REMINDER* {emoji}
─────────────────────
👤 *Customer:* {customer_name}
📋 *Bill No:* {bill_no}
📦 *Plan:* {plan_name}

💰 *EMI #{emi_number}*
├─ Amount: *Rs. {amount_due:,.2f}*
├─ Due Date: {due_date.strftime('%d-%b-%Y')}
└─ Status: *{urgency}* ({days_text})

📊 *Summary*
├─ Remaining: Rs. {remaining_balance:,.2f}
└─ Late Fee: Rs. {late_fee_per_day}/day

─────────────────────
🙏 Please clear your payment on time!
Click below to send reminder 👇"""

        wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
        
        return {
            'success': True,
            'url': wa_url,
            'phone': phone,
            'message': 'EMI reminder link generated!'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@staticmethod
def send_emi_payment_confirmation(customer_phone, customer_name, bill_no, 
                                   emi_number, amount_paid, due_date, 
                                   remaining_balance, next_due_date):
    """Payment confirmation after EMI payment"""
    try:
        phone = WhatsAppSender.format_phone(customer_phone)
        
        message = f"""✅ *PAYMENT CONFIRMATION* ✅
─────────────────────
👤 *Customer:* {customer_name}
📋 *Bill No:* {bill_no}

💰 *EMI #{emi_number}*
├─ Amount Paid: *Rs. {amount_paid:,.2f}*
├─ Payment Date: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}
└─ Due Date: {due_date.strftime('%d-%b-%Y')}

📊 *Updated Status*
├─ Remaining Balance: Rs. {remaining_balance:,.2f}
└─ Next Due: {next_due_date.strftime('%d-%b-%Y') if next_due_date else 'Completed 🎉'}

─────────────────────
🙏 Thank you for your payment!
Click below to send confirmation 👇"""

        wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
        
        return {
            'success': True,
            'url': wa_url,
            'phone': phone,
            'message': 'Payment confirmation link generated!'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@staticmethod
def send_installment_summary(customer_phone, customer_name, bill_no, plan_name,
                              total_payable, total_paid, remaining, 
                              total_emis, paid_emis, pending_emis, 
                              overdue_count, start_date, end_date, next_due_date):
    """Complete installment plan summary"""
    try:
        phone = WhatsAppSender.format_phone(customer_phone)
        
        progress = (total_paid / total_payable * 100) if total_payable > 0 else 0
        
        # Progress bar (10 blocks)
        filled = int(progress / 10)
        empty = 10 - filled
        progress_bar = "█" * filled + "░" * empty
        
        overdue_icon = "⚠️" if overdue_count > 0 else "✅"
        
        message = f"""📊 *INSTALLMENT PLAN SUMMARY* 📊
─────────────────────
👤 *Customer:* {customer_name}
📋 *Bill No:* {bill_no}
📦 *Plan:* {plan_name}

💰 *FINANCIAL SUMMARY*
├─ Total Payable: Rs. {total_payable:,.2f}
├─ Total Paid: Rs. {total_paid:,.2f}
├─ Remaining: Rs. {remaining:,.2f}
└─ Progress: {progress:.0f}% [{progress_bar}]

📅 *PAYMENT STATUS*
├─ Total EMIs: {total_emis}
├─ Paid: {paid_emis} ✅
├─ Pending: {pending_emis} ⏳
└─ Overdue: {overdue_count} {overdue_icon}

📆 *DATES*
├─ Start: {start_date.strftime('%d-%b-%Y')}
├─ Expected End: {end_date.strftime('%d-%b-%Y') if end_date else 'In progress'}
└─ Next Due: {next_due_date.strftime('%d-%b-%Y') if next_due_date else 'Completed 🎉'}

─────────────────────
Click below to send summary 👇"""

        wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
        
        return {
            'success': True,
            'url': wa_url,
            'phone': phone,
            'message': 'Installment summary link generated!'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


@staticmethod
def send_overdue_alert(customer_phone, customer_name, bill_no, 
                        overdue_emis_list, total_overdue, days_overdue, 
                        late_fee_per_day, remaining_balance):
    """Urgent overdue alert for multiple EMIs"""
    try:
        phone = WhatsAppSender.format_phone(customer_phone)
        
        # Build EMI list
        emi_text = ""
        for emi in overdue_emis_list[:5]:  # Max 5 EMIs in message
            emi_text += f"\n   └─ EMI #{emi['number']}: Rs. {emi['amount']:,.2f} (Due: {emi['due_date']})"
        
        if len(overdue_emis_list) > 5:
            emi_text += f"\n   └─ ... and {len(overdue_emis_list) - 5} more"
        
        message = f"""🚨 *URGENT: OVERDUE PAYMENT ALERT* 🚨
─────────────────────
👤 *Customer:* {customer_name}
📋 *Bill No:* {bill_no}

⚠️ *You have {len(overdue_emis_list)} overdue EMI(s):*
{emi_text}

💰 *Total Overdue Amount:* Rs. {total_overdue:,.2f}
📅 *Days Overdue:* {days_overdue} days

❗ *Late Fee:* Rs. {late_fee_per_day}/day will be added

📊 *Remaining Balance:* Rs. {remaining_balance:,.2f}

─────────────────────
⚠️ Please clear your payment IMMEDIATELY to avoid additional charges!

Click below to send alert 👇"""

        wa_url = f"https://api.whatsapp.com/send?phone={phone}&text={quote(message)}"
        
        return {
            'success': True,
            'url': wa_url,
            'phone': phone,
            'message': 'Overdue alert link generated!'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================
# BULK SENDER FOR INSTALLMENTS
# ============================================

class InstallmentWhatsAppSender:
    """Specialized bulk sender for installment plans"""
    
    @staticmethod
    def get_pending_emis():
        """Get all pending EMIs with customer details"""
        from .models import EmiPayment, SaleInstallment
        
        today = date.today()
        
        # EMIs due today
        due_today = EmiPayment.objects.filter(
            due_date=today,
            status='pending'
        ).select_related('installment__sale__customer', 'installment__plan')
        
        # EMIs due in next 7 days
        upcoming = EmiPayment.objects.filter(
            due_date__gt=today,
            due_date__lte=today + timedelta(days=7),
            status='pending'
        ).select_related('installment__sale__customer', 'installment__plan')
        
        # Overdue EMIs
        overdue = EmiPayment.objects.filter(
            due_date__lt=today,
            status='pending'
        ).select_related('installment__sale__customer', 'installment__plan')
        
        return {
            'due_today': due_today,
            'upcoming': upcoming,
            'overdue': overdue
        }
    
    @staticmethod
    def generate_all_reminder_links():
        """Generate WhatsApp links for all pending EMIs"""
        emis = InstallmentWhatsAppSender.get_pending_emis()
        all_links = []
        
        # Due today
        for emi in emis['due_today']:
            inst = emi.installment
            cust = inst.sale.customer
            result = WhatsAppSender.send_emi_reminder(
                cust.contact_number,
                cust.name,
                inst.sale.bill_no,
                emi.installment_number,
                emi.due_date,
                emi.amount_due - emi.amount_paid,
                inst.remaining_amount(),
                inst.plan.name if inst.plan else 'Installment',
                inst.plan.late_fee_per_day if inst.plan else 0
            )
            if result['success']:
                all_links.append({
                    'type': 'due_today',
                    'customer': cust.name,
                    'bill_no': inst.sale.bill_no,
                    'emi_no': emi.installment_number,
                    'amount': float(emi.amount_due - emi.amount_paid),
                    'url': result['url']
                })
        
        # Upcoming
        for emi in emis['upcoming']:
            inst = emi.installment
            cust = inst.sale.customer
            result = WhatsAppSender.send_emi_reminder(
                cust.contact_number,
                cust.name,
                inst.sale.bill_no,
                emi.installment_number,
                emi.due_date,
                emi.amount_due - emi.amount_paid,
                inst.remaining_amount(),
                inst.plan.name if inst.plan else 'Installment',
                inst.plan.late_fee_per_day if inst.plan else 0
            )
            if result['success']:
                all_links.append({
                    'type': 'upcoming',
                    'customer': cust.name,
                    'bill_no': inst.sale.bill_no,
                    'emi_no': emi.installment_number,
                    'amount': float(emi.amount_due - emi.amount_paid),
                    'due_date': emi.due_date.strftime('%d-%b-%Y'),
                    'url': result['url']
                })
        
        # Overdue
        for emi in emis['overdue']:
            inst = emi.installment
            cust = inst.sale.customer
            result = WhatsAppSender.send_emi_reminder(
                cust.contact_number,
                cust.name,
                inst.sale.bill_no,
                emi.installment_number,
                emi.due_date,
                emi.amount_due - emi.amount_paid,
                inst.remaining_amount(),
                inst.plan.name if inst.plan else 'Installment',
                inst.plan.late_fee_per_day if inst.plan else 0
            )
            if result['success']:
                all_links.append({
                    'type': 'overdue',
                    'customer': cust.name,
                    'bill_no': inst.sale.bill_no,
                    'emi_no': emi.installment_number,
                    'amount': float(emi.amount_due - emi.amount_paid),
                    'due_date': emi.due_date.strftime('%d-%b-%Y'),
                    'days_overdue': (date.today() - emi.due_date).days,
                    'url': result['url']
                })
        
        return all_links
    
    @staticmethod
    def get_overdue_installments():
        """Get all overdue installments with complete details"""
        from .models import SaleInstallment
        
        today = date.today()
        overdue_installments = SaleInstallment.objects.filter(
            status__in=['pending', 'partial'],
            next_due_date__lt=today
        ).select_related('sale__customer', 'plan')
        
        reports = []
        for inst in overdue_installments:
            cust = inst.sale.customer
            overdue_emis = inst.emi_payments.filter(
                status='pending', 
                due_date__lt=today
            )
            
            total_overdue = sum(emi.amount_due - emi.amount_paid for emi in overdue_emis)
            days_overdue = (today - inst.next_due_date).days if inst.next_due_date else 0
            
            emi_list = [{
                'number': emi.installment_number,
                'amount': float(emi.amount_due - emi.amount_paid),
                'due_date': emi.due_date.strftime('%d-%b-%Y')
            } for emi in overdue_emis]
            
            result = WhatsAppSender.send_overdue_alert(
                cust.contact_number,
                cust.name,
                inst.sale.bill_no,
                emi_list,
                float(total_overdue),
                days_overdue,
                float(inst.plan.late_fee_per_day) if inst.plan else 0,
                float(inst.remaining_amount())
            )
            
            if result['success']:
                reports.append({
                    'customer': cust.name,
                    'bill_no': inst.sale.bill_no,
                    'phone': cust.contact_number,
                    'days_overdue': days_overdue,
                    'total_overdue': float(total_overdue),
                    'emi_count': overdue_emis.count(),
                    'url': result['url']
                })
        
        return reports