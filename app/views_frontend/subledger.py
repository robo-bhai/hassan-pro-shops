"""Frontend views: customer / vendor statements and ageing taken from the general ledger (Step 4)."""
import csv
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .. import subledger as _sub
from ..models import CompanyInfo, Customer, Vendor
from ..posting_core import AGING_BUCKETS

_TITLES = {
    'customer': ('Customer Statement', 'Customer', 'They owe us'),
    'vendor': ('Vendor Statement', 'Vendor', 'We owe them'),
}


def _sl_company():
    info = CompanyInfo.objects.first()
    return info.name if info else 'ERP System'


def _sl_day(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default


def _sl_statement(request, kind, party):
    date_from = _sl_day(request.GET.get('date_from'))
    date_to = _sl_day(request.GET.get('date_to'))
    show_reversed = request.GET.get('show_reversed') == '1'
    st = _sub.party_statement(kind, party, date_from, date_to, include_reversed=show_reversed)

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="{kind}_statement_{party.pk}.csv"'
        w = csv.writer(resp)
        w.writerow([f'{_TITLES[kind][0]} - {party.name}'])
        w.writerow(['Date', 'Reference', 'Entry', 'Description', 'Debit', 'Credit', 'Balance'])
        w.writerow([date_from or '', 'Opening balance', '', '', '', '', st['opening']])
        for r in st['rows']:
            w.writerow([r['date'], r['reference'], r['entry'].entry_no, r['description'], r['debit'], r['credit'], r['balance']])
        w.writerow(['', 'Closing balance', '', '', st['total_debit'], st['total_credit'], st['closing']])
        return resp

    title, label, hint = _TITLES[kind]
    return render(request, 'reports/party_statement.html', {
        'company_name': _sl_company(), 'kind': kind, 'party': party, 'st': st, 'title': title, 'party_label': label,
        'balance_hint': hint, 'date_from': date_from, 'date_to': date_to, 'show_reversed': show_reversed,
        'today': date.today(),
    })


@login_required
def customer_statement(request, pk):
    """Customer statement from the ledger (Receivable account, this customer's lines)."""
    return _sl_statement(request, 'customer', get_object_or_404(Customer, pk=pk))


@login_required
def vendor_statement(request, pk):
    """Vendor statement from the ledger (Payable account, this vendor's lines)."""
    return _sl_statement(request, 'vendor', get_object_or_404(Vendor, pk=pk))


def _sl_aging(request, kind):
    as_of = _sl_day(request.GET.get('as_of'), date.today())
    only_overdue = request.GET.get('overdue') == '1'
    rep = _sub.aging_report(kind, as_of, only_overdue=only_overdue)
    label = 'Customer' if kind == 'customer' else 'Vendor'

    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="{kind}_aging_{as_of}.csv"'
        w = csv.writer(resp)
        w.writerow([f'{label} ageing from the ledger as of {as_of}'])
        w.writerow([label, 'Code', *AGING_BUCKETS, 'Total', 'Paid in advance'])
        for r in rep['rows']:
            p = r['party']
            code = getattr(p, 'customer_code', None) or getattr(p, 'vendor_code', '') if p else ''
            w.writerow([p.name if p else f'#{r["party_id"]}', code, *[r['buckets'][b] for b in AGING_BUCKETS], r['balance'], r['advance']])
        w.writerow(['Total', '', *[rep['totals'][b] for b in AGING_BUCKETS], rep['total'], rep['advance']])
        return resp

    # Django templates cannot read dict keys like '0-30', so hand them over as plain lists
    rep['totals_list'] = [rep['totals'][b] for b in AGING_BUCKETS]
    for r in rep['rows']:
        r['cells'] = [r['buckets'][b] for b in AGING_BUCKETS]

    return render(request, 'reports/gl_aging.html', {
        'company_name': _sl_company(), 'kind': kind, 'party_label': label, 'rep': rep, 'as_of': as_of,
        'only_overdue': only_overdue, 'buckets': AGING_BUCKETS,
        'title': 'Receivable Ageing (Ledger)' if kind == 'customer' else 'Payable Ageing (Ledger)',
    })


@login_required
def gl_receivable_aging(request):
    """Who owes us, by age - from the ledger, not from separate balances."""
    return _sl_aging(request, 'customer')


@login_required
def gl_payable_aging(request):
    """Whom we owe, by age - from the ledger, not from separate balances."""
    return _sl_aging(request, 'vendor')
