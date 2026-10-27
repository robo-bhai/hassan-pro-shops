import unittest
from decimal import Decimal

from datetime import date

from app.ledger.posting_core import (D, C, clean_lines, check_balanced, next_balance, PostingError, q2, line_signature, prorate, paid_gap,
                              split_vendor_gap, party_key, split_party, bucket_for, statement_rows, age_open_items,
                              classify_cash_row, first_match, split_loan_return, payroll_amounts)


class PostingCoreTests(unittest.TestCase):
    def test_balanced_entry(self):
        lines = clean_lines([D('AR', 1000), C('Sales', 1000)])
        self.assertEqual(check_balanced(lines), Decimal('1000.00'))

    def test_unbalanced_entry_rejected(self):
        with self.assertRaises(PostingError):
            check_balanced(clean_lines([D('AR', 1000), C('Sales', 999.99)]))

    def test_split_entry_balances(self):
        lines = clean_lines([D('AR', 900), D('Discount', 100), C('Sales', 1000)])
        self.assertEqual(check_balanced(lines), Decimal('1000.00'))

    def test_zero_lines_dropped_and_minimum_two(self):
        with self.assertRaises(PostingError):
            clean_lines([D('AR', 0), C('Sales', 100)])

    def test_negative_rejected(self):
        with self.assertRaises(PostingError):
            clean_lines([D('AR', -5), C('Sales', -5)])

    def test_rounding_to_paisa(self):
        self.assertEqual(q2('10.005'), Decimal('10.01'))
        lines = clean_lines([D('A', '10.005'), C('B', '10.005')])
        check_balanced(lines)

    def test_running_balance_by_nature(self):
        # asset: debit increases
        self.assertEqual(next_balance(100, 50, 0, 'asset'), Decimal('150.00'))
        self.assertEqual(next_balance(100, 0, 30, 'asset'), Decimal('70.00'))
        # liability / income / equity: credit increases
        self.assertEqual(next_balance(100, 0, 50, 'liability'), Decimal('150.00'))
        self.assertEqual(next_balance(100, 20, 0, 'income'), Decimal('80.00'))
        # expense behaves like an asset
        self.assertEqual(next_balance(0, 75, 0, 'expense'), Decimal('75.00'))

    def test_full_sale_cycle_nets_to_zero_receivable(self):
        ar = Decimal('0.00')
        ar = next_balance(ar, 1000, 0, 'asset')      # invoice
        ar = next_balance(ar, 0, 400, 'asset')       # part payment
        ar = next_balance(ar, 0, 600, 'asset')       # rest
        self.assertEqual(ar, Decimal('0.00'))

    def test_signature_ignores_order_and_detects_change(self):
        a = clean_lines([D(1, 1000), C(2, 1000)])
        b = clean_lines([C(2, 1000), D(1, 1000)])
        c = clean_lines([D(1, 1200), C(2, 1200)])
        self.assertEqual(line_signature(a), line_signature(b))
        self.assertNotEqual(line_signature(a), line_signature(c))

    def test_signature_uses_pk_of_objects(self):
        class Acc:
            def __init__(self, pk): self.pk = pk
        a = clean_lines([D(Acc(7), 50), C(Acc(9), 50)])
        b = clean_lines([D(7, 50), C(9, 50)])
        self.assertEqual(line_signature(a), line_signature(b))


if __name__ == '__main__':
    unittest.main()


class ProrateTests(unittest.TestCase):
    def test_partial_return_takes_proportional_cost(self):
        self.assertEqual(prorate('600.00', 10, 4), Decimal('240.00'))

    def test_full_return_gives_back_whole_cost(self):
        self.assertEqual(prorate('333.33', 3, 3), Decimal('333.33'))

    def test_never_more_than_sold(self):
        self.assertEqual(prorate('100', 2, 5), Decimal('100.00'))

    def test_zero_or_missing_inputs(self):
        self.assertEqual(prorate(None, 5, 1), Decimal('0.00'))
        self.assertEqual(prorate('100', 0, 1), Decimal('0.00'))
        self.assertEqual(prorate('100', 5, 0), Decimal('0.00'))

    def test_cogs_entry_balances(self):
        cost = prorate('600', 10, 4)
        lines = clean_lines([D('Inventory', cost), C('COGS', cost)])
        self.assertEqual(check_balanced(lines), Decimal('240.00'))

    def test_sale_return_four_line_entry_balances(self):
        revenue, cost = Decimal('500.00'), prorate('300', 10, 5)
        lines = clean_lines([D('SalesReturns', revenue), C('AR', revenue), D('Inventory', cost), C('COGS', cost)])
        self.assertEqual(check_balanced(lines), Decimal('650.00'))


class PaidGapTests(unittest.TestCase):
    def test_down_payment_without_record(self):
        self.assertEqual(paid_gap([(5000, 0)]), Decimal('5000.00'))

    def test_fully_recorded_has_no_gap(self):
        self.assertEqual(paid_gap([(1000, 1000), (500, 500)]), Decimal('0.00'))

    def test_emi_receipts_do_not_hide_another_gap(self):
        # sale A: down payment 2000 never recorded, but EMI records add up to 3000 (more than 'paid')
        # sale B: paid 800 with no record
        self.assertEqual(paid_gap([(2000, 3000), (800, 0)]), Decimal('800.00'))

    def test_unlinked_ledger_payments_are_not_counted_twice(self):
        self.assertEqual(paid_gap([(1000, 0), (1000, 0)], unlinked=1500), Decimal('500.00'))
        self.assertEqual(paid_gap([(1000, 0)], unlinked=5000), Decimal('0.00'))

    def test_gap_entry_balances(self):
        gap = paid_gap([(750, 0)])
        self.assertEqual(check_balanced(clean_lines([D('Cash', gap), C('AR', gap)])), Decimal('750.00'))


class VendorSplitTests(unittest.TestCase):
    def test_cash_then_shareholder_then_other(self):
        # paid 1000: 400 cash, bill deducted from shareholders -> 600 shareholder
        self.assertEqual(split_vendor_gap([(1000, 0, 400, True)]), (Decimal('400.00'), Decimal('600.00'), Decimal('0.00')))

    def test_no_shareholder_rest_is_other(self):
        self.assertEqual(split_vendor_gap([(1000, 0, 400, False)]), (Decimal('400.00'), Decimal('0.00'), Decimal('600.00')))

    def test_recorded_part_is_removed_first(self):
        self.assertEqual(split_vendor_gap([(1000, 700, 400, False)]), (Decimal('300.00'), Decimal('0.00'), Decimal('0.00')))

    def test_unlinked_payment_reduces_other_first(self):
        self.assertEqual(split_vendor_gap([(1000, 0, 400, False)], unlinked=200), (Decimal('400.00'), Decimal('0.00'), Decimal('400.00')))

    def test_split_adds_up_to_gap(self):
        c, s, o = split_vendor_gap([(1000, 0, 400, True), (300, 100, 0, False)])
        self.assertEqual(c + s + o, Decimal('1200.00'))


class SubledgerCoreTests(unittest.TestCase):
    """Step 4: party on a line, statement running balance, ageing from the ledger."""

    def test_party_key_roundtrip(self):
        self.assertEqual(party_key('C', 12), 'C12')
        self.assertEqual(split_party('V3'), ('V', 3))
        self.assertEqual(party_key('C', None), '')
        self.assertEqual(split_party(''), (None, None))
        with self.assertRaises(PostingError):
            party_key('X', 1)

    def test_party_survives_clean_lines(self):
        lines = clean_lines([D('AR', 100, party='C1'), C('Sales', 100)])
        self.assertEqual([ln.party for ln in lines], ['C1', ''])

    def test_party_is_part_of_the_signature(self):
        a = line_signature([D('AR', 100, party='C1'), C('Sales', 100)])
        b = line_signature([D('AR', 100, party='C2'), C('Sales', 100)])
        c = line_signature([D('AR', 100, party='C1'), C('Sales', 100)])
        self.assertNotEqual(a, b)          # same amounts, other customer: must be re-posted
        self.assertEqual(a, c)

    def test_bucket_edges(self):
        self.assertEqual([bucket_for(d) for d in (0, 30, 31, 60, 61, 90, 91)],
                         ['0-30', '0-30', '31-60', '31-60', '61-90', '61-90', '91+'])

    def test_customer_statement_running_balance(self):
        rows = [(date(2026, 1, 1), 1000, 0), (date(2026, 1, 5), 0, 400), (date(2026, 1, 9), 250, 0)]
        out, closing = statement_rows(100, rows)
        self.assertEqual([r[-1] for r in out], [Decimal('1100.00'), Decimal('700.00'), Decimal('950.00')])
        self.assertEqual(closing, Decimal('950.00'))

    def test_vendor_statement_is_credit_nature(self):
        rows = [(date(2026, 1, 1), 0, 1000), (date(2026, 1, 5), 300, 0)]
        out, closing = statement_rows(0, rows, credit_nature=True)
        self.assertEqual([r[-1] for r in out], [Decimal('1000.00'), Decimal('700.00')])

    def test_aging_applies_payment_to_oldest_first(self):
        rows = [(date(2026, 7, 1), 1000, 0), (date(2026, 9, 1), 500, 0), (date(2026, 9, 20), 0, 1200)]
        buckets, advance = age_open_items(0, rows, date(2026, 10, 26))
        self.assertEqual(buckets['31-60'], Decimal('300.00'))      # what is left of the 1 Sep bill (55 days)
        self.assertEqual(sum(buckets.values()), Decimal('300.00'))
        self.assertEqual(advance, Decimal('0.00'))

    def test_aging_overpayment_is_an_advance_not_a_negative_bucket(self):
        buckets, advance = age_open_items(0, [(date(2026, 10, 1), 100, 0), (date(2026, 10, 2), 0, 160)], date(2026, 10, 26))
        self.assertEqual(sum(buckets.values()), Decimal('0.00'))
        self.assertEqual(advance, Decimal('60.00'))

    def test_aging_advance_covers_the_next_bill(self):
        rows = [(date(2026, 10, 1), 0, 100), (date(2026, 10, 5), 70, 0)]      # paid first, bought later
        buckets, advance = age_open_items(0, rows, date(2026, 10, 26))
        self.assertEqual(sum(buckets.values()), Decimal('0.00'))
        self.assertEqual(advance, Decimal('30.00'))

    def test_aging_vendor_uses_credit_as_the_charge(self):
        rows = [(date(2026, 6, 1), 0, 900), (date(2026, 10, 20), 400, 0)]     # we bought 900, paid 400 later
        buckets, advance = age_open_items(0, rows, date(2026, 10, 26), credit_nature=True)
        self.assertEqual(buckets['91+'], Decimal('500.00'))
        self.assertEqual(advance, Decimal('0.00'))

    def test_aging_opening_balance_is_the_oldest_charge(self):
        rows = [(date(2026, 10, 10), 0, 150)]
        buckets, advance = age_open_items(200, rows, date(2026, 10, 26))
        self.assertEqual(sum(buckets.values()), Decimal('50.00'))


class CashBookClassifyTests(unittest.TestCase):
    """Step 5: which cash-book rows are booked here, and against which account."""

    def test_rows_other_documents_book_are_skipped(self):
        self.assertIsNone(classify_cash_row('withdraw', 'Vendor payment: Ali Traders'))
        self.assertIsNone(classify_cash_row('withdraw', 'Vendor payment: Ali Traders - BILL-7'))
        self.assertIsNone(classify_cash_row('withdraw', 'Expense #EXP-12 - Rent'))
        for t in ('sale', 'purchase', 'expense', 'opening', 'transfer'):
            self.assertIsNone(classify_cash_row(t, 'anything'))

    def test_shareholder_money(self):
        self.assertEqual(classify_cash_row('deposit', 'Share investment from Ahmed - 10 shares @ Rs. 100.00'), 'share_capital')
        self.assertEqual(classify_cash_row('deposit', 'Additional investment from Ahmed - +5 shares (Main Cash)'), 'share_capital')
        self.assertEqual(classify_cash_row('deposit', 'Share purchase by Ahmed - 3 shares @ Rs. 50.00'), 'share_capital')
        self.assertEqual(classify_cash_row('deposit', 'Deposit from Ahmed - Request #R-5'), 'shareholder_funds')
        self.assertEqual(classify_cash_row('withdraw', 'Withdrawal to Ahmed - Request #R-6'), 'shareholder_funds')
        self.assertEqual(classify_cash_row('withdraw', 'Shareholder withdrawal: Ahmed - cash out'), 'shareholder_funds')
        self.assertEqual(classify_cash_row('withdraw', 'Refund to Ahmed - share decrease'), 'share_capital')
        self.assertEqual(classify_cash_row('withdraw', 'Transfer cancellation from Bilal - #T-1'), 'share_capital')

    def test_dividends(self):
        self.assertEqual(classify_cash_row('withdraw', 'Dividend Payment #D-3 to Ahmed'), 'dividends')
        self.assertEqual(classify_cash_row('withdraw', 'Dividend allocation - Admin - D-3'), 'dividends')
        self.assertEqual(classify_cash_row('withdraw', 'Balance Dividend withdrawal by Ahmed - #D-3'), 'dividends')
        self.assertEqual(classify_cash_row('deposit', 'Dividend refund from Ahmed - #D-3'), 'dividends')

    def test_loans(self):
        self.assertEqual(classify_cash_row('deposit', 'Loan Received: LN-1 - Bank Alfalah - Stock'), 'loans_payable')
        self.assertEqual(classify_cash_row('withdraw', 'Loan Return #LR-2 - Bank Alfalah - Loan repayment'), 'loan_return')
        self.assertEqual(classify_cash_row('withdraw', 'Loan Given to Usman - LG-4'), 'loans_receivable')
        self.assertEqual(classify_cash_row('deposit', 'Loan repayment from Usman - LG-4'), 'loans_receivable')

    def test_manual_cash_screens(self):
        self.assertEqual(classify_cash_row('withdraw', '[Personal Use] groceries'), 'owner_drawings')
        self.assertEqual(classify_cash_row('withdraw', '[Rent Payment] shop rent'), 'expense_default')
        self.assertEqual(classify_cash_row('withdraw', '[Other] something'), 'suspense')
        self.assertEqual(classify_cash_row('deposit', 'investment - owner added cash'), 'owner_capital')
        self.assertEqual(classify_cash_row('deposit', 'other - not sure'), 'suspense')

    def test_refund_and_emergency_fund(self):
        self.assertEqual(classify_cash_row('withdraw', 'Void refund B-100 - Walk-in Customer'), 'customer_refund')
        self.assertEqual(first_match(r'^Void refund (.+?) - ', 'Void refund B-100 - Walk-in Customer'), 'B-100')
        self.assertEqual(classify_cash_row('withdraw', 'Emergency Fund: Reserve - monthly'), 'emergency_fund')
        self.assertEqual(classify_cash_row('deposit', 'Emergency Withdrawal: Reserve - repairs'), 'emergency_fund')

    def test_unknown_rows_go_to_suspense_never_vanish(self):
        self.assertEqual(classify_cash_row('deposit', 'Some new screen text'), 'suspense')
        self.assertEqual(classify_cash_row('withdraw', ''), 'suspense')
        self.assertEqual(classify_cash_row('withdraw', None), 'suspense')

    def test_loan_return_split(self):
        self.assertEqual(split_loan_return('1100', '1000'), (Decimal('1000.00'), Decimal('100.00')))
        self.assertEqual(split_loan_return('1000', '0'), (Decimal('1000.00'), Decimal('0.00')))
        self.assertEqual(split_loan_return('1000', '5000'), (Decimal('1000.00'), Decimal('0.00')))      # bad data: all principal
        p, i = split_loan_return('1100.50', '1000')
        lines = clean_lines([D('LoansPayable', p), D('Interest', i), C('Cash', '1100.50')])
        self.assertEqual(check_balanced(lines), Decimal('1100.50'))

    def test_cash_book_entries_balance(self):
        inflow = clean_lines([D('Cash', 5000), C('ShareCapital', 5000)])
        outflow = clean_lines([D('Dividends', 750), C('Cash', 750)])
        refund = clean_lines([D('Receivable', 300, party='C9'), C('Cash', 300)])
        for lines in (inflow, outflow, refund):
            check_balanced(lines)


class PayrollTests(unittest.TestCase):
    def test_plain_salary(self):
        expense, cash, tax, loan = payroll_amounts(50000, 0, 0, 0, 0)
        self.assertEqual((expense, cash, tax, loan), (Decimal('50000.00'), Decimal('50000.00'), Decimal('0.00'), Decimal('0.00')))

    def test_deductions(self):
        # earnings 60000, absence cut 2000, other cut 500, tax 3000, loan recovery 5000
        expense, cash, tax, loan = payroll_amounts(60000, 2000, 500, 3000, 5000)
        self.assertEqual(expense, Decimal('57500.00'))
        self.assertEqual(cash, Decimal('49500.00'))          # same as Payroll.net_salary(): 60000 - 10500
        self.assertEqual(cash, Decimal('60000.00') - Decimal('2000') - Decimal('500') - Decimal('3000') - Decimal('5000'))

    def test_salary_entry_balances(self):
        expense, cash, tax, loan = payroll_amounts(60000, 2000, 500, 3000, 5000)
        lines = clean_lines([D('Salaries', expense), C('Cash', cash), C('TaxPayable', tax), C('EmployeeLoans', loan)])
        self.assertEqual(check_balanced(lines), Decimal('57500.00'))

    def test_zero_tax_and_loan_lines_are_dropped(self):
        expense, cash, tax, loan = payroll_amounts(1000, 0, 0, 0, 0)
        lines = clean_lines([D('Salaries', expense), C('Cash', cash), C('TaxPayable', tax), C('EmployeeLoans', loan)])
        self.assertEqual(len(lines), 2)

    def test_deductions_bigger_than_earnings_rejected(self):
        with self.assertRaises(PostingError):
            payroll_amounts(1000, 0, 0, 800, 500)
        with self.assertRaises(PostingError):
            payroll_amounts(1000, 900, 200, 0, 0)



if __name__ == '__main__':
    unittest.main()
