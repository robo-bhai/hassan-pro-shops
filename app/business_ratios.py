"""
Business Ratios Calculator
Professional CFO-Level Financial Analysis
35+ Business Ratios + DuPont Analysis
"""

from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Sum, Avg, Count, Q, F
from django.utils.timezone import now, localdate
import logging

logger = logging.getLogger(__name__)


class BusinessRatios:
    """
    Calculate 35+ Business Ratios for CFO-Level Analysis
    Including DuPont Analysis
    """
    
    def __init__(self):
        from .models import (
            Sale, Purchase, Expense, Customer, Vendor,
            Inventory, CashBalance, CashTransaction,
            SaleItem, PurchaseItem, Product, Loan,
            LoanGiven, Shareholder
        )
        
        self.today = localdate()
        self.Sale = Sale
        self.Purchase = Purchase
        self.Expense = Expense
        self.Customer = Customer
        self.Vendor = Vendor
        self.Inventory = Inventory
        self.CashBalance = CashBalance
        self.CashTransaction = CashTransaction
        self.SaleItem = SaleItem
        self.PurchaseItem = PurchaseItem
        self.Product = Product
        self.Loan = Loan
        self.LoanGiven = LoanGiven
        self.Shareholder = Shareholder
    
    # ==========================================
    # MAIN METHOD — Get All Ratios
    # ==========================================
    
    def get_all_ratios(self, from_date=None, to_date=None):
        """Get all 35+ ratios"""
        
        if not from_date:
            from_date = self.today - timedelta(days=365)
        if not to_date:
            to_date = self.today
        
        return {
            'period': {
                'from': from_date.strftime('%d-%b-%Y'),
                'to': to_date.strftime('%d-%b-%Y'),
                'days': (to_date - from_date).days,
            },
            'dupont': self.dupont_analysis(from_date, to_date),
            'liquidity': self.liquidity_ratios(),
            'profitability': self.profitability_ratios(from_date, to_date),
            'efficiency': self.efficiency_ratios(from_date, to_date),
            'leverage': self.leverage_ratios(),
            'cash_flow': self.cash_flow_ratios(from_date, to_date),
            'business_health': self.business_health_ratios(from_date, to_date),
            'summary': self.get_summary_score(from_date, to_date),
        }
    
    # ==========================================
    # 1. LIQUIDITY RATIOS
    # ==========================================
    
    def liquidity_ratios(self):
        """Calculate liquidity ratios"""
        
        # Current Assets
        cash = Decimal(str(self.CashBalance.get_balance()))
        
        # Inventory Value
        inventory_value = Decimal('0')
        for inv in self.Inventory.objects.all():
            inventory_value += inv.stock_value()
        
        # Receivables
        receivables = Decimal('0')
        for cust in self.Customer.objects.all():
            bal = cust.adjusted_outstanding_balance()
            if bal > 0:
                receivables += bal
        
        # Payables
        payables = Decimal('0')
        for vend in self.Vendor.objects.all():
            bal = vend.outstanding_balance()
            if bal > 0:
                payables += bal
        
        current_assets = cash + inventory_value + receivables
        current_liabilities = payables if payables > 0 else Decimal('1')
        
        # Ratios - Convert to float for safety
        current_ratio = float(current_assets) / float(current_liabilities)
        quick_ratio = (float(cash) + float(receivables)) / float(current_liabilities)
        cash_ratio = float(cash) / float(current_liabilities) if float(current_liabilities) > 0 else 0
        working_capital = float(current_assets) - float(payables)
        
        return {
            'current_ratio': {
                'value': round(current_ratio, 2),
                'formula': 'Current Assets / Current Liabilities',
                'benchmark': '> 2.0 is excellent',
                'status': self._get_status(current_ratio, 'higher', 2.0, 1.2),
                'details': {
                    'current_assets': float(current_assets),
                    'current_liabilities': float(payables),
                }
            },
            'quick_ratio': {
                'value': round(quick_ratio, 2),
                'formula': '(Cash + Receivables) / Payables',
                'benchmark': '> 1.5 is excellent',
                'status': self._get_status(quick_ratio, 'higher', 1.5, 1.0),
            },
            'cash_ratio': {
                'value': round(cash_ratio, 2),
                'formula': 'Cash / Payables',
                'benchmark': '> 0.5 is good',
                'status': self._get_status(cash_ratio, 'higher', 0.5, 0.2),
            },
            'working_capital': {
                'value': round(working_capital, 2),
                'formula': 'Current Assets - Liabilities',
                'benchmark': 'Positive is good',
                'status': 'success' if working_capital > 0 else 'danger',
            },
            'current_assets': float(current_assets),
            'current_liabilities': float(payables),
            'breakdown': {
                'cash': float(cash),
                'inventory': float(inventory_value),
                'receivables': float(receivables),
                'payables': float(payables),
            }
        }
    
    # ==========================================
    # 2. PROFITABILITY RATIOS
    # ==========================================
    
    def profitability_ratios(self, from_date, to_date):
        """Calculate profitability ratios"""
        
        # Sales
        sales_qs = self.Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        )
        total_sales = sales_qs.aggregate(
            total=Sum('saleitem__total_amt')
        )['total'] or Decimal('0')
        
        # COGS (Purchases)
        purchases_qs = self.Purchase.objects.filter(
            pur_date__date__gte=from_date,
            pur_date__date__lte=to_date
        )
        total_purchases = purchases_qs.aggregate(
            total=Sum('purchaseitem__total_amt')
        )['total'] or Decimal('0')
        
        # Expenses
        total_expenses = self.Expense.objects.filter(
            expense_date__gte=from_date,
            expense_date__lte=to_date,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Profit
        gross_profit = total_sales - total_purchases
        net_profit = gross_profit - total_expenses
        operating_profit = total_sales - total_expenses
        
        # Safety
        sales_safe = float(total_sales) if float(total_sales) > 0 else 1
        
        # Ratios - All as float
        gross_margin = (float(gross_profit) / sales_safe) * 100
        net_margin = (float(net_profit) / sales_safe) * 100
        operating_margin = (float(operating_profit) / sales_safe) * 100
        expense_ratio = (float(total_expenses) / sales_safe) * 100
        
        # Assets (for ROA)
        total_assets = Decimal(str(self.CashBalance.get_balance()))
        for inv in self.Inventory.objects.all():
            total_assets += inv.stock_value()
        
        assets_safe = float(total_assets) if float(total_assets) > 0 else 1
        
        roa = (float(net_profit) / assets_safe) * 100
        
        # ROI
        roi = (float(net_profit) / float(total_purchases) * 100) if float(total_purchases) > 0 else 0
        
        return {
            'gross_profit_margin': {
                'value': round(gross_margin, 2),
                'formula': '(Sales - COGS) / Sales x 100',
                'benchmark': '> 20% is excellent',
                'status': self._get_status(gross_margin, 'higher', 20, 10),
                'unit': '%',
            },
            'net_profit_margin': {
                'value': round(net_margin, 2),
                'formula': 'Net Profit / Sales x 100',
                'benchmark': '> 15% is excellent',
                'status': self._get_status(net_margin, 'higher', 15, 5),
                'unit': '%',
            },
            'operating_margin': {
                'value': round(operating_margin, 2),
                'formula': 'Operating Profit / Sales x 100',
                'benchmark': '> 12% is good',
                'status': self._get_status(operating_margin, 'higher', 12, 5),
                'unit': '%',
            },
            'expense_ratio': {
                'value': round(expense_ratio, 2),
                'formula': 'Expenses / Sales x 100',
                'benchmark': '< 30% is excellent',
                'status': self._get_status(expense_ratio, 'lower', 30, 50),
                'unit': '%',
            },
            'roa': {
                'value': round(roa, 2),
                'formula': 'Net Profit / Total Assets x 100',
                'benchmark': '> 15% is excellent',
                'status': self._get_status(roa, 'higher', 15, 8),
                'unit': '%',
            },
            'roi': {
                'value': round(roi, 2),
                'formula': 'Net Profit / Investment x 100',
                'benchmark': '> 20% is excellent',
                'status': self._get_status(roi, 'higher', 20, 10),
                'unit': '%',
            },
            'amounts': {
                'total_sales': float(total_sales),
                'total_purchases': float(total_purchases),
                'total_expenses': float(total_expenses),
                'gross_profit': float(gross_profit),
                'net_profit': float(net_profit),
            }
        }
    
    # ==========================================
    # 3. EFFICIENCY RATIOS
    # ==========================================
    
    def efficiency_ratios(self, from_date, to_date):
        """Calculate efficiency ratios"""
        
        days_period = (to_date - from_date).days
        if days_period <= 0:
            days_period = 365
        
        # Purchases (COGS)
        total_purchases = self.Purchase.objects.filter(
            pur_date__date__gte=from_date,
            pur_date__date__lte=to_date
        ).aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0')
        
        # Sales
        total_sales = self.Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        # Average Inventory
        total_inventory = Decimal('0')
        for inv in self.Inventory.objects.all():
            total_inventory += inv.stock_value()
        
        # Receivables
        receivables = Decimal('0')
        for cust in self.Customer.objects.all():
            bal = cust.adjusted_outstanding_balance()
            if bal > 0:
                receivables += bal
        
        # Payables
        payables = Decimal('0')
        for vend in self.Vendor.objects.all():
            bal = vend.outstanding_balance()
            if bal > 0:
                payables += bal
        
        # All as floats
        purchases_f = float(total_purchases)
        sales_f = float(total_sales)
        inventory_f = float(total_inventory)
        receivables_f = float(receivables)
        payables_f = float(payables)
        
        # Ratios
        if inventory_f > 0:
            inventory_turnover = purchases_f / inventory_f
            dio = (inventory_f / purchases_f) * days_period if purchases_f > 0 else 0
        else:
            inventory_turnover = 0
            dio = 0
        
        if receivables_f > 0 and sales_f > 0:
            receivable_turnover = sales_f / receivables_f
            dso = (receivables_f / sales_f) * days_period
        else:
            receivable_turnover = 0
            dso = 0
        
        if payables_f > 0 and purchases_f > 0:
            payable_turnover = purchases_f / payables_f
            dpo = (payables_f / purchases_f) * days_period
        else:
            payable_turnover = 0
            dpo = 0
        
        # Cash Conversion Cycle
        ccc = dio + dso - dpo
        
        return {
            'inventory_turnover': {
                'value': round(inventory_turnover, 2),
                'formula': 'COGS / Average Inventory',
                'benchmark': '> 4 is excellent',
                'status': self._get_status(inventory_turnover, 'higher', 4, 2),
            },
            'dio': {
                'value': round(dio, 1),
                'formula': '(Inventory / COGS) x Days',
                'benchmark': '< 60 days is good',
                'status': self._get_status(dio, 'lower', 60, 120),
                'unit': 'days',
            },
            'receivable_turnover': {
                'value': round(receivable_turnover, 2),
                'formula': 'Sales / Receivables',
                'benchmark': '> 6 is excellent',
                'status': self._get_status(receivable_turnover, 'higher', 6, 3),
            },
            'dso': {
                'value': round(dso, 1),
                'formula': '(Receivables / Sales) x Days',
                'benchmark': '< 45 days is excellent',
                'status': self._get_status(dso, 'lower', 45, 90),
                'unit': 'days',
            },
            'payable_turnover': {
                'value': round(payable_turnover, 2),
                'formula': 'Purchases / Payables',
                'benchmark': '5-10 is good',
                'status': self._get_status(payable_turnover, 'between', 10, 5),
            },
            'dpo': {
                'value': round(dpo, 1),
                'formula': '(Payables / Purchases) x Days',
                'benchmark': '> 30 days is good',
                'status': self._get_status(dpo, 'higher', 30, 15),
                'unit': 'days',
            },
            'cash_conversion_cycle': {
                'value': round(ccc, 1),
                'formula': 'DIO + DSO - DPO',
                'benchmark': '< 30 days is excellent',
                'status': self._get_status(ccc, 'lower', 30, 60),
                'unit': 'days',
            },
        }
    
    # ==========================================
    # 4. LEVERAGE RATIOS
    # ==========================================
    
    def leverage_ratios(self):
        """Calculate leverage/solvency ratios"""
        
        # Loans Taken (Liabilities)
        total_loans = self.Loan.objects.filter(
            status='active'
        ).aggregate(total=Sum('remaining_amount'))['total'] or Decimal('0')
        
        # Equity (Shareholders Investment)
        total_equity = Decimal('0')
        for sh in self.Shareholder.objects.filter(status='active'):
            total_equity += sh.total_investment()
        
        # Assets
        total_assets = Decimal(str(self.CashBalance.get_balance()))
        for inv in self.Inventory.objects.all():
            total_assets += inv.stock_value()
        
        for cust in self.Customer.objects.all():
            bal = cust.adjusted_outstanding_balance()
            if bal > 0:
                total_assets += bal
        
        # All as floats
        loans_f = float(total_loans)
        equity_f = float(total_equity) if float(total_equity) > 0 else 1
        assets_f = float(total_assets) if float(total_assets) > 0 else 1
        
        # Ratios
        debt_to_equity = loans_f / equity_f
        debt_to_assets = (loans_f / assets_f) * 100
        equity_ratio = (equity_f / assets_f) * 100
        debt_ratio = (loans_f / assets_f) * 100
        
        return {
            'debt_to_equity': {
                'value': round(debt_to_equity, 2),
                'formula': 'Total Debt / Equity',
                'benchmark': '< 0.5 is excellent',
                'status': self._get_status(debt_to_equity, 'lower', 0.5, 1.0),
            },
            'debt_to_assets': {
                'value': round(debt_to_assets, 2),
                'formula': '(Total Debt / Total Assets) x 100',
                'benchmark': '< 40% is excellent',
                'status': self._get_status(debt_to_assets, 'lower', 40, 60),
                'unit': '%',
            },
            'equity_ratio': {
                'value': round(equity_ratio, 2),
                'formula': '(Equity / Total Assets) x 100',
                'benchmark': '> 60% is excellent',
                'status': self._get_status(equity_ratio, 'higher', 60, 40),
                'unit': '%',
            },
            'debt_ratio': {
                'value': round(debt_ratio, 2),
                'formula': '(Liabilities / Total Assets) x 100',
                'benchmark': '< 40% is excellent',
                'status': self._get_status(debt_ratio, 'lower', 40, 60),
                'unit': '%',
            },
            'amounts': {
                'total_loans': float(total_loans),
                'total_equity': float(total_equity),
                'total_assets': float(total_assets),
            }
        }
    
    # ==========================================
    # 5. CASH FLOW RATIOS
    # ==========================================
    
    def cash_flow_ratios(self, from_date, to_date):
        """Calculate cash flow ratios"""
        
        days_period = (to_date - from_date).days
        if days_period <= 0:
            days_period = 30
        
        # Cash Inflow
        cash_in = self.CashTransaction.objects.filter(
            date__date__gte=from_date,
            date__date__lte=to_date,
            transaction_type__in=['deposit', 'sale', 'opening']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Cash Outflow
        cash_out = self.CashTransaction.objects.filter(
            date__date__gte=from_date,
            date__date__lte=to_date,
            transaction_type__in=['withdraw', 'purchase', 'expense']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # All as floats
        cash_in_f = float(cash_in)
        cash_out_f = float(cash_out)
        
        # Operating Cash Flow
        operating_cf = cash_in_f - cash_out_f
        
        # Monthly Burn Rate
        monthly_burn = cash_out_f / (days_period / 30) if days_period > 0 else cash_out_f
        
        # Current Cash
        current_cash_f = float(self.CashBalance.get_balance())
        
        # Cash Runway
        if monthly_burn > 0:
            cash_runway = current_cash_f / monthly_burn
        else:
            cash_runway = 999
        
        # Sales
        total_sales = self.Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        sales_f = float(total_sales) if float(total_sales) > 0 else 1
        
        # Ratios
        cash_flow_margin = (operating_cf / sales_f) * 100
        free_cash_flow = operating_cf
        
        return {
            'operating_cash_flow': {
                'value': round(operating_cf, 2),
                'formula': 'Cash In - Cash Out',
                'benchmark': 'Positive is good',
                'status': 'success' if operating_cf > 0 else 'danger',
                'unit': 'Rs.',
            },
            'cash_flow_margin': {
                'value': round(cash_flow_margin, 2),
                'formula': 'Operating CF / Sales x 100',
                'benchmark': '> 10% is excellent',
                'status': self._get_status(cash_flow_margin, 'higher', 10, 5),
                'unit': '%',
            },
            'monthly_burn_rate': {
                'value': round(monthly_burn, 2),
                'formula': 'Monthly Cash Outflow',
                'benchmark': 'Track karo',
                'status': 'info',
                'unit': 'Rs./month',
            },
            'cash_runway': {
                'value': round(cash_runway, 1),
                'formula': 'Current Cash / Monthly Burn',
                'benchmark': '> 6 months is excellent',
                'status': self._get_status(cash_runway, 'higher', 6, 3),
                'unit': 'months',
            },
            'free_cash_flow': {
                'value': round(free_cash_flow, 2),
                'formula': 'Operating CF - CapEx',
                'benchmark': 'Positive is good',
                'status': 'success' if free_cash_flow > 0 else 'warning',
                'unit': 'Rs.',
            },
            'amounts': {
                'cash_in': cash_in_f,
                'cash_out': cash_out_f,
                'current_cash': current_cash_f,
            }
        }
    
    # ==========================================
    # 6. BUSINESS HEALTH RATIOS
    # ==========================================
    
    def business_health_ratios(self, from_date, to_date):
        """Calculate business health ratios"""
        
        # Sales
        total_sales = self.Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        # Expenses
        total_expenses = self.Expense.objects.filter(
            expense_date__gte=from_date,
            expense_date__lte=to_date,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Purchases
        total_purchases = self.Purchase.objects.filter(
            pur_date__date__gte=from_date,
            pur_date__date__lte=to_date
        ).aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0')
        
        # Customer count
        customer_count = self.Customer.objects.count()
        
        # Total Sales Count
        sales_count = self.Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).count()
        
        # All as floats
        sales_f = float(total_sales)
        expenses_f = float(total_expenses)
        purchases_f = float(total_purchases)
        
        # Average Sale Value
        avg_sale = (sales_f / sales_count) if sales_count > 0 else 0
        
        # Customer Lifetime Value
        if customer_count > 0:
            customer_lifetime_value = sales_f / customer_count
        else:
            customer_lifetime_value = 0
        
        return {
            'break_even_sales': {
                'value': round(expenses_f + purchases_f, 2),
                'formula': 'Fixed + Variable Cost',
                'benchmark': 'Issay zyada sale par profit',
                'status': 'info',
                'unit': 'Rs.',
            },
            'average_sale_value': {
                'value': round(avg_sale, 2),
                'formula': 'Total Sales / Sales Count',
                'benchmark': 'Badhao',
                'status': self._get_status(avg_sale, 'higher', 5000, 2000),
                'unit': 'Rs.',
            },
            'customer_lifetime_value': {
                'value': round(customer_lifetime_value, 2),
                'formula': 'Total Sales / Customers',
                'benchmark': '> Rs. 10,000 is good',
                'status': self._get_status(customer_lifetime_value, 'higher', 10000, 5000),
                'unit': 'Rs.',
            },
            'customer_count': {
                'value': customer_count,
                'formula': 'Total Active Customers',
                'benchmark': 'Badhao',
                'status': 'info',
            },
            'sales_count': {
                'value': sales_count,
                'formula': 'Total Sales Count',
                'benchmark': 'Badhao',
                'status': 'info',
            },
        }
    
    # ==========================================
    # 7. DUPONT ANALYSIS
    # ==========================================
    
    def dupont_analysis(self, from_date, to_date):
        """
        DuPont Analysis - ROE ko 3 hisson mein todta hai
        
        ROE = Net Profit Margin × Asset Turnover × Equity Multiplier
        """
        
        # ==========================================
        # 1. Net Profit Margin (Profitability)
        # ==========================================
        total_sales = self.Sale.objects.filter(
            sale_date__date__gte=from_date,
            sale_date__date__lte=to_date
        ).aggregate(total=Sum('saleitem__total_amt'))['total'] or Decimal('0')
        
        total_purchases = self.Purchase.objects.filter(
            pur_date__date__gte=from_date,
            pur_date__date__lte=to_date
        ).aggregate(total=Sum('purchaseitem__total_amt'))['total'] or Decimal('0')
        
        total_expenses = self.Expense.objects.filter(
            expense_date__gte=from_date,
            expense_date__lte=to_date,
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        net_profit = total_sales - total_purchases - total_expenses
        
        sales_f = float(total_sales) if float(total_sales) > 0 else 1
        net_profit_f = float(net_profit)
        
        net_profit_margin = (net_profit_f / sales_f) * 100
        
        # ==========================================
        # 2. Asset Turnover (Efficiency)
        # ==========================================
        total_assets = Decimal(str(self.CashBalance.get_balance()))
        
        # Inventory
        for inv in self.Inventory.objects.all():
            total_assets += inv.stock_value()
        
        # Receivables
        for cust in self.Customer.objects.all():
            bal = cust.adjusted_outstanding_balance()
            if bal > 0:
                total_assets += bal
        
        assets_f = float(total_assets) if float(total_assets) > 0 else 1
        
        asset_turnover = sales_f / assets_f
        
        # ==========================================
        # 3. Equity Multiplier (Leverage)
        # ==========================================
        total_equity = Decimal('0')
        for sh in self.Shareholder.objects.filter(status='active'):
            total_equity += sh.total_investment()
        
        equity_f = float(total_equity) if float(total_equity) > 0 else 1
        
        equity_multiplier = assets_f / equity_f
        
        # ==========================================
        # ROE CALCULATION
        # ==========================================
        roe_direct = (net_profit_f / equity_f) * 100
        roe_dupont = (net_profit_margin / 100) * asset_turnover * equity_multiplier * 100
        
        # ==========================================
        # ANALYSIS
        # ==========================================
        drivers = {
            'profitability': net_profit_margin,
            'efficiency': asset_turnover * 100,
            'leverage': equity_multiplier * 100,
        }
        
        strongest = max(drivers, key=drivers.get)
        weakest = min(drivers, key=drivers.get)
        
        # Interpretations
        if net_profit_margin >= 15:
            margin_status = 'Excellent'
            margin_color = 'success'
        elif net_profit_margin >= 8:
            margin_status = 'Good'
            margin_color = 'info'
        elif net_profit_margin >= 3:
            margin_status = 'Moderate'
            margin_color = 'warning'
        else:
            margin_status = 'Poor'
            margin_color = 'danger'
        
        if asset_turnover >= 2:
            turnover_status = 'Excellent'
            turnover_color = 'success'
        elif asset_turnover >= 1:
            turnover_status = 'Good'
            turnover_color = 'info'
        elif asset_turnover >= 0.5:
            turnover_status = 'Moderate'
            turnover_color = 'warning'
        else:
            turnover_status = 'Poor'
            turnover_color = 'danger'
        
        if equity_multiplier <= 1.5:
            multiplier_status = 'Low Risk'
            multiplier_color = 'success'
        elif equity_multiplier <= 2.5:
            multiplier_status = 'Moderate'
            multiplier_color = 'info'
        elif equity_multiplier <= 4:
            multiplier_status = 'High Risk'
            multiplier_color = 'warning'
        else:
            multiplier_status = 'Very High Risk'
            multiplier_color = 'danger'
        
        if roe_direct >= 25:
            roe_status = 'Excellent'
            roe_color = 'success'
        elif roe_direct >= 15:
            roe_status = 'Good'
            roe_color = 'info'
        elif roe_direct >= 8:
            roe_status = 'Moderate'
            roe_color = 'warning'
        else:
            roe_status = 'Poor'
            roe_color = 'danger'
        
        # ==========================================
        # RECOMMENDATIONS
        # ==========================================
        recommendations = []
        
        if net_profit_margin < 10:
            recommendations.append({
                'icon': '💰',
                'title': 'Profit Margin Kam Hai',
                'message': f'Net margin {net_profit_margin:.1f}% hai. Price barhao ya expense kam karo.',
                'priority': 'high',
            })
        
        if asset_turnover < 1:
            recommendations.append({
                'icon': '⚙️',
                'title': 'Assets Ka Use Kam Hai',
                'message': f'Asset turnover {asset_turnover:.2f} hai. Stock aur receivables tez karo.',
                'priority': 'high',
            })
        
        if equity_multiplier > 3:
            recommendations.append({
                'icon': '⚠️',
                'title': 'Qarz Zyada Hai',
                'message': f'Equity multiplier {equity_multiplier:.2f} hai. Qarz kam karo.',
                'priority': 'high',
            })
        
        if roe_direct >= 20:
            recommendations.append({
                'icon': '✅',
                'title': 'ROE Excellent Hai!',
                'message': f'ROE {roe_direct:.1f}% hai. Isi tarah chalta raho.',
                'priority': 'info',
            })
        
        return {
            'net_profit_margin': {
                'value': round(net_profit_margin, 2),
                'formula': '(Net Profit / Sales) x 100',
                'description': 'Munafa kitna bach raha hai',
                'benchmark': '> 15% is excellent',
                'status': margin_color,
                'label': margin_status,
                'unit': '%',
            },
            'asset_turnover': {
                'value': round(asset_turnover, 2),
                'formula': 'Sales / Total Assets',
                'description': 'Assets kitne tez chal rahe hain',
                'benchmark': '> 2.0 is excellent',
                'status': turnover_color,
                'label': turnover_status,
                'unit': 'x',
            },
            'equity_multiplier': {
                'value': round(equity_multiplier, 2),
                'formula': 'Total Assets / Equity',
                'description': 'Qarz kitna hai',
                'benchmark': '< 1.5 is safe',
                'status': multiplier_color,
                'label': multiplier_status,
                'unit': 'x',
            },
            'roe': {
                'value': round(roe_direct, 2),
                'formula': 'Net Profit / Equity x 100',
                'dupont_formula': 'Margin × Turnover × Multiplier',
                'description': 'Shareholders ke paise par return',
                'benchmark': '> 25% is excellent',
                'status': roe_color,
                'label': roe_status,
                'unit': '%',
                'direct_value': round(roe_direct, 2),
                'dupont_value': round(roe_dupont, 2),
            },
            'drivers': {
                'strongest': strongest,
                'weakest': weakest,
                'profitability': round(net_profit_margin, 2),
                'efficiency': round(asset_turnover * 100, 2),
                'leverage': round(equity_multiplier * 100, 2),
            },
            'amounts': {
                'net_profit': round(net_profit_f, 2),
                'total_sales': round(sales_f, 2),
                'total_assets': round(assets_f, 2),
                'total_equity': round(equity_f, 2),
            },
            'recommendations': recommendations,
            'summary': self._get_dupont_summary(net_profit_margin, asset_turnover, equity_multiplier, roe_direct),
        }
    
    def _get_dupont_summary(self, margin, turnover, multiplier, roe):
        """DuPont ka aasan summary"""
        
        if roe >= 25:
            return {
                'title': '🟢 Excellent ROE',
                'message': f'ROE {roe:.1f}% hai — bohot acha! Profit margin {margin:.1f}%, Assets {turnover:.2f}x chal rahe, Qarz {multiplier:.2f}x.',
                'color': 'success',
            }
        elif roe >= 15:
            return {
                'title': '🟡 Good ROE',
                'message': f'ROE {roe:.1f}% hai — theek hai. Improve karo: margin {margin:.1f}% barhao.',
                'color': 'info',
            }
        elif roe >= 8:
            return {
                'title': '🟠 Moderate ROE',
                'message': f'ROE {roe:.1f}% hai — kam hai. Focus: profit margin aur asset turnover.',
                'color': 'warning',
            }
        else:
            return {
                'title': '🔴 Poor ROE',
                'message': f'ROE {roe:.1f}% hai — kaafi kam. Fauran improve karo: margin {margin:.1f}%, turnover {turnover:.2f}x, qarz {multiplier:.2f}x.',
                'color': 'danger',
            }
    
    # ==========================================
    # SUMMARY SCORE
    # ==========================================
    
    def get_summary_score(self, from_date, to_date):
        """Calculate overall business health score (0-100)"""
        
        liquidity = self.liquidity_ratios()
        profitability = self.profitability_ratios(from_date, to_date)
        efficiency = self.efficiency_ratios(from_date, to_date)
        leverage = self.leverage_ratios()
        cash_flow = self.cash_flow_ratios(from_date, to_date)
        
        scores = {
            'liquidity': self._score_ratios(liquidity),
            'profitability': self._score_ratios(profitability),
            'efficiency': self._score_ratios(efficiency),
            'leverage': self._score_ratios(leverage),
            'cash_flow': self._score_ratios(cash_flow),
        }
        
        overall = sum(scores.values()) / len(scores) if scores else 0
        
        return {
            'overall_score': round(overall, 1),
            'category_scores': scores,
            'rating': self._get_rating(overall),
            'color': self._get_rating_color(overall),
        }
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _get_status(self, value, direction, good, ok):
        """Get status color based on benchmark"""
        
        value = float(value)
        
        if direction == 'higher':
            if value >= good:
                return 'success'
            elif value >= ok:
                return 'warning'
            else:
                return 'danger'
        elif direction == 'lower':
            if value <= good:
                return 'success'
            elif value <= ok:
                return 'warning'
            else:
                return 'danger'
        elif direction == 'between':
            if ok <= value <= good:
                return 'success'
            else:
                return 'warning'
        
        return 'info'
    
    def _score_ratios(self, ratios_dict):
        """Score a category of ratios"""
        
        scores = []
        
        for key, value in ratios_dict.items():
            if isinstance(value, dict) and 'status' in value:
                status = value['status']
                if status == 'success':
                    scores.append(100)
                elif status == 'warning':
                    scores.append(60)
                elif status == 'danger':
                    scores.append(30)
                elif status == 'info':
                    scores.append(75)
        
        return round(sum(scores) / len(scores), 1) if scores else 0
    
    def _get_rating(self, score):
        """Get rating text"""
        if score >= 80:
            return '🟢 Excellent'
        elif score >= 65:
            return '🟡 Good'
        elif score >= 45:
            return '🟠 Moderate'
        else:
            return '🔴 Poor'
    
    def _get_rating_color(self, score):
        """Get rating color"""
        if score >= 80:
            return 'success'
        elif score >= 65:
            return 'info'
        elif score >= 45:
            return 'warning'
        else:
            return 'danger'