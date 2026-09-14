"""
AI Chatbot Engine - Complete Business Assistant
Handles all business queries in English, Urdu, and Roman Urdu
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
    """
    
    def __init__(self, user=None):
        self.user = user
        
        # Import models
        from .models import (
            Sale, Purchase, Customer, Vendor, Product, 
            Inventory, Expense, Employee, SaleInstallment,
            OperationsKPI, OperationTask, BusinessOperationPlan,
            CashBalance, Shareholder, Dividend, AIOperationsInsight,
            SaleOrder, PurchaseOrder, DeliveryChallan, GoodsReceivedNote,
            PaymentMethod, VendorPayment, CustomerPayment,
            ExpenseCategory, Department, Project, Budget,
            ServiceRequest, Service, Loan, LoanGiven,
            Share, SharePrice, ShareTransfer, ShareholderMeeting
        )
        
        # Sales & Purchases
        self.Sale = Sale
        self.Purchase = Purchase
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
    
    # ========================================== #
    # MAIN METHOD                                #
    # ========================================== #
    
    def get_response(self, question):
        """Main response method"""
        
        if not question:
            return "Please kuch poochein 😊"
        
        q = question.lower().strip()
        
        # Remove punctuation for matching
        q_clean = re.sub(r'[^\w\s]', '', q)
        
        # ========================================== #
        # GREETINGS                                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['hello', 'hi', 'hey', 'salam', 'assalam', 'helo']):
            return self.greeting_response()
        
        if any(w in q_clean for w in ['thank', 'shukriya', 'shukria', 'thanks', 'thanx']):
            return "You're welcome! 😊 Kuch aur poochna hai?"
        
        if any(w in q_clean for w in ['bye', 'khuda hafiz', 'goodbye', 'allah hafiz']):
            return "Allah Hafiz! 👋 Phir milte hain."
        
        if any(w in q_clean for w in ['help', 'madad', 'kya kar sakte', 'kya kar skte']):
            return self.help_response()
        
        if any(w in q_clean for w in ['kaun ho', 'who are you', 'tum kon', 'aap kon']):
            return self.who_are_you_response()
        
        # ========================================== #
        # SALES                                      #
        # ========================================== #
        
        if any(w in q_clean for w in ['sale', 'sales', 'bikri', 'becha', 'sold', 'sells']):
            return self.get_sales_answer(q_clean)
        
        # ========================================== #
        # PURCHASE                                   #
        # ========================================== #
        
        if any(w in q_clean for w in ['purchase', 'kharida', 'khareeda', 'buying', 'bought']):
            return self.get_purchase_answer(q_clean)
        
        # ========================================== #
        # PROFIT / LOSS                              #
        # ========================================== #
        
        if any(w in q_clean for w in ['profit', 'munafa', 'faida', 'loss', 'nuksan', 'earning']):
            return self.get_profit_answer(q_clean)
        
        # ========================================== #
        # STOCK / INVENTORY                          #
        # ========================================== #
        
        if any(w in q_clean for w in ['stock', 'inventory', 'maal', 'samaan', 'saman']):
            return self.get_stock_answer(q_clean)
        
        # ========================================== #
        # CUSTOMERS                                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['customer', 'client', 'grahak', 'party']):
            return self.get_customer_answer(q_clean)
        
        # ========================================== #
        # VENDORS                                    #
        # ========================================== #
        
        if any(w in q_clean for w in ['vendor', 'supplier', 'dealer']):
            return self.get_vendor_answer(q_clean)
        
        # ========================================== #
        # PAYMENTS / OUTSTANDING                     #
        # ========================================== #
        
        if any(w in q_clean for w in ['payment', 'outstanding', 'baqaya', 'udhar', 'due', 'baqi']):
            return self.get_payment_answer(q_clean)
        
        # ========================================== #
        # CASH                                       #
        # ========================================== #
        
        if any(w in q_clean for w in ['cash', 'nakad', 'naqad', 'balance', 'paisa', 'paise']):
            return self.get_cash_answer(q_clean)
        
        # ========================================== #
        # EXPENSE                                    #
        # ========================================== #
        
        if any(w in q_clean for w in ['expense', 'kharcha', 'kharch', 'kharchay']):
            return self.get_expense_answer(q_clean)
        
        # ========================================== #
        # EMPLOYEES                                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['employee', 'staff', 'worker', 'naukar', 'team']):
            return self.get_employee_answer(q_clean)
        
        # ========================================== #
        # TASKS / OPERATIONS                         #
        # ========================================== #
        
        if any(w in q_clean for w in ['task', 'kaam', 'work', 'assignment']):
            return self.get_task_answer(q_clean)
        
        # ========================================== #
        # PLANS                                      #
        # ========================================== #
        
        if any(w in q_clean for w in ['plan', 'planning', 'mansooba']):
            return self.get_plan_answer(q_clean)
        
        # ========================================== #
        # KPI / TARGETS                              #
        # ========================================== #
        
        if any(w in q_clean for w in ['kpi', 'target', 'performance', 'lakshya']):
            return self.get_kpi_answer(q_clean)
        
        # ========================================== #
        # AI INSIGHTS                                #
        # ========================================== #
        
        if any(w in q_clean for w in ['insight', 'ai', 'analysis', 'salah', 'suggest']):
            return self.get_ai_answer(q_clean)
        
        # ========================================== #
        # ALERTS                                     #
        # ========================================== #
        
        if any(w in q_clean for w in ['alert', 'warning', 'notification', 'itla']):
            return self.get_alert_answer(q_clean)
        
        # ========================================== #
        # INSTALLMENTS                               #
        # ========================================== #
        
        if any(w in q_clean for w in ['installment', 'emi', 'qist', 'kisht']):
            return self.get_installment_answer(q_clean)
        
        # ========================================== #
        # SHAREHOLDERS                               #
        # ========================================== #
        
        if any(w in q_clean for w in ['shareholder', 'share', 'stock holder', 'hissa']):
            return self.get_shareholder_answer(q_clean)
        
        # ========================================== #
        # DIVIDENDS                                  #
        # ========================================== #
        
        if any(w in q_clean for w in ['dividend', 'munafa hissa']):
            return self.get_dividend_answer(q_clean)
        
        # ========================================== #
        # LOANS                                      #
        # ========================================== #
        
        if any(w in q_clean for w in ['loan', 'qarz', 'udhar liya', 'udhar diya']):
            return self.get_loan_answer(q_clean)
        
        # ========================================== #
        # SERVICES                                   #
        # ========================================== #
        
        if any(w in q_clean for w in ['service', 'services', 'khidmat']):
            return self.get_service_answer(q_clean)
        
        # ========================================== #
        # ORDERS                                     #
        # ========================================== #
        
        if any(w in q_clean for w in ['order', 'orders', 'sale order', 'purchase order']):
            return self.get_order_answer(q_clean)
        
        # ========================================== #
        # TOP / BEST                                 #
        # ========================================== #
        
        if any(w in q_clean for w in ['top', 'best', 'best selling', 'sabse zyada', 'highest']):
            return self.get_top_answer(q_clean)
        
        # ========================================== #
        # SUMMARY / REPORT                           #
        # ========================================== #
        
        if any(w in q_clean for w in ['summary', 'overview', 'report', 'situation', 'halat']):
            return self.get_summary_answer(q_clean)
        
        # ========================================== #
        # DEFAULT                                    #
        # ========================================== #
        
        return self.default_response(question)
    
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
            name = self.user.get_full_name() or self.user.username
            name = f" {name}"
        
        return f"""{time_greet}{name}!

Main aapka **Business Assistant** hoon 🤖

Kya jaanna chahte hain?
- 📊 Sales
- 💰 Profit
- 📦 Stock
- 👥 Customers
- 💵 Cash
- 🚨 Alerts
- ✅ Tasks

Bas likhein ya mic dabayein! 🎤"""
    
    def help_response(self):
        return """🤖 **Main Kya Kar Sakta Hoon:**

📊 **Sales & Purchase:**
"aaj ki sale"
"is mahine ka purchase"
"kal ki sale"

💰 **Financial:**
"profit kitna hai"
"cash balance"
"expenses"

📦 **Inventory:**
"low stock products"
"total stock value"

👥 **People:**
"top customers"
"vendors ki list"
"employees"

📋 **Operations:**
"mere tasks"
"kpi status"
"ai insights"

💡 **Tips:**
- Simple likhein
- Ya mic button 🎤 dabayein
- Roman Urdu bhi chalega!"""
    
    def who_are_you_response(self):
        return """Main hoon **Business Assistant** 🤖

Aapka personal AI assistant jo:
- 📊 Aapke business ke numbers jaanta hai
- 💡 Suggestions deta hai
- 🚨 Alerts dikhata hai
- 🎤 Voice mein jawaab deta hai

Bas poochein — main bata dunga! 😊"""
    
    # ========================================== #
    # SALES ANSWERS                              #
    # ========================================== #
    
    def get_sales_answer(self, question):
        today = localdate()
        
        # Today's sales
        if any(w in question for w in ['today', 'aaj', 'aaj ki']):
            sales = self.Sale.objects.filter(sale_date__date=today)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            
            # Top product today
            top = sales.values('saleitem__product__name').annotate(
                qty=Sum('saleitem__qty')
            ).order_by('-qty').first()
            
            top_str = f"\n🏆 Top: **{top['saleitem__product__name']}** ({top['qty']:.0f} units)" if top else ""
            
            return f"""📊 **Aaj ki Sales:**

💰 Total: **Rs. {total:,.2f}**
🛒 Orders: **{count}**{top_str}

Aur kuch jaanna hai? 😊"""
        
        # Yesterday
        if any(w in question for w in ['yesterday', 'kal']):
            yesterday = today - timedelta(days=1)
            sales = self.Sale.objects.filter(sale_date__date=yesterday)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            
            return f"""📊 **Kal ki Sales:**

💰 Total: **Rs. {total:,.2f}**
🛒 Orders: **{count}**"""
        
        # This week
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
        
        # This month
        if any(w in question for w in ['month', 'mahine', 'mahina', '30 days']):
            month_start = today.replace(day=1)
            sales = self.Sale.objects.filter(sale_date__date__gte=month_start)
            total = sales.aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
            count = sales.count()
            
            # Comparison with last month
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
        
        # Default - current month
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
        
        # Default
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
        
        # Determine period
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
        
        # Calculate
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
        
        # Gross profit (sale item profit)
        gross_profit = self.Sale.objects.filter(
            sale_date__date__gte=start_date
        ).aggregate(
            t=Sum('saleitem__profit')
        )['t'] or Decimal('0')
        
        gross_profit = gross_profit - discount_total
        
        net_profit = sales_total - purchases_total - expenses_total
        
        margin = (net_profit / sales_total * 100) if sales_total > 0 else 0
        
        # Status
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
        # Low stock
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
            return "✅ **Sab products ka stock theek hai!** 🎉"
        
        # Out of stock
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

🚨 **Urgent:** Inhe abhi order karein!"""
            return "✅ **Koi product out of stock nahi!**"
        
        # Total value
        if any(w in question for w in ['value', 'worth', 'total']):
            total_value = Decimal('0')
            for inv in self.Inventory.objects.all():
                total_value += inv.stock_value()
            
            return f"""💰 **Total Stock Value:**

📦 **Rs. {total_value:,.2f}**"""
        
        # Default - Summary
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
        
        # Top customers
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
        
        # Outstanding
        if any(w in question for w in ['outstanding', 'baqaya', 'udhar']):
            outstanding_list = []
            total_out = Decimal('0')
            
            for c in self.Customer.objects.all():
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
        
        # Outstanding
        if any(w in question for w in ['outstanding', 'baqaya', 'payable']):
            outstanding_list = []
            total_out = Decimal('0')
            
            for v in self.Vendor.objects.all():
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
        # Customer outstanding
        total_out = Decimal('0')
        count = 0
        
        for c in self.Customer.objects.all():
            bal = c.adjusted_outstanding_balance()
            if bal > 0:
                total_out += bal
                count += 1
        
        # Vendor payables
        total_pay = Decimal('0')
        v_count = 0
        
        for v in self.Vendor.objects.all():
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

💡 "customer outstanding" ya "vendor payables" poochein details ke liye"""
    
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

💡 "cash report" poochein detail ke liye"""
    
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
        
        # Top category
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
        # My tasks
        if any(w in question for w in ['my', 'mere', 'mera', 'my tasks']):
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
                    return "🎉 **Koi pending task nahi!**"
        
        # Overdue
        if any(w in question for w in ['overdue', 'late', 'der']):
            overdue = [t for t in self.OperationTask.objects.filter(
                status__in=['pending', 'in_progress']
            ) if t.is_overdue()]
            
            if overdue:
                items = "\n".join([
                    f"⚠️ **{t.title}** - Due: {t.due_date.strftime('%d %b')}"
                    for t in overdue[:5]
                ])
                return f"""🚨 **Overdue Tasks:**

{items}

Total: **{len(overdue)}**"""
            return "✅ **Koi overdue task nahi!**"
        
        # Default summary
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
            return "📋 **Koi active plan nahi hai**"
        
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
            return "📊 **Koi KPI set nahi hai**"
        
        on_track = kpis.filter(status='on_track').count()
        warning = kpis.filter(status='warning').count()
        critical = kpis.filter(status='critical').count()
        achieved = kpis.filter(status='achieved').count()
        
        # List critical
        critical_kpis = kpis.filter(status__in=['warning', 'critical'])[:3]
        critical_str = ""
        if critical_kpis:
            items = "\n".join([
                f"⚠️ **{k.name}**: {k.progress_percent:.0f}% ({k.current_value}/{k.target_value})"
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

Abhi koi insights nahi hain.

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
        from .models import OperationAlert, Notification
        
        # Operation alerts
        alerts = OperationAlert.objects.filter(is_resolved=False)[:5]
        
        # Notifications
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
        
        return f"""🔔 **Alerts Summary:**

📢 Unread Notifications: **{notifications.count() if hasattr(notifications, 'count') else len(notifications)}**
🚨 Active Alerts: **{alerts.count()}**{alert_str}"""
    
    # ========================================== #
    # INSTALLMENT ANSWERS                        #
    # ========================================== #
    
    def get_installment_answer(self, question):
        active = self.SaleInstallment.objects.filter(
            status__in=['pending', 'partial']
        )
        
        count = active.count()
        total_outstanding = sum(i.remaining_amount() for i in active)
        
        # Overdue
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
        
        # Total shares
        total_shares = self.Share.objects.aggregate(
            t=Sum('quantity')
        )['t'] or 0
        
        # Current price
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
        # Loans taken
        taken = self.Loan.objects.filter(status='active')
        taken_total = sum(l.remaining_amount for l in taken)
        
        # Loans given
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
        
        # Top products
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
        
        # Top customers
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
        
        # Sales
        sales = self.Sale.objects.filter(
            sale_date__date__gte=month_start
        ).aggregate(t=Sum('saleitem__total_amt'))['t'] or Decimal('0')
        
        # Purchases
        purchases = self.Purchase.objects.filter(
            pur_date__date__gte=month_start
        ).aggregate(t=Sum('purchaseitem__total_amt'))['t'] or Decimal('0')
        
        # Cash
        try:
            cash = self.CashBalance.get_balance()
        except:
            cash = Decimal('0')
        
        # Tasks
        pending_tasks = self.OperationTask.objects.filter(status='pending').count()
        
        # Low stock
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
        return f"""🤔 **Samajh nahi aaya:**

"{question}"

💡 **Yeh try karein:**
• "aaj ki sale"
• "profit kitna hai"
• "low stock products"
• "top customers"
• "mere tasks"
• "cash balance"
• "alerts"

Ya **help** likhein! 😊"""