"""
python manage.py post_ledger --setup                  create starter accounts + mapping
python manage.py post_ledger --backfill [--since 2026-01-01] [--only sale,purchase] [--dry-run]
python manage.py post_ledger --backfill-cost [--dry-run]   save FIFO cost on old sale items (Step 3)
python manage.py post_ledger --opening-stock [--date YYYY-MM-DD] [--confirm]   book stock the ledger does not know (Step 3b)
python manage.py post_ledger --backfill-party [--dry-run]  name the customer / vendor on old receivable / payable lines (Step 4)
python manage.py post_ledger --check                  trial balance + ledger health check (incl. Step 5: cash book, loans, shareholders, payroll)
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import ExpressionWrapper, F, Sum

from app.ledger import posting
from app.ledger.posting_stock import inventory_figures, post_opening_stock
from django.db.models import DecimalField, Value
from django.db.models.functions import Coalesce

from app.models import (Account, CustomerPayment, GLPosting, JournalEntryItem, LedgerEntry, Payroll, PostingRule, Purchase,
                        Sale, SaleItem, SalePayment, StoreJournalLink, VendorPayment, CashTransaction)
from app.ledger.posting_core import PostingError, classify_cash_row, q2, next_balance

DATE_FIELD = {'sale': 'sale_date', 'sale_payment': 'payment_date', 'customer_payment': 'payment_date',
              'purchase': 'pur_date', 'vendor_payment': 'payment_date', 'expense': 'expense_date',
              'sale_cogs': 'sale_date', 'sale_return': 'sale_return_date',
              'purchase_return': 'purchase_return_date', 'stock_adjustment': 'adjustment_date', 'cash_opening': 'date',
              'cash_book': 'date'}
# documents whose date column is a plain date (no time), so the filter is `field__gte`, not `field__date__gte`
DATE_ONLY = {'expense': 'expense_date', 'payroll': 'month', 'daily_closing': 'closing_date'}
# purchases first (stock comes in), then sales and their cost, then returns and adjustments
ORDER = ['cash_opening', 'vendor_opening', 'purchase', 'vendor_payment', 'sale', 'sale_cogs', 'sale_payment', 'customer_payment', 'expense',
         'sale_return', 'purchase_return', 'stock_adjustment', 'customer_paid_gap', 'vendor_paid_gap',
         'cash_book', 'payroll', 'daily_closing']

# source type -> which party its receivable / payable line belongs to ('C' customer / 'V' vendor)
# and how to find the party id from the document: ('attr', 'customer_id') = a column of the document itself,
# ('via', 'sale', 'customer_id') = a column of the sale it belongs to, ('self',) = the document id IS the party id.
PARTY_OF = {
    'sale': ('C', ('attr', 'customer_id')), 'sale_return': ('C', ('attr', 'customer_id')),
    'customer_payment': ('C', ('attr', 'customer_id')), 'sale_payment': ('C', ('via', 'sale', 'customer_id')),
    'customer_paid_gap': ('C', ('self',)),
    'purchase': ('V', ('attr', 'vendor_id')), 'purchase_return': ('V', ('attr', 'vendor_id')),
    'vendor_payment': ('V', ('attr', 'vendor_id')), 'vendor_paid_gap': ('V', ('self',)), 'vendor_opening': ('V', ('self',)),
}


class Command(BaseCommand):
    help = 'Post business documents to the general ledger and check the books.'

    def add_arguments(self, p):
        p.add_argument('--setup', action='store_true')
        p.add_argument('--backfill', action='store_true')
        p.add_argument('--check', action='store_true')
        p.add_argument('--backfill-cost', action='store_true', dest='backfill_cost')
        p.add_argument('--opening-stock', action='store_true', dest='opening_stock')
        p.add_argument('--backfill-party', action='store_true', dest='backfill_party')
        p.add_argument('--date', help='YYYY-MM-DD for --opening-stock (default: day of the first ledger entry)')
        p.add_argument('--confirm', action='store_true')
        p.add_argument('--since', help='YYYY-MM-DD, only documents from this date')
        p.add_argument('--only', help='comma list: ' + ','.join(ORDER))
        p.add_argument('--dry-run', action='store_true')

    def handle(self, *a, **o):
        if not (o['setup'] or o['backfill'] or o['check'] or o['backfill_cost'] or o['opening_stock'] or o['backfill_party']):
            self.stdout.write('Use --setup, --backfill, --backfill-cost, --backfill-party, --opening-stock or --check.')
            return
        if o['setup']:
            made = posting.setup_defaults()
            self.stdout.write(self.style.SUCCESS('Mapping created:' if made else 'Mapping already complete.'))
            for m in made:
                self.stdout.write('  ' + m)
        if o['backfill_cost']:
            self.backfill_cost(o)
        if o['backfill']:
            self.backfill(o)
        if o['backfill_party']:
            self.backfill_party(o)
        if o['opening_stock']:
            self.opening_stock(o)
        if o['check']:
            self.check()

    # ---------------------------------------------------------------
    def backfill(self, o):
        only = [s.strip() for s in o['only'].split(',')] if o['only'] else ORDER
        for src in only:
            if src not in posting.SOURCES:
                self.stderr.write(f'Unknown source {src}')
                return
        done = 0
        for src in [s for s in ORDER if s in only]:
            model, _ = posting.SOURCES[src]
            qs = model.objects.exclude(pk__in=GLPosting.objects.filter(
                source_type=src, is_active=True).values('source_id'))
            if src == 'cash_book':                        # sales / purchases / opening rows are booked by their documents
                qs = qs.filter(transaction_type__in=['deposit', 'withdraw'])
            if o['since']:
                if src in DATE_ONLY:
                    qs = qs.filter(**{f'{DATE_ONLY[src]}__gte': o['since']})
                elif src in DATE_FIELD:
                    qs = qs.filter(**{f'{DATE_FIELD[src]}__date__gte': o['since']})
            total, ok, skipped, errors = qs.count(), 0, 0, []
            if o['dry_run']:
                if src == 'cash_book':                    # rows that a document already books are not counted
                    total = sum(1 for t in qs.only('transaction_type', 'description')
                                if classify_cash_row(t.transaction_type, t.description))
                self.stdout.write(f'{src:15} {total} not yet posted')
                continue
            for obj in qs.order_by('pk').iterator():
                try:
                    entry = posting.post_document(src, obj)
                    ok += 1 if entry else 0
                    skipped += 0 if entry else 1
                except PostingError as e:
                    errors.append(f'#{obj.pk}: {e}')
                    if 'not mapped' in str(e):
                        break
                except Exception as e:  # keep going, report at the end
                    errors.append(f'#{obj.pk}: {e}')
            done += ok
            self.stdout.write(f'{src:15} posted {ok}, nothing to post {skipped}, failed {len(errors)}')
            for err in errors[:5]:
                self.stderr.write('   ' + err)
        if not o['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Done. {done} entries posted.'))

    # ---------------------------------------------------------------
    def backfill_cost(self, o):
        """
        Old sale items have no saved cost. Work it out, using update() so no stock logic or signal runs:
          exact      profit was simply (amount - cost)                     -> cost = amount - profit
          estimated  batch had its own selling price (profit not derivable) -> average cost of the batches used x qty
          unknown    no batch information at all                           -> left empty, listed in --check
        """
        exact = est = unknown = 0
        for item in SaleItem.objects.filter(cost_amount__isnull=True).prefetch_related('batches_used').iterator():
            batches = list(item.batches_used.all())
            if batches and not any((b.selling_price or 0) > 0 for b in batches):
                cost, kind = max(q2(item.total_amt - item.profit), Decimal('0.00')), 'exact'
            elif batches:
                avg = sum((b.price for b in batches), Decimal('0')) / len(batches)
                cost, kind = q2(avg * Decimal(str(item.qty))), 'estimated'
            elif item.profit and item.total_amt:
                cost, kind = max(q2(item.total_amt - item.profit), Decimal('0.00')), 'exact'
            else:
                unknown += 1
                continue
            exact += kind == 'exact'
            est += kind == 'estimated'
            if not o['dry_run']:
                SaleItem.objects.filter(pk=item.pk).update(cost_amount=cost)
        tag = ' (dry run - nothing saved)' if o['dry_run'] else ''
        self.stdout.write(f'Sale item cost{tag}: exact {exact}, estimated {est}, still unknown {unknown}')
        if est:
            self.stdout.write('  estimated = the batch had its own selling price, so cost = average batch price x qty.')
        if not o['dry_run']:
            self.stdout.write('Now book it:  post_ledger --backfill --only sale_cogs')

    # ---------------------------------------------------------------
    def backfill_party(self, o):
        """
        Step 4: entries booked before the sub-ledger existed have no customer / vendor on their receivable / payable
        lines. Find the party from the document each entry was booked for and write it on the line and on its ledger
        row (amounts and balances are not touched). Reversal entries take the party of the entry they cancel.
        """
        from app.ledger import subledger
        from app.models import Customer, JournalEntry, Vendor
        from app.ledger.posting import party_fields
        from app.ledger.posting_core import party_key

        todo = {}                         # (kind) -> account
        for kind in ('customer', 'vendor'):
            acc = subledger.control_account(kind)
            if acc is None:
                self.stderr.write(f'The {subledger.KINDS[kind][2]} account is not mapped. Run --setup first.')
                return
            todo[kind] = acc

        # entry id -> (source_type, source_id); a reversal entry uses the entry it reverses
        link = {}
        for gp in GLPosting.objects.order_by('id').values_list('journal_entry_id', 'source_type', 'source_id'):
            link.setdefault(gp[0], (gp[1], gp[2]))
        reversal_of = dict(JournalEntry.objects.filter(reversed_from__isnull=False).values_list('pk', 'reversed_from_id'))

        # document id -> party id, one query per source type
        cache = {}

        def party_id(src, doc_id):
            if src not in PARTY_OF:
                return None
            kind, how = PARTY_OF[src]
            if how[0] == 'self':
                model = Customer if kind == 'C' else Vendor
                return doc_id if model.objects.filter(pk=doc_id).exists() else None
            if src not in cache:
                model = posting.SOURCES[src][0]
                if how[0] == 'attr':
                    cache[src] = dict(model.objects.values_list('pk', how[1]))
                else:
                    cache[src] = dict(model.objects.values_list('pk', f'{how[1]}__{how[2]}'))
            return cache[src].get(doc_id)

        stamped = skipped = 0
        for kind, acc in todo.items():
            code = 'C' if kind == 'customer' else 'V'
            items = JournalEntryItem.objects.filter(account=acc, customer__isnull=True, vendor__isnull=True)
            for item in items.iterator():
                entry_id = reversal_of.get(item.journal_entry_id, item.journal_entry_id)
                src = link.get(entry_id)
                pid = party_id(*src) if src and PARTY_OF.get(src[0], (None,))[0] == code else None
                if not pid:
                    skipped += 1
                    continue
                stamped += 1
                if o['dry_run']:
                    continue
                fields = party_fields(party_key(code, pid))
                JournalEntryItem.objects.filter(pk=item.pk).update(**fields)
                row = LedgerEntry.objects.filter(
                    journal_entry_id=item.journal_entry_id, account=acc, customer__isnull=True, vendor__isnull=True,
                    debit=item.amount if item.is_debit else 0, credit=0 if item.is_debit else item.amount,
                ).order_by('id').first()
                if row:
                    LedgerEntry.objects.filter(pk=row.pk).update(**fields)
        tag = ' (dry run - nothing saved)' if o['dry_run'] else ''
        self.stdout.write(f'Party on receivable / payable lines{tag}: named {stamped}, left without a party {skipped}')
        if skipped:
            self.stdout.write('  Left without a party = manual journal entries or entries whose document was deleted; see --check.')

    # ---------------------------------------------------------------
    def opening_stock(self, o):
        """Book the stock the ledger does not know about (opening stock). Shows the amount first; --confirm books it."""
        from datetime import date as _date
        from django.db.models import Min
        from app.models import JournalEntry
        if StoreJournalLink.objects.filter(doc_type='opening').exists():
            self.stderr.write('The store module already booked an opening stock entry (Store Settings). '
                              'Booking another one would count the stock twice.')
            return
        acc, ledger, value = inventory_figures()
        if acc is None:
            self.stderr.write('Inventory account is not mapped. Run --setup first.')
            return
        existing = GLPosting.objects.filter(source_type='opening_stock', is_active=True).first()
        done = existing.amount if existing else Decimal('0.00')
        diff = value - ledger
        self.stdout.write(f'Inventory in the ledger: Rs. {ledger:,}   Stock batches: Rs. {value:,}   Difference: Rs. {diff:,}')
        if diff <= 0:
            self.stdout.write('Ledger is not below the stock, nothing to book as opening stock.'
                              + (' (If it is ABOVE the stock, look for sales without cost or purchases that never reached the shelves.)' if diff < 0 else ''))
            return
        if o['date']:
            when = _date.fromisoformat(o['date'])
        else:
            first = JournalEntry.objects.exclude(gl_postings__source_type='opening_stock').aggregate(m=Min('entry_date'))['m']
            when = first or _date.today()
        total = done + diff
        self.stdout.write(f'Opening stock entry: Dr Inventory / Cr Opening Balance Equity  Rs. {total:,}  dated {when}'
                          + (f'  (replaces the earlier entry of Rs. {done:,})' if done else ''))
        if not o['confirm']:
            self.stdout.write('Nothing booked. Check the amount, then run again with --confirm.')
            return
        post_opening_stock(total, when)
        self.stdout.write(self.style.SUCCESS('Opening stock booked.'))

    # ---------------------------------------------------------------
    def check(self):
        items = JournalEntryItem.objects.filter(journal_entry__status__in=['posted', 'reversed'])
        dr = items.filter(is_debit=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        cr = items.filter(is_debit=False).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        self.stdout.write(f'Total debit  {q2(dr):>18,}')
        self.stdout.write(f'Total credit {q2(cr):>18,}')
        self.stdout.write((self.style.SUCCESS if dr == cr else self.style.ERROR)(
            'Books balance.' if dr == cr else f'OUT OF BALANCE by {q2(dr - cr):,}'))

        bad = 0
        self.stdout.write('\nAccount balances (from the ledger):')
        for acc in Account.objects.select_related('account_type').order_by('code'):
            rows = LedgerEntry.objects.filter(account=acc).order_by('date', 'id')
            if not rows.exists():
                continue
            running = q2(acc.opening_balance)
            for r in rows:
                running = next_balance(running, r.debit, r.credit, acc.account_type.account_class)
            last = rows.last().balance
            flag = '' if running == last else '   <-- running balance is stale'
            bad += 1 if flag else 0
            self.stdout.write(f'  {acc.code:10} {acc.name[:28]:28} {running:>16,}{flag}')
        self.stdout.write(self.style.SUCCESS('Ledger OK.') if not bad else self.style.ERROR(f'{bad} account(s) need a rebuild.'))
        self.reconcile()

    # ---------------------------------------------------------------
    def reconcile(self):
        """Compare the 'paid' totals on documents with the receipts/payments that reached the ledger."""
        zero = Value(Decimal('0'), output_field=DecimalField())
        def total(qs, field='amount'):
            return qs.aggregate(t=Coalesce(Sum(field), zero))['t']

        def posted(src):
            return GLPosting.objects.filter(source_type=src, is_active=True).count()

        self.stdout.write('\nDocuments vs ledger:')
        self.stdout.write(f"  sales posted {posted('sale')} of {Sale.objects.count()}, "
                          f"purchases posted {posted('purchase')} of {Purchase.objects.count()}")
        sale_gap = total(Sale.objects.all(), 'paid') - total(SalePayment.objects.all()) - total(CustomerPayment.objects.all())
        pur_gap = total(Purchase.objects.all(), 'paid') - total(VendorPayment.objects.all())
        for label, gap in (('Customer money not in any payment record (Sale.paid)', sale_gap),
                           ('Vendor money not in any payment record (Purchase.paid)', pur_gap)):
            style = self.style.SUCCESS if gap == 0 else self.style.WARNING
            self.stdout.write(style(f'  {label}: Rs. {q2(gap):,}'))
        booked_c = total(GLPosting.objects.filter(source_type='customer_paid_gap', is_active=True), 'amount')
        booked_v = total(GLPosting.objects.filter(source_type='vendor_paid_gap', is_active=True), 'amount')
        self.stdout.write(f'  Booked as "paid on the bill" entries (Step 2b): customers Rs. {q2(booked_c):,}, vendors Rs. {q2(booked_v):,}')
        if sale_gap or pur_gap:
            self.stdout.write('  (the gap lines above are the raw totals; the booked amounts are what the ledger already carries.\n'
                              '   Run --backfill --only customer_paid_gap,vendor_paid_gap if they are 0 and the gap is not.)')
        self.reconcile_stock()
        self.reconcile_cash()
        self.reconcile_subledger()
        self.reconcile_step5()

    # ---------------------------------------------------------------
    def reconcile_subledger(self):
        """Step 4 check: the customers' balances must add up to the Receivable account, the vendors' to Payable."""
        from app.ledger import subledger
        from app.models import Customer, Vendor

        self.stdout.write('\nCustomer / vendor sub-ledgers:')
        for kind, label, model in (('customer', 'Receivable', Customer), ('vendor', 'Payable', Vendor)):
            acc = subledger.control_account(kind)
            if acc is None:
                self.stdout.write(self.style.WARNING(f'  {label} account is not mapped (run --setup).'))
                continue
            credit_nature = subledger.KINDS[kind][3]
            agg = LedgerEntry.objects.filter(account=acc).aggregate(d=Sum('debit'), c=Sum('credit'))
            d, c = q2(agg['d'] or 0), q2(agg['c'] or 0)
            control = (c - d) if credit_nature else (d - c)      # movement in the ledger, same nature as the parties
            parties = subledger.party_balances(kind, include_reversed=True)
            total = q2(sum(parties.values(), Decimal('0')))
            missing = control - total
            if q2(acc.opening_balance):
                self.stdout.write(f'  (note: account {acc.code} also has an opening balance of Rs. {q2(acc.opening_balance):,} typed on the account; the parties below do not include it)')
            self.stdout.write(f'  {label} account {acc.code}: Rs. {control:,}   sum of {kind}s: Rs. {total:,}   without a {kind}: Rs. {q2(missing):,}')
            if q2(missing) == 0:
                self.stdout.write(self.style.SUCCESS(f'  Every rupee on {label} belongs to a {kind}.'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'  Rs. {q2(missing):,} on {label} names no {kind} (manual entries, or entries not yet named: run --backfill-party).'))

            # the old screens against the ledger, biggest difference first
            names = dict(model.objects.values_list('pk', 'name'))
            diffs = []
            for pid, ledger_bal in parties.items():
                obj = model.objects.filter(pk=pid).first()
                if obj is None:
                    continue
                old = q2(obj.outstanding_balance() if kind == 'vendor' else obj.adjusted_outstanding_balance())
                if old != ledger_bal:
                    diffs.append((abs(old - ledger_bal), pid, old, ledger_bal))
            diffs.sort(reverse=True)
            self.stdout.write(f'  {kind}s whose old screen balance differs from the ledger: {len(diffs)} of {len(parties)}')
            for _, pid, old, ledger_bal in diffs[:5]:
                self.stdout.write(f'     {names.get(pid, pid)[:30]:30} screen {old:>14,}   ledger {ledger_bal:>14,}')
            if diffs:
                self.stdout.write('     (a difference is a lead, not an error: discounts, returns and "paid" typed on the bill were handled\n'
                                  '      differently by the old screens. Check one party with its statement before changing anything.)')

    # ---------------------------------------------------------------
    def reconcile_cash(self):
        """The old cash book against the Cash in Hand account - a difference points at money still missing from the ledger."""
        from app.models import CashBalance
        rule = PostingRule.objects.select_related('account').filter(key='cash').first()
        if not rule:
            return
        acc = rule.account
        agg = LedgerEntry.objects.filter(account=acc).aggregate(d=Sum('debit'), c=Sum('credit'))
        ledger = q2(acc.opening_balance) + q2(agg['d'] or 0) - q2(agg['c'] or 0)
        book = q2(CashBalance.objects.first().balance if CashBalance.objects.exists() else 0)
        self.stdout.write('\nCash:')
        self.stdout.write(f'  Cash in Hand in the ledger ({acc.code}): Rs. {ledger:,}     old cash book: Rs. {book:,}')
        if ledger == book:
            self.stdout.write(self.style.SUCCESS('  Cash agrees.'))
        else:
            self.stdout.write(self.style.WARNING(f'  Difference: Rs. {ledger - book:,}'))
            self.stdout.write('  Usual reasons: the old cash book counts a new sale at its full amount and again when the customer pays,\n'
                              '  salaries are not in the old cash book at all, and bank / wallet money is not in this account.\n'
                              '  Rows still waiting to be booked are listed under "Step 5" below.')

    # ---------------------------------------------------------------
    def reconcile_stock(self):
        """Step 3 check: the Inventory account must agree with the real stock batches."""
        self.stdout.write('\nStock and cost:')
        no_cost = SaleItem.objects.filter(cost_amount__isnull=True).count()
        style = self.style.SUCCESS if no_cost == 0 else self.style.WARNING
        self.stdout.write(style(f'  Sale items without a saved cost: {no_cost}'
                                + ('' if no_cost == 0 else '   (run --backfill-cost, then --backfill --only sale_cogs)')))
        unposted = Sale.objects.filter(saleitem__cost_amount__gt=0).distinct().exclude(
            pk__in=GLPosting.objects.filter(source_type='sale_cogs', is_active=True).values('source_id')).count()
        self.stdout.write((self.style.SUCCESS if unposted == 0 else self.style.WARNING)(
            f'  Sales with cost but no cost entry yet: {unposted}'))

        acc, ledger, value = inventory_figures()
        if acc is None:
            self.stdout.write(self.style.WARNING("  Inventory account is not mapped (run --setup)."))
            return
        diff = ledger - value
        self.stdout.write(f'  Inventory in the ledger ({acc.code}):  Rs. {ledger:,}')
        self.stdout.write(f'  Stock batches (qty x cost):           Rs. {value:,}')
        if diff == 0:
            self.stdout.write(self.style.SUCCESS('  Inventory agrees with the stock.'))
        else:
            self.stdout.write(self.style.WARNING(f'  Difference: Rs. {diff:,}'))
            if diff < 0:
                self.stdout.write('  Stock is worth more than the ledger: run  --opening-stock  to see / book the opening stock.')
            else:
                self.stdout.write('  Ledger is above the stock: look for estimated old costs, sale returns that went back at the selling\n'
                                  '  price (before Step 3b), or sales whose stock was edited by hand.')

    # ---------------------------------------------------------------
    def reconcile_step5(self):
        """Step 5 check: cash-book rows, unclassified money, salaries, and the shareholder / loan accounts."""
        self.stdout.write('\nStep 5 - cash book, shareholders, loans, salaries:')
        booked = set(GLPosting.objects.filter(source_type='cash_book', is_active=True).values_list('source_id', flat=True))
        waiting, suspense_rows, suspense_net = 0, [], Decimal('0.00')
        for t in CashTransaction.objects.filter(transaction_type__in=['deposit', 'withdraw']).only(
                'id', 'transaction_type', 'description', 'amount', 'date').order_by('-amount').iterator():
            key = classify_cash_row(t.transaction_type, t.description)
            if key is None:
                continue
            if t.pk not in booked:
                waiting += 1
            if key == 'suspense':
                suspense_net += q2(t.amount) if t.transaction_type == 'deposit' else -q2(t.amount)
                if len(suspense_rows) < 5:
                    suspense_rows.append(t)
        self.stdout.write((self.style.SUCCESS if waiting == 0 else self.style.WARNING)(
            f'  Cash book rows not booked yet: {waiting}' + ('' if waiting == 0 else '   (run --backfill --only cash_book)')))

        rule = PostingRule.objects.select_related('account').filter(key='suspense').first()
        in_ledger = Decimal('0.00')
        if rule:
            agg = LedgerEntry.objects.filter(account=rule.account).aggregate(d=Sum('debit'), c=Sum('credit'))
            in_ledger = q2(agg['c'] or 0) - q2(agg['d'] or 0)
        self.stdout.write((self.style.SUCCESS if suspense_net == 0 else self.style.WARNING)(
            f'  Unclassified cash movements (net in): Rs. {q2(suspense_net):,}   in the ledger: Rs. {in_ledger:,}'))
        for t in suspense_rows:
            self.stdout.write(f'     {t.date:%d-%m-%Y} {t.transaction_type:8} {q2(t.amount):>14,}  {(t.description or "")[:60]}')
        if suspense_rows:
            self.stdout.write('     (move these to the right account with a journal entry, or word the cash screens so the rules recognise them)')

        paid = Payroll.objects.filter(status='paid')
        unposted = paid.exclude(pk__in=GLPosting.objects.filter(source_type='payroll', is_active=True).values('source_id')).count()
        self.stdout.write((self.style.SUCCESS if unposted == 0 else self.style.WARNING)(
            f'  Paid salaries not booked yet: {unposted} of {paid.count()}' + ('' if unposted == 0 else '   (run --backfill --only payroll)')))

        self.stdout.write('  Balances of the Step 5 accounts:')
        for key in ('share_capital', 'owner_capital', 'shareholder_funds', 'dividends', 'owner_drawings', 'loans_payable',
                    'loans_receivable', 'employee_loans', 'emergency_fund', 'salary_expense', 'interest_expense'):
            r = PostingRule.objects.select_related('account__account_type').filter(key=key).first()
            if not r:
                continue
            a = r.account
            agg = LedgerEntry.objects.filter(account=a).aggregate(d=Sum('debit'), c=Sum('credit'))
            bal = next_balance(a.opening_balance, agg['d'] or 0, agg['c'] or 0, a.account_type.account_class)
            if agg['d'] or agg['c']:
                self.stdout.write(f'     {a.code:8} {a.name[:30]:30} {bal:>16,}')
        self.stdout.write('  Note: the old screens move shareholder wallet money and main cash separately (a share bought from the wallet\n'
                          '  also adds cash, a "share buyback" is stored as a cash deposit). The ledger follows the cash book exactly, so\n'
                          '  Shareholder Funds / Share Capital can look odd; check them before relying on them.')
