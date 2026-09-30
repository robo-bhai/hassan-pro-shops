"""
WhatsApp Sender - Android & Desktop Compatible
All Features: Invoice, Reminder, PDF, Daily Summary, Order Status, Broadcast
+ Order Tracking System (Rider, Pickup, ETA, Delivery)
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from urllib.parse import quote
from django.db.models import Sum, F


class WhatsAppSender:
    """Single message sender"""
    
    @staticmethod
    def format_phone(phone):
        """Phone number ko +92 format mein convert karo"""
        if not phone:
            return None
        phone = str(phone).replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if phone.startswith('+'):
            return phone
        elif phone.startswith('0'):
            return '+92' + phone[1:]
        elif phone.startswith('92'):
            return '+' + phone
        else:
            return '+92' + phone
    
    @staticmethod
    def _generate_link(phone, message):
        """WhatsApp link generate karo"""
        formatted = WhatsAppSender.format_phone(phone)
        if not formatted:
            return None
        # Remove + for wa.me
        clean_phone = formatted.replace('+', '').replace(' ', '')
        encoded_msg = quote(message)
        return f"https://wa.me/{clean_phone}?text={encoded_msg}"
    
    @staticmethod
    def get_company_name():
        """Get company name"""
        try:
            from .models import CompanyInfo
            company = CompanyInfo.objects.first()
            return company.name if company else "Our Shop"
        except:
            return "Our Shop"
    
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
            
            sales = Sale.objects.filter(sale_date__date=today)
            total_sales = sum(s.total_amount() for s in sales)
            total_profit = sum(s.total_profit() for s in sales)
            sale_count = sales.count()
            
            purchases = Purchase.objects.filter(pur_date__date=today)
            total_purchase = sum(p.total_amount() for p in purchases)
            purchase_count = purchases.count()
            
            low_stock = Inventory.objects.filter(
                stock__lt=F('product__low_stock_threshold')
            ).count()
            
            total_outstanding = sum(
                c.adjusted_outstanding_balance() 
                for c in Customer.objects.all()
            )
            
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
    # ✅ 7.1 ORDER TRACKING — RIDER ASSIGNED
    # ============================================
    
    @staticmethod
    def send_rider_assigned(customer_phone, customer_name, order_no,
                            rider_name, rider_contact, rider_vehicle='', expected_time=''):
        """Rider assigned message"""
        try:
            company = WhatsAppSender.get_company_name()
            msg = f"""🏍️ *RIDER ASSIGNED*

{customer_name}, aapka order *#{order_no}* rider ko de diya gaya hai.

👤 *Rider Name:* {rider_name}
📞 *Contact:* {rider_contact}"""
            
            if rider_vehicle:
                msg += f"\n🏍️ *Vehicle:* {rider_vehicle}"
            if expected_time:
                msg += f"\n⏰ *Expected:* {expected_time}"
            
            msg += f"""

Aap rider se direct rabta kar sakte hain.

Shukriya! ❤️
_{company}_"""
            
            return WhatsAppSender._generate_link(customer_phone, msg)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # ✅ 7.2 ORDER TRACKING — READY FOR PICKUP
    # ============================================
    
    @staticmethod
    def send_ready_for_pickup(customer_phone, customer_name, order_no,
                              pickup_address, timing='10 AM - 8 PM'):
        """Ready for pickup message"""
        try:
            company = WhatsAppSender.get_company_name()
            msg = f"""🚶 *ORDER READY FOR PICKUP*

{customer_name}, aapka order *#{order_no}* pickup ke liye tayyar hai!

📍 *Pickup Address:*
{pickup_address}

⏰ *Timing:* {timing}

Apni ID saath le kar aayein.

Shukriya! ❤️
_{company}_"""
            
            return WhatsAppSender._generate_link(customer_phone, msg)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # ✅ 7.3 ORDER TRACKING — OUT FOR DELIVERY
    # ============================================
    
    @staticmethod
    def send_out_for_delivery(customer_phone, customer_name, order_no,
                              rider_name='', rider_contact='', expected_time=''):
        """Out for delivery message"""
        try:
            company = WhatsAppSender.get_company_name()
            msg = f"""🛵 *ORDER RASTE MEIN HAI*

{customer_name}, aapka order *#{order_no}* aapki taraf rawana ho gaya hai!"""
            
            if rider_name:
                msg += f"\n\n👤 *Rider:* {rider_name}"
            if rider_contact:
                msg += f"\n📞 *Contact:* {rider_contact}"
            if expected_time:
                msg += f"\n⏰ *Expected:* {expected_time}"
            
            msg += f"""

Apna phone paas rakhein. Rider call karega.

_{company}_"""
            
            return WhatsAppSender._generate_link(customer_phone, msg)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # ✅ 7.4 ORDER TRACKING — DELIVERED
    # ============================================
    
    @staticmethod
    def send_delivered(customer_phone, customer_name, order_no, amount=0):
        """Order delivered message"""
        try:
            company = WhatsAppSender.get_company_name()
            msg = f"""🎉 *ORDER DELIVER HO GAYA*

{customer_name}, aapka order *#{order_no}* successfully deliver ho gaya!"""
            
            if amount > 0:
                msg += f"\n\n💰 *Amount Received:* Rs. {amount:,.0f}"
            
            msg += f"""

Shukriya shopping karne ka! ❤️
Hamari service kaise lagi? Apna feedback zaroor dein.

_{company}_"""
            
            return WhatsAppSender._generate_link(customer_phone, msg)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # ✅ 7.5 ORDER TRACKING — CANCELLED
    # ============================================
    
    @staticmethod
    def send_order_cancelled(customer_phone, customer_name, order_no, reason=''):
        """Order cancelled message"""
        try:
            company = WhatsAppSender.get_company_name()
            msg = f"""❌ *ORDER CANCELLED*

{customer_name}, aapka order *#{order_no}* cancel kar diya gaya hai."""
            
            if reason:
                msg += f"\n\n*Reason:* {reason}"
            
            msg += f"""

Kisi bhi sawal ke liye hum se rabta karein.

_{company}_"""
            
            return WhatsAppSender._generate_link(customer_phone, msg)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # ✅ 7.6 ORDER TRACKING — PICKED UP
    # ============================================
    
    @staticmethod
    def send_picked_up(customer_phone, customer_name, order_no):
        """Customer picked up order"""
        try:
            company = WhatsAppSender.get_company_name()
            msg = f"""✋ *ORDER PICKED UP*

{customer_name}, aapne order *#{order_no}* pickup kar liya hai.

Shukriya shopping karne ka! ❤️

_{company}_"""
            
            return WhatsAppSender._generate_link(customer_phone, msg)
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


# ============================================
# BULK SENDER
# ============================================

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
# INSTALLMENT WhatsApp SENDER
# ============================================

class InstallmentWhatsAppSender:
    """Specialized bulk sender for installment plans"""
    
    @staticmethod
    def get_pending_emis():
        """Get all pending EMIs with customer details"""
        from .models import EmiPayment
        
        today = date.today()
        
        due_today = EmiPayment.objects.filter(
            due_date=today,
            status='pending'
        ).select_related('installment__sale__customer', 'installment__plan')
        
        upcoming = EmiPayment.objects.filter(
            due_date__gt=today,
            due_date__lte=today + timedelta(days=7),
            status='pending'
        ).select_related('installment__sale__customer', 'installment__plan')
        
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
        
        for emi_type, emi_list in emis.items():
            for emi in emi_list:
                inst = emi.installment
                cust = inst.sale.customer
                result = WhatsAppSender.send_direct_message(
                    cust.contact_number,
                    f"📅 EMI #{emi.installment_number} Reminder\nAmount: Rs. {emi.amount_due - emi.amount_paid:,.2f}\nDue: {emi.due_date.strftime('%d-%b-%Y')}"
                )
                if result.get('success'):
                    all_links.append({
                        'type': emi_type,
                        'customer': cust.name,
                        'bill_no': inst.sale.bill_no,
                        'emi_no': emi.installment_number,
                        'amount': float(emi.amount_due - emi.amount_paid),
                        'url': result['url']
                    })
        
        return all_links
    
    @staticmethod
    def get_overdue_installments():
        """Get all overdue installments"""
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
            
            reports.append({
                'customer': cust.name,
                'bill_no': inst.sale.bill_no,
                'phone': cust.contact_number,
                'days_overdue': days_overdue,
                'total_overdue': float(total_overdue),
                'emi_count': overdue_emis.count(),
            })
        
        return reports