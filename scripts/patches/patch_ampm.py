"""Shows times as AM/PM (e.g. 03:45 PM) in POS, shift, stock register and dashboard pages.
CSV exports keep 24-hour time on purpose (easy to sort in Excel). Safe to run twice."""
import os, re

PY = ['app/views_frontend/pos.py', 'app/views_frontend/shift.py', 'app/views_frontend/shop_tools.py',
      'app/views_frontend/dashboard_extras.py']
HTML = ['templates/index.html', 'templates/sales/stock_register.html', 'templates/sales/shift_close.html',
        'templates/sales/shift_list.html', 'templates/sales/shift_report.html']
changed = 0
for p in PY:
    if not os.path.exists(p):
        print('skip (not found):', p); continue
    s = open(p, encoding='utf-8').read()
    out = []
    for line in s.split('\n'):
        if '%H:%M' in line and '%Y-%m-%d' not in line:      # keep CSV lines as they are
            line = line.replace('%H:%M', '%I:%M %p')
        out.append(line)
    n = '\n'.join(out)
    if n != s:
        if not os.path.exists(p + '.bak_ampm'): open(p + '.bak_ampm', 'w', encoding='utf-8').write(s)
        open(p, 'w', encoding='utf-8').write(n); changed += 1; print('updated', p)
for p in HTML:
    if not os.path.exists(p):
        print('skip (not found):', p); continue
    s = open(p, encoding='utf-8').read()
    n = re.sub(r'(\|date:"[^"]*?)H:i(:s)?', lambda m: m.group(1) + 'h:i' + (m.group(2) or '') + ' A', s)
    if n != s:
        if not os.path.exists(p + '.bak_ampm'): open(p + '.bak_ampm', 'w', encoding='utf-8').write(s)
        open(p, 'w', encoding='utf-8').write(n); changed += 1; print('updated', p)
print('done,', changed, 'file(s) changed')
