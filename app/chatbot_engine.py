"""
AI Chatbot Engine - Complete Business Assistant
Handles all business queries in English, Urdu, and Roman Urdu

✅ Level 4 Auto-Reply System
✅ Customer-friendly responses
✅ Order tracking
✅ Product search
✅ Payment/Delivery/Return info
"""

import re
import json
from decimal import Decimal
from datetime import datetime, timedelta, date
from django.db.models import Sum, Count, Avg, Q, F
from django.utils.timezone import now, localdate
import logging

logger = logging.getLogger(__name__)


class BusinessChatbot:
    """
    Complete Business Chatbot
    Supports English, Urdu, Roman Urdu
    
    ✅ Handles both ADMIN and CUSTOMER queries
    """
    
    def __init__(self, user=None):
        self.user = user
        
        # ========================================== #
        # IMPORT MODELS                              #
        # ========================================== #
        
        try:
            from .models import (
                Sale, Purchase, Customer, Vendor, Product, 
                Inventory, Expense, Employee, SaleInstallment,
                OperationsKPI, OperationTask, BusinessOperationPlan,
                CashBalance, Shareholder, Dividend, AIOperationsInsight,
                SaleOrder, PurchaseOrder, DeliveryChallan, GoodsReceivedNote,
                PaymentMethod, VendorPayment, CustomerPayment,
                ExpenseCategory, Department, Project, Budget,
                ServiceRequest, Service, Loan, LoanGiven,
                Share, SharePrice, ShareTransfer, ShareholderMeeting,
                CompanyInfo, SaleItem
            )
            
            # Sales & Purchases
            self.Sale = Sale
            self.Purchase = Purchase
            self.SaleItem = SaleItem
            self.SaleOrder = SaleOrder
            self.PurchaseOrder = PurchaseOrder
            self.DeliveryChallan = DeliveryChallan
            self.GoodsReceivedNote = GoodsReceivedNote
            
            # People
            self.Customer = Customer
            self.Vendor = Vendor
            self.Employee = Employee
            
            # Products & Inventory
            self.Product = Product
            self.Inventory = Inventory
            
            # Finance
            self.Expense = Expense
            self.ExpenseCategory = ExpenseCategory
            self.CashBalance = CashBalance
            self.Budget = Budget
            
            # Payments
            self.VendorPayment = VendorPayment
            self.CustomerPayment = CustomerPayment
            
            # Installments
            self.SaleInstallment = SaleInstallment
            
            # Operations
            self.OperationsKPI = OperationsKPI
            self.OperationTask = OperationTask
            self.BusinessOperationPlan = BusinessOperationPlan
            self.AIOperationsInsight = AIOperationsInsight
            
            # Shareholders
            self.Shareholder = Shareholder
            self.Share = Share
            self.SharePrice = SharePrice
            self.ShareTransfer = ShareTransfer
            self.Dividend = Dividend
            self.ShareholderMeeting = ShareholderMeeting
            
            # Loans
            self.Loan = Loan
            self.LoanGiven = LoanGiven
            
            # Services
            self.Service = Service
            self.ServiceRequest = ServiceRequest
            
            # Company
            self.CompanyInfo = CompanyInfo
            
        except Exception as e:
            logger.error(f"Chatbot model import error: {e}")
            raise
    
    # ========================================== #
    # MAIN METHOD                                #
    # ========================================== #
    
    def get_response(self, question):
        """Main response method — safe with try/except"""
        
        if not question:
            return "Please ask something 😊"
        
        try:
            return self._process_question(question)
        except Exception as e:
            logger.error(f"Chatbot processing error: {e}")
            return (
                "🤔 **Sorry, there was a technical issue.**\n\n"
                "Please try again or contact an admin.\n\n"
                "📞 Talk to Support."
            )
    
    def _process_question(self, question):
        """Process question with keyword matching"""
        
        q = question.lower().strip()
        q_clean = re.sub(r'[^\w\s]', '', q)
        
        # ========================================== #
        # 1. GREETINGS & INTRO                       #
        # ========================================== #
        
        if any(w in q_clean for w in ['hello', 'hi', 'hey', 'salam', 'assalam', 'helo', 'aoa']):
            return self.greeting_response()
        
        if any(w in q_clean for w in ['thank', 'shukriya', 'shukria', 'thanks', 'thanx', 'jazak']):
            return "You're welcome! 😊 Anything else you want to ask?"
        
        if any(w in q_clean for w in ['bye', 'khuda hafiz', 'goodbye', 'allah hafiz']):
            return "Allah Hafiz! 👋 See you again."
        
        if any(w in q_clean for w in ['help', 'madad', 'kya kar sakte', 'kya kar skte']):
            return self.help_response()
        
        if any(w in q_clean for w in ['kaun ho', 'who are you', 'tum kon', 'aap kon']):
            return self.who_are_you_response()
        
        # ========================================== #
        # 2. ✅ NEW: ORDER TRACKING                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['order status', 'track order', 'order kahan', 'order ka', 'order no']):
            return self.get_order_status_response(question)
        
        # Order number pattern (e.g., "order 1234", "#1234")
        order_match = re.search(r'(?:order|ord|#)\s*[-#]?\s*(\d+)', question.lower())
        if order_match and not any(w in q_clean for w in ['sale', 'purchase', 'today', 'aaj']):
            return self.get_order_status_response(question, order_match.group(1))
        
        # ========================================== #
        # 3. ✅ NEW: PAYMENT METHODS                 #
        # ========================================== #
        
        if any(w in q_clean for w in ['payment method', 'payment kaise', 'pay kaise', 'cod', 'jazzcash', 'easypaisa', 'bank transfer']):
            return self.get_payment_methods_response()
        
        # ========================================== #
        # 4. ✅ NEW: DELIVERY INFO                   #
        # ========================================== #
        
        if any(w in q_clean for w in ['delivery', 'shipping', 'courier', 'kitne din', 'kab aayega', 'kitna time']):
            return self.get_delivery_response()
        
        # ========================================== #
        # 5. ✅ NEW: RETURN / REFUND                 #
        # ========================================== #
        
        if any(w in q_clean for w in ['return', 'refund', 'wapas', 'exchange', 'wapisi']):
            return self.get_return_response()
        
        # ========================================== #
        # 6. ✅ NEW: CONTACT INFO                    #
        # ========================================== #
        
        if any(w in q_clean for w in ['contact', 'number', 'phone', 'email', 'address', 'location', 'helpline']):
            # But not "phone" alone — only in context
            if any(w in q_clean for w in ['contact', 'helpline', 'address', 'location', 'email']):
                return self.get_contact_response()
        
        # ========================================== #
        # 7. ✅ NEW: PRODUCT SEARCH                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['price', 'rate', 'kitna', 'stock hai', 'available', 'milega']):
            return self.get_product_search_response(question)
        
        # ========================================== #
        # 8. SALES                                   #
        # ========================================== #
        
        if any(w in q_clean for w in ['sale', 'sales', 'bikri', 'becha', 'sold', 'sells']):
            return self.get_sales_answer(q_clean)
        
        # ========================================== #
        # 9. PURCHASE                                #
        # ========================================== #
        
        if any(w in q_clean for w in ['purchase', 'kharida', 'khareeda', 'buying', 'bought']):
            return self.get_purchase_answer(q_clean)
        
        # ========================================== #
        # 10. PROFIT / LOSS                          #
        # ========================================== #
        
        if any(w in q_clean for w in ['profit', 'munafa', 'faida', 'loss', 'nuksan', 'earning']):
            return self.get_profit_answer(q_clean)
        
        # ========================================== #
        # 11. STOCK / INVENTORY                      #
        # ========================================== #
        
        if any(w in q_clean for w in ['stock', 'inventory', 'maal', 'samaan', 'saman']):
            return self.get_stock_answer(q_clean)
        
        # ========================================== #
        # 12. CUSTOMERS                              #
        # ========================================== #
        
        if any(w in q_clean for w in ['customer', 'client', 'grahak', 'party']):
            return self.get_customer_answer(q_clean)
        
        # ========================================== #
        # 13. VENDORS                                #
        # ========================================== #
        
        if any(w in q_clean for w in ['vendor', 'supplier', 'dealer']):
            return self.get_vendor_answer(q_clean)
        
        # ========================================== #
        # 14. PAYMENTS / OUTSTANDING                 #
        # ========================================== #
        
        if any(w in q_clean for w in ['payment', 'outstanding', 'baqaya', 'udhar', 'due', 'baqi']):
            return self.get_payment_answer(q_clean)
        
        # ========================================== #
        # 15. CASH                                   #
        # ========================================== #
        
        if any(w in q_clean for w in ['cash', 'nakad', 'naqad', 'balance', 'paisa', 'paise']):
            return self.get_cash_answer(q_clean)
        
        # ========================================== #
        # 16. EXPENSE                                #
        # ========================================== #
        
        if any(w in q_clean for w in ['expense', 'kharcha', 'kharch', 'kharchay']):
            return self.get_expense_answer(q_clean)
        
        # ========================================== #
        # 17. EMPLOYEES                              #
        # ========================================== #
        
        if any(w in q_clean for w in ['employee', 'staff', 'worker', 'naukar', 'team']):
            return self.get_employee_answer(q_clean)
        
        # ========================================== #
        # 18. TASKS / OPERATIONS                     #
        # ========================================== #
        
        if any(w in q_clean for w in ['task', 'kaam', 'work', 'assignment']):
            return self.get_task_answer(q_clean)
        
        # ========================================== #
        # 19. PLANS                                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['plan', 'planning', 'mansooba']):
            return self.get_plan_answer(q_clean)
        
        # ========================================== #
        # 20. KPI / TARGETS                          #
        # ========================================== #
        
        if any(w in q_clean for w in ['kpi', 'target', 'performance', 'lakshya']):
            return self.get_kpi_answer(q_clean)
        
        # ========================================== #
        # 21. AI INSIGHTS                            #
        # ========================================== #
        
        if any(w in q_clean for w in ['insight', 'ai', 'analysis', 'salah', 'suggest']):
            return self.get_ai_answer(q_clean)
        
        # ========================================== #
        # 22. ALERTS                                 #
        # ========================================== #
        
        if any(w in q_clean for w in ['alert', 'warning', 'notification', 'itla']):
            return self.get_alert_answer(q_clean)
        
        # ========================================== #
        # 23. INSTALLMENTS                           #
        # ========================================== #
        
        if any(w in q_clean for w in ['installment', 'emi', 'qist', 'kisht']):
            return self.get_installment_answer(q_clean)
        
        # ========================================== #
        # 24. SHAREHOLDERS                           #
        # ========================================== #
        
        if any(w in q_clean for w in ['shareholder', 'share holder', 'hissa']):
            return self.get_shareholder_answer(q_clean)
        
        # ========================================== #
        # 25. DIVIDENDS                              #
        # ========================================== #
        
        if any(w in q_clean for w in ['dividend', 'munafa hissa']):
            return self.get_dividend_answer(q_clean)
        
        # ========================================== #
        # 26. LOANS                                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['loan', 'qarz', 'udhar liya', 'udhar diya']):
            return self.get_loan_answer(q_clean)
        
        # ========================================== #
        # 27. SERVICES                               #
        # ========================================== #
        
        if any(w in q_clean for w in ['service', 'services', 'khidmat']):
            return self.get_service_answer(q_clean)
        
        # ========================================== #
        # 28. ORDERS                                 #
        # ========================================== #
        
        if any(w in q_clean for w in ['order', 'orders', 'sale order', 'purchase order']):
            return self.get_order_answer(q_clean)
        
        # ========================================== #
        # 29. TOP / BEST                             #
        # ========================================== #
        
        if any(w in q_clean for w in ['top', 'best', 'best selling', 'sabse zyada', 'highest']):
            return self.get_top_answer(q_clean)
        
        # ========================================== #
        # 30. SUMMARY / REPORT                       #
        # ========================================== #
        
        if any(w in q_clean for w in ['summary', 'overview', 'report', 'situation', 'halat']):
            return self.get_summary_answer(q_clean)
        
        # ========================================== #
        # 31. DEFAULT                                #
        # ========================================== #
        
        return self.default_response(question)
    
    # ========================================== #
    # ✅ NEW: ORDER STATUS                       #
    # ========================================== #
    
    def get_order_status_response(self, question, order_no=None):
        """Order status check"""
        
        if order_no:
            return f"""📦 **About Order #{order_no}:**

You can see the live status from the **Track Order** page:

🔗 **Link:** `/shop/track/`

There, enter your:
- ✅ Order number
- ✅ Phone number

Daalein aur status dekh lein! 📊

━━━━━━━━━━━━━━━━━
💡 **Order Statuses:**
• ⏳ Pending
• ✅ Confirmed
• ⚙️ Processing
• 📦 Ready
• 🚚 Shipped
• 🎉 Delivered

If you do not remember the order number, check with your phone number!"""
        
        return """📦 **To Check Order Status:**

**Option 1: Online Track Karein**
🔗 `/shop/track/` pe jaayein
- Order number daalein
- Phone number daalein
- Live status dekhein

**Option 2: Yahan Bataein**
Enter your order number and I will check it.

━━━━━━━━━━━━━━━━━
💡 **Tip:** Once your order is received you will also get a tracking number — you can track with that too."""
    
    # ========================================== #
    # ✅ NEW: PAYMENT METHODS                    #
    # ========================================== #
    
    def get_payment_methods_response(self):
        """Payment methods info"""
        return """💳 **Payment Methods Available:**

💰 **1. Cash on Delivery (COD)**
Sabse popular! Ghar par cash dein
✅ No extra charge

📱 **2. JazzCash**
Pay with a mobile wallet
✅ Instant confirmation

📱 **3. EasyPaisa**
Pay with a mobile wallet
✅ Instant confirmation

🏦 **4. Bank Transfer**
Directly into a bank account
✅ Best for large orders

━━━━━━━━━━━━━━━━━
🔒 **100% Secure Payments**
Aapki information safe hai!

💡 Choose the method at order checkout."""
    
    # ========================================== #
    # ✅ NEW: DELIVERY INFO                      #
    # ========================================== #
    
    def get_delivery_response(self):
        """Delivery information"""
        return """🚚 **Delivery Information:**

⏱️ **Delivery Time:**
• Standard: **2-4 working days**
• Express: **1-2 working days**
• Remote areas: **3-5 working days**

💵 **Delivery Charges:**
• **FREE** — Rs. 1,000+ orders
• **Rs. 100** — Below Rs. 1,000

📍 **Coverage:**
Karachi, Lahore, Islamabad, Rawalpindi, Faisalabad, Multan, Peshawar, Quetta — aur zyada shehr

📦 **Tracking:**
You get the tracking number as soon as the order is confirmed
SMS + Email pe bhi notification aayegi

━━━━━━━━━━━━━━━━━
❓ Koi aur sawal? Poochein!"""
    
    # ========================================== #
    # ✅ NEW: RETURN / REFUND                    #
    # ========================================== #
    
    def get_return_response(self):
        """Return/Refund policy"""
        return """↩️ **Return & Refund Policy:**

✅ **7-Day Return:**
You can return the product within **7 days** of receiving it

📋 **Conditions:**
• Original packaging
• Unused product
• All accessories included
• Bill/receipt zaroori

💰 **Refund Process:**
• **3-5 working days** after the request
• Original payment method pe refund
• Bank transfer for COD orders

⚠️ **Not Refundable:**
• Used/damaged products
• Intimate items
• Customized products
• Sale items

━━━━━━━━━━━━━━━━━
📞 **For returns:**
Message the admin
Order number + Reason bataein"""
    
    # ========================================== #
    # ✅ NEW: CONTACT INFO                       #
    # ========================================== #
    
    def get_contact_response(self):
        """Company contact info"""
        try:
            company = self.CompanyInfo.objects.first()
            
            if company:
                result = "📞 **Contact Information:**\n\n"
                
                if company.contact_number:
                    result += f"📱 **Phone:** {company.contact_number}\n"
                
                if company.email:
                    result += f"📧 **Email:** {company.email}\n"
                
                if company.address:
                    result += f"📍 **Address:** {company.address}\n"
                
                if company.website:
                    result += f"🌐 **Website:** {company.website}\n"
                
                result += "\n━━━━━━━━━━━━━━━━━\n"
                result += "🕐 **Support Hours:**\n"
                result += "Mon-Sat: 9 AM - 10 PM\n"
                result += "Sunday: 11 AM - 8 PM"
                
                return result
        except Exception as e:
            logger.error(f"Contact info error: {e}")
        
        return """📞 **Contact Us:**

Contact us:
• Send a message in chat
• Shop page pe "Contact" section dekhein
• Talk to the admin personally

🤝 We are always ready to help you!"""
    
    # ========================================== #
    # ✅ NEW: PRODUCT SEARCH                     #
    # ========================================== #
    
    def get_product_search_response(self, question):
        """Product price/stock search"""
        try:
            # Common stop words
            stop_words = [
                'price', 'rate', 'kitna', 'stock', 'available', 'hai', 'ka', 'ki', 'ke', 
                'kya', 'milega', 'price?', 'kya hai', 'kitne ka', 'kitne ki'
            ]
            
            words = question.lower().split()
            search_words = [w for w in words if w not in stop_words and len(w) > 2]
            
            if search_words:
                query = Q()
                for word in search_words[:3]:
                    query |= Q(name__icontains=word)
                
                products = self.Product.objects.filter(query, is_active=True)[:5]
                
                if products.exists():
                    result = "🔍 **These products were found:**\n\n"
                    
                    for p in products:
                        # Stock check
                        stock = self.Inventory.objects.filter(
                            product=p
                        ).aggregate(total=Sum('stock'))['total'] or 0
                        
                        stock_status = "✅ Available" if stock > 0 else "❌ Out of Stock"
                        
                        # Price
                        price = p.price or Decimal('0')
                        
                        result += f"📦 **{p.name}**\n"
                        result += f"   💰 Rs. {price:,.2f}\n"
                        result += f"   {stock_status}\n"
                        
                        if p.serial_no:
                            result += f"   🏷️ {p.serial_no}\n"
                        
                        result += "\n"
                    
                    result += "━━━━━━━━━━━━━━━━━\n"
                    result += "🛒 Go to the shop page to place an order!\n"
                    result += "🔗 `/shop/`"
                    
                    return result
        except Exception as e:
            logger.error(f"Product search error: {e}")
        
        return """💰 **Product Price/Stock Check:**

**Option 1: Online Search Karein**
🔗 `/shop/` pe jaayein
- Enter the product name in the search box
- Price + Stock will all be shown

**Option 2: Yahan Bataein**
Enter the product name and I will check it.

━━━━━━━━━━━━━━━━━
💡 **Tip:** Write the correct spelling or search in the shop."""
    
    # ========================================== #
    # GREETINGS & HELP                           #
    # ========================================== #
    
    def greeting_response(self):
        hour = datetime.now().hour
        
        if hour < 12:
            time_greet = "Good Morning 🌅"
        elif hour < 17:
            time_greet = "Good Afternoon ☀️"
        else:
            time_greet = "Good Evening 🌙"
        
        name = ""
        if self.user and hasattr(self.user, 'get_full_name'):
            full_name = self.user.get_full_name() or self.user.username
            if full_name:
                name = f" {full_name}"
        
        return f"""{time_greet}{name}!

Main aapka **Business Assistant** hoon 🤖

What would you like to know?
📊 Sales | 💰 Profit | 📦 Stock | 👥 Customers
💵 Cash | 🚨 Alerts | ✅ Tasks

Or ask about orders/delivery! 📦

Bas likhein ya mic dabayein! 🎤"""
    
    def help_response(self):
        return """🤖 **What Can I Do:**

🛒 **Customer Help:**
"order status check karo"
"payment methods kya hain"
"delivery kitne din mein"
"return kaise karun"
"[product name] ki price"

📊 **Business Info:**
"aaj ki sale"
"profit kitna hai"
"low stock products"
"top customers"
"cash balance"

📋 **Operations:**
"mere tasks"
"kpi status"
"alerts dikhao"

💡 **Tips:**
- Write in simple Roman Urdu
- Ya 🎤 mic button dabayein
- Any question, I will help!"""
    
    def who_are_you_response(self):
        return """Main hoon **Business Assistant** 🤖

Aapka smart AI assistant jo:
• 📊 Business numbers jaanta hai
• 🛒 Can give order/delivery info
• 💡 Gives suggestions
• 🚨 Alerts dikhata hai
• 🎤 Replies by voice

Bas poochein — main bata dunga! 😊"""
    
    # ========================================== #
    # SALES ANSWERS                              #
    # ========================================== #
    
    def get_sales_answer(self, question):
        today = localdate()
        
        if any(w in question for w in ['today', 'aaj', 'aaj ki']):
            sales = self.Sale.objects.filter(sale_date__date=today)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            
            top = sales.values('saleitem__product__name').annotate(
                qty=Sum('saleitem__qty')
            ).order_by('-qty').first()
            
            top_str = f"\n🏆 Top: **{top['saleitem__product__name']}** ({top['qty']:.0f} units)" if top else ""
            
            return f"""📊 **Aaj ki Sales:**

💰 Total: **Rs. {total:,.2f}**
🛒 Orders: **{count}**{top_str}

Want to know anything else? 😊"""
        
        if any(w in question for w in ['yesterday', 'kal']):
            yesterday = today - timedelta(days=1)
            sales = self.Sale.objects.filter(sale_date__date=yesterday)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            
            return f"""📊 **Kal ki Sales:**

💰 Total: **Rs. {total:,.2f}**
🛒 Orders: **{count}**"""
        
        if any(w in question for w in ['week', 'hafte', 'hafta', '7 days']):
            week_ago = today - timedelta(days=7)
            sales = self.Sale.objects.filter(sale_date__date__gte=week_ago)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            avg = total / count if count > 0 else 0
            
            return f"""📊 **Is Hafte ki Sales:**

💰 Total: **Rs. {total:,.2f}**
🛒 Orders: **{count}**
📈 Average: **Rs. {avg:,.2f}/order**

📅 Period: {week_ago.strftime('%d %b')} - {today.strftime('%d %b')}"""
        
        if any(w in question for w in ['month', 'mahine', 'mahina', '30 days']):
            month_start = today.replace(day=1)
            sales = self.Sale.objects.filter(sale_date__date__gte=month_start)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            
            last_month_start = (month_start - timedelta(days=1)).replace(day=1)
            last_month = self.Sale.objects.filter(
                sale_date__date__gte=last_month_start,
                sale_date__date__lt=month_start
            ).aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            
            growth = 0
            if last_month > 0:
                growth = ((total - last_month) / last_month) * 100
            
            growth_emoji = "📈" if growth > 0 else "📉" if growth < 0 else "➡️"
            
            return f"""📊 **Is Mahine ki Sales:**

💰 Total: **Rs. {total:,.2f}**
🛒 Orders: **{count}**

{growth_emoji} **Growth: {growth:+.1f}%** (vs last month)

📅 {month_start.strftime('%B %Y')}"""
        
        # Default
        month_start = today.replace(day=1)
        total = self.Sale.objects.filter(
            sale_date__date__gte=month_start
        ).aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
        
        return f"""📊 **Sales Summary:**

📅 Is Mahine: **Rs. {total:,.2f}**

💡 Specific poochein:
- "aaj ki sale"
- "kal ki sale"  
- "is hafte ki sale"
- "is mahine ki sale\""""
    
    # ========================================== #
    # PURCHASE ANSWERS                           #
    # ========================================== #
    
    def get_purchase_answer(self, question):
        today = localdate()
        
        if any(w in question for w in ['today', 'aaj']):
            purchases = self.Purchase.objects.filter(pur_date__date=today)
            total = purchases.aggregate(t=Sum('purchaseitem__total_amt'))['t'] or Decimal('0')
            count = purchases.count()
            
            return f"""📥 **Aaj ke Purchases:**

💰 Total: **Rs. {total:,.2f}**
📦 Bills: **{count}**"""
        
        if any(w in question for w in ['month', 'mahine']):
            month_start = today.replace(day=1)
            purchases = self.Purchase.objects.filter(pur_date__date__gte=month_start)
            total = purchases.aggregate(t=Sum('purchaseitem__total_amt'))['t'] or Decimal('0')
            count = purchases.count()
            
            return f"""📥 **Is Mahine ke Purchases:**

💰 Total: **Rs. {total:,.2f}**
📦 Bills: **{count}**"""
        
        month_start = today.replace(day=1)
        total = self.Purchase.objects.filter(
            pur_date__date__gte=month_start
        ).aggregate(t=Sum('purchaseitem__total_amt'))['t'] or Decimal('0')
        
        return f"""📥 **Purchase Summary:**

📅 Is Mahine: **Rs. {total:,.2f}**"""
    
    # ========================================== #
    # PROFIT ANSWERS                             #
    # ========================================== #
    
    def get_profit_answer(self, question):
        today = localdate()
        
        if any(w in question for w in ['today', 'aaj']):
            start_date = today
            period = "Aaj"
        elif any(w in question for w in ['week', 'hafte']):
            start_date = today - timedelta(days=7)
            period = "Is Hafte"
        elif any(w in question for w in ['year', 'saal']):
            start_date = today.replace(month=1, day=1)
            period = "Is Saal"
        else:
            start_date = today.replace(day=1)
            period = "Is Mahine"
        
        sales_total = self.Sale.objects.filter(
            sale_date__date__gte=start_date
        ).aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
        
        discount_total = self.Sale.objects.filter(
            sale_date__date__gte=start_date
        ).aggregate(t=Sum('discount_value'))['t'] or Decimal('0')
        
        purchases_total = self.Purchase.objects.filter(
            pur_date__date__gte=start_date
        ).aggregate(t=Sum('purchaseitem__total_amt'))['t'] or Decimal('0')
        
        expenses_total = self.Expense.objects.filter(
            expense_date__gte=start_date
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        
        net_profit = sales_total - purchases_total - expenses_total
        margin = (net_profit / sales_total * 100) if sales_total > 0 else 0
        
        if net_profit > 0:
            status = "✅ **PROFITABLE** 🎉"
        elif net_profit < 0:
            status = "⚠️ **LOSS** 😟"
        else:
            status = "➡️ **BREAK EVEN**"
        
        return f"""💰 **{period} ka Profit:**

━━━━━━━━━━━━━━━━━━━━━━━
📊 **Revenue:**
├─ Sales: Rs. {sales_total:,.2f}
└─ Discounts: (Rs. {discount_total:,.2f})

📥 **Costs:**
├─ Purchases: Rs. {purchases_total:,.2f}
└─ Expenses: Rs. {expenses_total:,.2f}
━━━━━━━━━━━━━━━━━━━━━━━

💵 **Net Profit: Rs. {net_profit:,.2f}**
📈 **Margin: {margin:.1f}%**

{status}"""
    
    # ========================================== #
    # STOCK ANSWERS                              #
    # ========================================== #
    
    def get_stock_answer(self, question):
        if any(w in question for w in ['low', 'kam', 'shortage']):
            low_stock = self.Inventory.objects.filter(
                stock__lt=F('product__low_stock_threshold'),
                stock__gt=0
            ).select_related('product').order_by('stock')[:10]
            
            if low_stock:
                items = "\n".join([
                    f"⚠️ **{item.product.name}**: {item.stock:.0f} units (min: {item.product.low_stock_threshold:.0f})"
                    for item in low_stock
                ])
                return f"""📦 **Low Stock Alert:**

{items}

💡 **Action:** Inhe turant order karein!"""
            return "✅ **All products have enough stock!** 🎉"
        
        if any(w in question for w in ['out', 'khatam', 'zero', 'empty']):
            out_stock = self.Inventory.objects.filter(
                stock__lte=0
            ).select_related('product')[:10]
            
            if out_stock:
                items = "\n".join([
                    f"❌ **{item.product.name}**" 
                    for item in out_stock
                ])
                return f"""📦 **Out of Stock:**

{items}

🚨 **Urgent:** Order these now!"""
            return "✅ **No product is out of stock!**"
        
        if any(w in question for w in ['value', 'worth', 'total']):
            total_value = Decimal('0')
            for inv in self.Inventory.objects.all()[:100]:
                total_value += inv.stock_value()
            
            return f"""💰 **Total Stock Value:**

📦 **Rs. {total_value:,.2f}**"""
        
        # Default
        total_products = self.Product.objects.count()
        
        low_count = self.Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold'),
            stock__gt=0
        ).count()
        
        out_count = self.Inventory.objects.filter(stock__lte=0).count()
        
        total_value = Decimal('0')
        for inv in self.Inventory.objects.all()[:100]:
            total_value += inv.stock_value()
        
        return f"""📦 **Stock Summary:**

📊 Total Products: **{total_products}**
💰 Total Value: **Rs. {total_value:,.2f}**

⚠️ Low Stock: **{low_count}**
❌ Out of Stock: **{out_count}**

Specific poochein:
- "low stock products"
- "out of stock"
- "total stock value\""""
    
    # ========================================== #
    # CUSTOMER ANSWERS                           #
    # ========================================== #
    
    def get_customer_answer(self, question):
        total = self.Customer.objects.count()
        
        if any(w in question for w in ['top', 'best', 'highest']):
            top = self.Customer.objects.annotate(
                total_sales=Sum('sale__saleitem__total_amt')
            ).filter(total_sales__gt=0).order_by('-total_sales')[:5]
            
            items = "\n".join([
                f"{i+1}. **{c.name}**: Rs. {c.total_sales:,.2f}"
                for i, c in enumerate(top)
            ])
            
            return f"""🏆 **Top 5 Customers:**

{items}"""
        
        if any(w in question for w in ['outstanding', 'baqaya', 'udhar']):
            outstanding_list = []
            total_out = Decimal('0')
            
            for c in self.Customer.objects.all()[:500]:
                bal = c.adjusted_outstanding_balance()
                if bal > 0:
                    outstanding_list.append({'name': c.name, 'balance': bal})
                    total_out += bal
            
            outstanding_list.sort(key=lambda x: x['balance'], reverse=True)
            top = outstanding_list[:5]
            items = "\n".join([
                f"⚠️ **{c['name']}**: Rs. {c['balance']:,.2f}"
                for c in top
            ])
            
            return f"""💰 **Customer Outstanding:**

💵 Total: **Rs. {total_out:,.2f}**
👥 Customers: **{len(outstanding_list)}**

**Top 5:**
{items}"""
        
        return f"""👥 **Customer Summary:**

📊 Total Customers: **{total}**

Specific poochein:
- "top customers"
- "customer outstanding\""""
    
    # ========================================== #
    # VENDOR ANSWERS                             #
    # ========================================== #
    
    def get_vendor_answer(self, question):
        total = self.Vendor.objects.count()
        
        if any(w in question for w in ['outstanding', 'baqaya', 'payable']):
            outstanding_list = []
            total_out = Decimal('0')
            
            for v in self.Vendor.objects.all()[:500]:
                bal = v.outstanding_balance()
                if bal > 0:
                    outstanding_list.append({'name': v.name, 'balance': bal})
                    total_out += bal
            
            outstanding_list.sort(key=lambda x: x['balance'], reverse=True)
            top = outstanding_list[:5]
            items = "\n".join([
                f"⚠️ **{v['name']}**: Rs. {v['balance']:,.2f}"
                for v in top
            ])
            
            return f"""💸 **Vendor Payables:**

💰 Total: **Rs. {total_out:,.2f}**
🏢 Vendors: **{len(outstanding_list)}**

**Top 5:**
{items}"""
        
        return f"""🏢 **Vendor Summary:**

📊 Total Vendors: **{total}**

Specific poochein:
- "vendor payables"
- "vendor outstanding\""""
    
    # ========================================== #
    # PAYMENT ANSWERS                            #
    # ========================================== #
    
    def get_payment_answer(self, question):
        total_out = Decimal('0')
        count = 0
        
        for c in self.Customer.objects.all()[:500]:
            bal = c.adjusted_outstanding_balance()
            if bal > 0:
                total_out += bal
                count += 1
        
        total_pay = Decimal('0')
        v_count = 0
        
        for v in self.Vendor.objects.all()[:500]:
            bal = v.outstanding_balance()
            if bal > 0:
                total_pay += bal
                v_count += 1
        
        net = total_out - total_pay
        
        return f"""💰 **Payment Summary:**

📥 **Receive (Customers):**
Rs. {total_out:,.2f} from {count} customers

📤 **Pay (Vendors):**
Rs. {total_pay:,.2f} to {v_count} vendors

━━━━━━━━━━━━━━━━━━━━
📊 **Net Position: Rs. {net:,.2f}**

💡 "customer outstanding" ya "vendor payables" poochein"""
    
    # ========================================== #
    # CASH ANSWERS                               #
    # ========================================== #
    
    def get_cash_answer(self, question):
        try:
            balance = self.CashBalance.get_balance()
        except:
            balance = Decimal('0')
        
        return f"""💵 **Cash Balance:**

💰 Available: **Rs. {balance:,.2f}**

💡 Ask "cash report" for details"""
    
    # ========================================== #
    # EXPENSE ANSWERS                            #
    # ========================================== #
    
    def get_expense_answer(self, question):
        today = localdate()
        month_start = today.replace(day=1)
        
        total = self.Expense.objects.filter(
            expense_date__gte=month_start
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        
        count = self.Expense.objects.filter(
            expense_date__gte=month_start
        ).count()
        
        top = self.Expense.objects.filter(
            expense_date__gte=month_start
        ).values('category__name').annotate(
            total=Sum('amount')
        ).order_by('-total').first()
        
        top_str = f"\n📂 Top: **{top['category__name']}** (Rs. {top['total']:,.2f})" if top else ""
        
        return f"""💸 **Expense Summary:**

📅 Is Mahine: **Rs. {total:,.2f}**
📊 Total Expenses: **{count}**{top_str}"""
    
    # ========================================== #
    # EMPLOYEE ANSWERS                           #
    # ========================================== #
    
    def get_employee_answer(self, question):
        total = self.Employee.objects.count()
        active = self.Employee.objects.filter(status='active').count()
        on_leave = self.Employee.objects.filter(status='on_leave').count()
        
        return f"""👔 **Employee Summary:**

👥 Total: **{total}**
✅ Active: **{active}**
🏖️ On Leave: **{on_leave}**"""
    
    # ========================================== #
    # TASK ANSWERS                               #
    # ========================================== #
    
    def get_task_answer(self, question):
        if any(w in question for w in ['my', 'mere', 'mera']):
            if self.user:
                emp = self.Employee.objects.filter(email=self.user.email).first()
                if emp:
                    my_tasks = self.OperationTask.objects.filter(
                        assigned_to=emp,
                        status__in=['pending', 'in_progress']
                    ).order_by('due_date')[:5]
                    
                    if my_tasks:
                        items = "\n".join([
                            f"• **{t.title}** ({t.get_status_display()}) - Due: {t.due_date.strftime('%d %b')}"
                            for t in my_tasks
                        ])
                        return f"""✅ **Mere Tasks:**

{items}

Total: **{my_tasks.count()}**"""
                    return "🎉 **No pending tasks!**"
        
        if any(w in question for w in ['overdue', 'late', 'der']):
            overdue = [
                t for t in self.OperationTask.objects.filter(
                    status__in=['pending', 'in_progress']
                ) if t.is_overdue()
            ]
            
            if overdue:
                items = "\n".join([
                    f"⚠️ **{t.title}** - Due: {t.due_date.strftime('%d %b')}"
                    for t in overdue[:5]
                ])
                return f"""🚨 **Overdue Tasks:**

{items}

Total: **{len(overdue)}**"""
            return "✅ **No overdue tasks!**"
        
        pending = self.OperationTask.objects.filter(status='pending').count()
        in_progress = self.OperationTask.objects.filter(status='in_progress').count()
        completed = self.OperationTask.objects.filter(status='completed').count()
        
        overdue = sum(
            1 for t in self.OperationTask.objects.filter(
                status__in=['pending', 'in_progress']
            ) if t.is_overdue()
        )
        
        return f"""✅ **Task Summary:**

⏳ Pending: **{pending}**
⚙️ In Progress: **{in_progress}**
✅ Completed: **{completed}**
⚠️ Overdue: **{overdue}**

💡 "mere tasks" ya "overdue tasks" poochein"""
    
    # ========================================== #
    # PLAN ANSWERS                               #
    # ========================================== #
    
    def get_plan_answer(self, question):
        active = self.BusinessOperationPlan.objects.filter(
            status__in=['active', 'in_progress']
        )
        
        count = active.count()
        
        if count == 0:
            return "📋 **There is no active plan**"
        
        items = "\n".join([
            f"• **{p.plan_no}** - {p.title} ({p.progress_percent:.0f}%)"
            for p in active[:5]
        ])
        
        return f"""📋 **Active Plans:**

{items}

Total: **{count}**"""
    
    # ========================================== #
    # KPI ANSWERS                                #
    # ========================================== #
    
    def get_kpi_answer(self, question):
        kpis = self.OperationsKPI.objects.filter(is_active=True)
        
        if not kpis.exists():
            return "📊 **No KPI is set**"
        
        on_track = kpis.filter(status='on_track').count()
        warning = kpis.filter(status='warning').count()
        critical = kpis.filter(status='critical').count()
        achieved = kpis.filter(status='achieved').count()
        
        critical_kpis = kpis.filter(status__in=['warning', 'critical'])[:3]
        critical_str = ""
        if critical_kpis:
            items = "\n".join([
                f"⚠️ **{k.name}**: {k.progress_percent:.0f}%"
                for k in critical_kpis
            ])
            critical_str = f"\n\n**Needs Attention:**\n{items}"
        
        return f"""📊 **KPI Status:**

✅ On Track: **{on_track}**
⚠️ Warning: **{warning}**
🔴 Critical: **{critical}**
🎉 Achieved: **{achieved}**{critical_str}"""
    
    # ========================================== #
    # AI ANSWERS                                 #
    # ========================================== #
    
    def get_ai_answer(self, question):
        insights = self.AIOperationsInsight.objects.filter(
            is_resolved=False, is_ignored=False
        ).order_by('-detected_at')[:3]
        
        if not insights:
            return """🤖 **AI Analysis:**

There are no insights right now.

💡 **Tip:** Operations Dashboard pe "Run AI Analysis" button dabayein!"""
        
        items = "\n".join([
            f"{i+1}. **{insight.title}**\n   {insight.description[:80]}..."
            for i, insight in enumerate(insights)
        ])
        
        return f"""🤖 **AI Insights:**

{items}

💡 Complete details Operations Dashboard pe!"""
    
    # ========================================== #
    # ALERTS ANSWERS                             #
    # ========================================== #
    
    def get_alert_answer(self, question):
        try:
            from .models import OperationAlert, Notification
            
            alerts = OperationAlert.objects.filter(is_resolved=False)[:5]
            
            if self.user:
                notifications = Notification.objects.filter(
                    Q(user=self.user) | Q(user__isnull=True),
                    is_read=False
                )[:5]
            else:
                notifications = []
            
            alert_str = ""
            if alerts:
                items = "\n".join([
                    f"🚨 **{a.title}**"
                    for a in alerts
                ])
                alert_str = f"\n\n**Operation Alerts:**\n{items}"
            
            notif_count = notifications.count() if hasattr(notifications, 'count') else len(notifications)
            alert_count = alerts.count() if hasattr(alerts, 'count') else len(alerts)
            
            return f"""🔔 **Alerts Summary:**

📢 Unread Notifications: **{notif_count}**
🚨 Active Alerts: **{alert_count}**{alert_str}"""
        except Exception as e:
            logger.error(f"Alert error: {e}")
            return "🔔 **Could not load alerts.**"
    
    # ========================================== #
    # INSTALLMENT ANSWERS                        #
    # ========================================== #
    
    def get_installment_answer(self, question):
        active = self.SaleInstallment.objects.filter(
            status__in=['pending', 'partial']
        )
        
        count = active.count()
        total_outstanding = sum(i.remaining_amount() for i in active)
        
        overdue = [
            i for i in active 
            if i.next_due_date and i.next_due_date < localdate()
        ]
        
        return f"""📅 **Installment Summary:**

📋 Active Plans: **{count}**
💰 Outstanding: **Rs. {total_outstanding:,.2f}**
⚠️ Overdue: **{len(overdue)}**"""
    
    # ========================================== #
    # SHAREHOLDER ANSWERS                        #
    # ========================================== #
    
    def get_shareholder_answer(self, question):
        total = self.Shareholder.objects.filter(status='active').count()
        
        total_shares = self.Share.objects.aggregate(
            t=Sum('quantity')
        )['t'] or 0
        
        price = self.SharePrice.objects.filter(is_active=True).first()
        price_str = f"Rs. {price.price:,.2f}" if price else "Not set"
        
        return f"""👥 **Shareholder Summary:**

👤 Total Shareholders: **{total}**
📈 Total Shares: **{total_shares:,}**
💰 Current Price: **{price_str}**"""
    
    # ========================================== #
    # DIVIDEND ANSWERS                           #
    # ========================================== #
    
    def get_dividend_answer(self, question):
        total = self.Dividend.objects.count()
        distributed = self.Dividend.objects.filter(status='distributed').count()
        pending = self.Dividend.objects.filter(status__in=['declared', 'approved']).count()
        
        return f"""💰 **Dividend Summary:**

📊 Total: **{total}**
✅ Distributed: **{distributed}**
⏳ Pending: **{pending}**"""
    
    # ========================================== #
    # LOAN ANSWERS                               #
    # ========================================== #
    
    def get_loan_answer(self, question):
        taken = self.Loan.objects.filter(status='active')
        taken_total = sum(l.remaining_amount for l in taken)
        
        given = self.LoanGiven.objects.filter(status='active')
        given_total = sum(l.remaining_amount for l in given)
        
        return f"""🏦 **Loan Summary:**

📥 **Loans Taken:**
Count: {taken.count()}
Outstanding: Rs. {taken_total:,.2f}

📤 **Loans Given:**
Count: {given.count()}
Outstanding: Rs. {given_total:,.2f}

━━━━━━━━━━━━━━━━━━━
📊 Net: Rs. {given_total - taken_total:,.2f}"""
    
    # ========================================== #
    # SERVICE ANSWERS                            #
    # ========================================== #
    
    def get_service_answer(self, question):
        pending = self.ServiceRequest.objects.filter(status='pending').count()
        in_progress = self.ServiceRequest.objects.filter(status='in_progress').count()
        completed = self.ServiceRequest.objects.filter(status='completed').count()
        
        return f"""🛠️ **Service Summary:**

⏳ Pending: **{pending}**
⚙️ In Progress: **{in_progress}**
✅ Completed: **{completed}**"""
    
    # ========================================== #
    # ORDER ANSWERS                              #
    # ========================================== #
    
    def get_order_answer(self, question):
        sale_orders = self.SaleOrder.objects.filter(status='pending').count()
        purchase_orders = self.PurchaseOrder.objects.filter(status='pending').count()
        
        return f"""📋 **Order Summary:**

🛒 Pending Sale Orders: **{sale_orders}**
📥 Pending Purchase Orders: **{purchase_orders}**"""
    
    # ========================================== #
    # TOP ANSWERS                                #
    # ========================================== #
    
    def get_top_answer(self, question):
        today = localdate()
        month_start = today.replace(day=1)
        
        if any(w in question for w in ['product', 'products', 'maal']):
            top = self.Sale.objects.filter(
                sale_date__date__gte=month_start
            ).values('saleitem__product__name').annotate(
                qty=Sum('saleitem__qty'),
                amount=Sum('saleitem__total_amt')
            ).order_by('-amount')[:5]
            
            items = "\n".join([
                f"{i+1}. **{p['saleitem__product__name']}**\n   Qty: {p['qty']:.0f} | Rs. {p['amount']:,.2f}"
                for i, p in enumerate(top)
            ])
            
            return f"""🏆 **Top 5 Products (This Month):**

{items}"""
        
        if any(w in question for w in ['customer', 'customers']):
            top = self.Customer.objects.annotate(
                total=Sum('sale__saleitem__total_amt')
            ).filter(total__gt=0).order_by('-total')[:5]
            
            items = "\n".join([
                f"{i+1}. **{c.name}**: Rs. {c.total:,.2f}"
                for i, c in enumerate(top)
            ])
            
            return f"""🏆 **Top 5 Customers:**

{items}"""
        
        return """💡 **Specific poochein:**
- "top products"
- "top customers\""""
    
    # ========================================== #
    # SUMMARY ANSWERS                            #
    # ========================================== #
    
    def get_summary_answer(self, question):
        today = localdate()
        month_start = today.replace(day=1)
        
        sales = self.Sale.objects.filter(
            sale_date__date__gte=month_start
        ).aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
        
        purchases = self.Purchase.objects.filter(
            pur_date__date__gte=month_start
        ).aggregate(t=Sum('purchaseitem__total_amt'))['t'] or Decimal('0')
        
        try:
            cash = self.CashBalance.get_balance()
        except:
            cash = Decimal('0')
        
        pending_tasks = self.OperationTask.objects.filter(status='pending').count()
        
        low_stock = self.Inventory.objects.filter(
            stock__lt=F('product__low_stock_threshold'),
            stock__gt=0
        ).count()
        
        return f"""📊 **Business Overview:**

━━━━━━━━━━━━━━━━━━━━━━━
💰 **Financial (This Month):**
├─ Sales: Rs. {sales:,.2f}
├─ Purchases: Rs. {purchases:,.2f}
└─ Cash: Rs. {cash:,.2f}

📋 **Operations:**
├─ Pending Tasks: {pending_tasks}
└─ Low Stock: {low_stock}

━━━━━━━━━━━━━━━━━━━━━━━

💡 Specific cheez poochein:
- "profit kitna hai"
- "aaj ki sale"
- "mere tasks"
- "low stock\""""
    
    # ========================================== #
    # DEFAULT RESPONSE                           #
    # ========================================== #
    
    def default_response(self, question):
        return f"""🤔 **I did not understand:**

"{question[:100]}"

💡 **Try this:**

🛒 **Customer Help:**
• "order status check karo"
• "payment methods"
• "delivery kitne din"
• "return policy"

📊 **Business:**
• "aaj ki sale"
• "profit kitna hai"
• "low stock products"
• "cash balance"

📋 **Operations:**
• "mere tasks"
• "kpi status"
• "alerts"

Ya **help** likhein! 😊"""

# ==========================================
# 🎯 CUSTOMER CHATBOT — Sirf customer queries
# ==========================================
class CustomerChatbot:
    """
    Chatbot for customers — customer-related info ONLY
    
    ✅ Allowed:
    - Greetings, help, thanks
    - Product search, price, stock
    - Order status, tracking
    - Payment methods, delivery, returns
    - Contact info
    
    ❌ NOT Allowed (business secrets):
    - Sales, profit, loss
    - Cash balance, accounts
    - Employee info, salary
    - Vendor info, purchase
    - Business reports
    - Shareholder data
    - ANY business operations data
    """
    
    def __init__(self, user=None):
        self.user = user
        
        try:
            from .models import (
                Product, Category, Brand, CompanyInfo,
                SaleOrder, Customer, CustomerProfile
            )
            self.Product = Product
            self.Category = Category
            self.Brand = Brand
            self.CompanyInfo = CompanyInfo
            self.SaleOrder = SaleOrder
            self.Customer = Customer
            self.CustomerProfile = CustomerProfile
        except Exception as e:
            logger.error(f"CustomerChatbot model import error: {e}")
            raise
    
    def get_response(self, question):
        """Main response method"""
        if not question:
            return "Please ask something 😊"
        
        try:
            return self._process_question(question)
        except Exception as e:
            logger.error(f"Customer chatbot error: {e}")
            return (
                "🤔 **Sorry, there was a technical issue.**\n\n"
                "Please try again or contact an admin.\n\n"
                "📞 Talk to Support."
            )
    
    def _process_question(self, question):
        """Process question with customer-friendly keywords only"""
        
        q = question.lower().strip()
        q_clean = re.sub(r'[^\w\s]', '', q)
        
        # ========================================== #
        # 1. GREETINGS                               #
        # ========================================== #
        if any(w in q_clean for w in ['hello', 'hi', 'hey', 'salam', 'assalam', 'helo', 'aoa']):
            return self.greeting_response()
        
        if any(w in q_clean for w in ['thank', 'shukriya', 'shukria', 'thanks', 'thanx', 'jazak']):
            return "You're welcome! 😊 Anything else you want to ask?"
        
        if any(w in q_clean for w in ['bye', 'khuda hafiz', 'goodbye', 'allah hafiz']):
            return "Allah Hafiz! 👋 See you again."
        
        if any(w in q_clean for w in ['help', 'madad', 'kya kar sakte', 'kya kar skte']):
            return self.help_response()
        
        if any(w in q_clean for w in ['kaun ho', 'who are you', 'tum kon', 'aap kon']):
            return self.who_are_you_response()
        
        # ========================================== #
        # 2. ORDER TRACKING                          #
        # ========================================== #
        if any(w in q_clean for w in ['order status', 'track order', 'order kahan', 'order ka', 'order no', 'mera order']):
            return self.get_order_status_response(question)
        
        order_match = re.search(r'(?:order|ord|#)\s*[-#]?\s*(\d+)', question.lower())
        if order_match:
            return self.get_order_status_response(question, order_match.group(1))
        
        # ========================================== #
        # 3. PAYMENT METHODS                         #
        # ========================================== #
        if any(w in q_clean for w in ['payment method', 'payment kaise', 'pay kaise', 'cod', 'jazzcash', 'easypaisa', 'bank transfer', 'payment options']):
            return self.get_payment_methods_response()
        
        # ========================================== #
        # 4. DELIVERY INFO                           #
        # ========================================== #
        if any(w in q_clean for w in ['delivery', 'shipping', 'courier', 'kitne din', 'kab aayega', 'kitna time']):
            return self.get_delivery_response()
        
        # ========================================== #
        # 5. RETURN / REFUND                         #
        # ========================================== #
        if any(w in q_clean for w in ['return', 'refund', 'wapas', 'exchange', 'wapisi']):
            return self.get_return_response()
        
        # ========================================== #
        # 6. CONTACT INFO                            #
        # ========================================== #
        if any(w in q_clean for w in ['contact', 'helpline', 'address', 'location', 'email', 'phone number', 'shop address']):
            return self.get_contact_response()
        
        # ========================================== #
        # 7. PRODUCT SEARCH / PRICE                  #
        # ========================================== #
        if any(w in q_clean for w in ['price', 'rate', 'kitna', 'stock hai', 'available', 'milega', 'product']):
            return self.get_product_search_response(question)
        
        # ========================================== #
        # 8. MY ORDERS (Customer Specific)           #
        # ========================================== #
        if any(w in q_clean for w in ['my order', 'mere order', 'order history', 'mera order']):
            return self.get_my_orders_response()
        
        # ========================================== #
        # 9. CART HELP                               #
        # ========================================== #
        if any(w in q_clean for w in ['cart', 'add to cart', 'checkout']):
            return self.get_cart_help_response()
        
        # ========================================== #
        # 10. SHOP INFO                              #
        # ========================================== #
        if any(w in q_clean for w in ['shop timing', 'timing', 'open', 'band', 'khula', 'hours']):
            return self.get_shop_timing_response()
        
        # ========================================== #
        # 11. DEFAULT — Does NOT give business data      #
        # ========================================== #
        return self.default_response(question)
    
    # ========================================== #
    # RESPONSE METHODS                           #
    # ========================================== #
    
    def greeting_response(self):
        hour = datetime.now().hour
        
        if hour < 12:
            time_greet = "Good Morning 🌅"
        elif hour < 17:
            time_greet = "Good Afternoon ☀️"
        else:
            time_greet = "Good Evening 🌙"
        
        name = ""
        if self.user and hasattr(self.user, 'get_full_name'):
            full_name = self.user.get_full_name() or self.user.username
            if full_name:
                name = f" {full_name}"
        
        return f"""{time_greet}{name}!

Main **Customer Support** assistant hoon 🤖

What help do you need?
🛒 Product search
📦 Order tracking
💳 Payment info
🚚 Delivery info
↩️ Return / Refund

Bas likhein ya mic dabayein! 🎤"""
    
    def help_response(self):
        return """🤖 **What Can I Do:**

🛒 **Products:**
• "iPhone ki price"
• "sale wale products"
• "kya available hai"

📦 **Orders:**
• "mera order status"
• "order track karo"
• "order #1234"

💳 **Payment & Delivery:**
• "payment methods"
• "delivery kitne din"
• "return policy"

📞 **Contact:**
• "shop address"
• "contact number"

Bas apna sawal likhein! 😊"""
    
    def who_are_you_response(self):
        return """Main hoon **Customer Support Assistant** 🤖

I can help you with:
• 🛒 Product search
• 📦 Order tracking
• 💳 Payment info
• 🚚 Delivery info
• ↩️ Return policy

Bas poochein! 😊"""
    
    def get_order_status_response(self, question, order_no=None):
        """Order status check"""
        
        if order_no:
            # Try to find order
            try:
                order = self.SaleOrder.objects.filter(order_no__icontains=order_no).first()
                
                if order:
                    status_display = order.get_status_display()
                    total = sum(item.total_amt for item in order.items.all())
                    
                    return f"""📦 **Order #{order.order_no}:**

📊 **Status:** {status_display}
📅 **Date:** {order.order_date.strftime('%d-%m-%Y')}
💰 **Total:** Rs. {total:,.2f}

For more details:
🔗 `/shop/track/?order_no={order.order_no}`"""
                else:
                    return f"""🔍 **Order #{order_no} nahi mila**

Please enter the correct order number, or check your phone number.

🔗 **Track Order:** `/shop/track/`"""
            except Exception as e:
                logger.error(f"Order status error: {e}")
        
        return """📦 **To Check Order Status:**

**Option 1: Online Track Karein**
🔗 `/shop/track/` pe jaayein
- Order number daalein
- Phone number daalein
- Live status dekhein

**Option 2: Yahan Bataein**
Enter your order number and I will check it."""
    
    def get_payment_methods_response(self):
        return """💳 **Payment Methods:**

💰 **Cash on Delivery**
Ghar par cash dein — no extra charge

📱 **JazzCash**
Mobile wallet se pay

📱 **EasyPaisa**
Mobile wallet se pay

🏦 **Bank Transfer**
For large orders

━━━━━━━━━━━━━━━━━
🔒 **100% Secure**"""
    
    def get_delivery_response(self):
        return """🚚 **Delivery Information:**

⏱️ **Time:**
• Standard: **2-4 working days**
• Express: **1-2 working days**

💵 **Charges:**
• **FREE** — Rs. 1,000+ orders
• **Rs. 100** — Below Rs. 1,000

📦 **Tracking:**
Order confirm hone pe tracking number milega

━━━━━━━━━━━━━━━━━
❓ Kuch aur poochein!"""
    
    def get_return_response(self):
        return """↩️ **Return & Refund:**

✅ **7-Day Return** — Within 7 days of receiving

📋 **Conditions:**
• Original packaging
• Unused product
• Bill zaroori

💰 **Refund:** 3-5 working days

━━━━━━━━━━━━━━━━━
📞 For returns, message the admin"""
    
    def get_contact_response(self):
        try:
            company = self.CompanyInfo.objects.first()
            
            if company:
                result = "📞 **Contact Information:**\n\n"
                
                if company.contact_number:
                    result += f"📱 **Phone:** {company.contact_number}\n"
                
                if company.email:
                    result += f"📧 **Email:** {company.email}\n"
                
                if company.address:
                    result += f"📍 **Address:** {company.address}\n"
                
                if company.website:
                    result += f"🌐 **Website:** {company.website}\n"
                
                result += "\n━━━━━━━━━━━━━━━━━\n"
                result += "🕐 **Support Hours:**\n"
                result += "Mon-Sat: 9 AM - 10 PM\n"
                result += "Sunday: 11 AM - 8 PM"
                
                return result
        except Exception as e:
            logger.error(f"Contact info error: {e}")
        
        return """📞 **Contact Us:**

Contact us:
• Send a message in chat
• Shop page pe "Contact" section dekhein
• Talk to the admin personally

🤝 We are here to help!"""
    
    def get_product_search_response(self, question):
        """Product price/stock search"""
        try:
            # Stop words remove karo
            stop_words = [
                'price', 'rate', 'kitna', 'stock', 'available', 'hai', 'ka', 'ki', 'ke', 
                'kya', 'milega', 'kya hai', 'kitne ka', 'kitne ki', 'product', 'products'
            ]
            
            words = question.lower().split()
            search_words = [w for w in words if w not in stop_words and len(w) > 2]
            
            if search_words:
                query = Q()
                for word in search_words[:3]:
                    query |= Q(name__icontains=word)
                
                products = self.Product.objects.filter(query, is_active=True)[:5]
                
                if products.exists():
                    result = "🔍 **These products were found:**\n\n"
                    
                    for p in products:
                        # ✅ Stock check
                        from .models import Inventory
                        stock = Inventory.objects.filter(
                            product=p
                        ).aggregate(total=Sum('stock'))['total'] or 0
                        
                        stock_status = "✅ Available" if stock > 0 else "❌ Out of Stock"
                        price = p.price or Decimal('0')
                        
                        result += f"📦 **{p.name}**\n"
                        result += f"   💰 Rs. {price:,.2f}\n"
                        result += f"   {stock_status}\n\n"
                    
                    result += "━━━━━━━━━━━━━━━━━\n"
                    result += "🛒 Go to the shop page to place an order!\n"
                    result += "🔗 `/shop/`"
                    
                    return result
        
        except Exception as e:
            logger.error(f"Product search error: {e}")
        
        return """💰 **Product Price/Stock:**

**Option 1: Online Search**
🔗 `/shop/` pe jaayein
- Enter the name in the search box
- Price + Stock dikhega

**Option 2: Yahan Bataein**
Enter the product name and I will check it."""
    
    def get_my_orders_response(self):
        return """📦 **To See Your Orders:**

🔗 `/shop/my-orders/` pe jaayein

Wahan aapko dikhega:
• Total orders
• Pending orders
• Delivered orders
• Order history

Login zaroori hai! 🔒"""
    
    def get_cart_help_response(self):
        return """🛒 **Shopping Cart Help:**

**To Add Products:**
1. Shop page pe jaayein: `/shop/`
2. Product pe "Add to Cart" dabayein

**To See Your Cart:**
🔗 `/shop/cart/`

**To Check Out:**
Press the "Checkout" button in the cart

Koi masla? Bataein! 😊"""
    
    def get_shop_timing_response(self):
        return """🕐 **Shop Timing:**

📅 **Monday - Saturday:**
9:00 AM - 10:00 PM

📅 **Sunday:**
11:00 AM - 8:00 PM

Online shop **24/7** open hai! 🛒
🔗 `/shop/`"""
    
    def default_response(self, question):
        return f"""🤔 **I did not understand:**

"{question[:100]}"

💡 **Try this:**

🛒 **Products:**
• "[product name] ki price"
• "kya available hai"

📦 **Orders:**
• "mera order status"
• "order track karo"

💳 **Info:**
• "payment methods"
• "delivery info"
• "return policy"

📞 **Contact:**
• "shop address"
• "contact number"

Ya **help** likhein! 😊"""