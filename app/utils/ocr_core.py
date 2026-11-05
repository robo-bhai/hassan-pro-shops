"""OCR product matching - pure Python, NO Django imports (so it can be unit-tested with plain python).

Used by app/views_frontend/pos_sales/ocr.py.  Matching behaviour is the same as the old ocr.py (v2);
this file only moves it out of the view and adds two small helpers for the learning loop:

    is_confident(top)            -> should the page add the first product automatically?
    alias_candidate(text, name)  -> a clean alias string worth remembering, or '' if not worth it
"""
import difflib
import re

# ---- tuning (raise AUTO_ADD_* if wrong products get added, lower them if too few are) ----
AUTO_ADD_MIN_SCORE = 78      # first match must score at least this ...
AUTO_ADD_MIN_GAP = 8         # ... and be this far ahead of the second one
MIN_LIST_SCORE = 45          # matches below this are not shown
PREFILTER_MIN = 0.25         # trigram share needed to enter the precise scoring
PREFILTER_TOP = 60           # how many candidates get the precise scoring
STOCK_BOOST = 3              # points added to products that have stock in the chosen warehouse (0 = off)
CANDIDATES = 10              # how many ranked products are looked at for stock before the top 5 are shown

# ---- alias learning ----
ALIAS_AUTO_HITS = 3          # same text -> same product confirmed this many times => becomes a ProductAlias
ALIAS_MIN_LETTERS = 6        # shorter texts are too vague to remember
ALIAS_MAX_LEN = 100          # ProductAlias.alias max_length

STOP_WORDS = {'the', 'and', 'for', 'with', 'new', 'pack', 'pcs', 'pc', 'rs', 'mrp', 'price', 'net', 'wt',
              'exp', 'mfg', 'date', 'batch', 'best', 'before', 'made', 'in', 'from', 'use', 'only'}

_LETTER_RE = re.compile(r'[a-z\u0600-\u06ff]')


def normalize(text):
    """lower-case, keep latin letters / digits / Urdu-Arabic letters only, collapse spaces."""
    text = (text or '').lower()
    text = re.sub(r'[^a-z0-9\u0600-\u06ff]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def tokens(text):
    return [t for t in normalize(text).split() if len(t) >= 3 and t not in STOP_WORDS]


def trigrams(s):
    s = ' ' + s + ' '
    return {s[i:i + 3] for i in range(len(s) - 2)}


def score(ocr_text, ocr_tokens, name):
    """0-100: how well the product name matches the text read from the camera."""
    n = normalize(name)
    if not n:
        return 0
    o = normalize(ocr_text)
    if n in o:                                    # the whole product name is visible in the text
        return min(100, 90 + len(n) // 3)         # longer (more specific) names win over short ones
    name_tokens = [t for t in n.split() if len(t) >= 2]
    if not name_tokens:
        return 0

    hit = 0.0
    for nt in name_tokens:                        # words of the name found (1-2 wrong letters allowed)
        best = 0.0
        for ot in ocr_tokens:
            r = difflib.SequenceMatcher(None, nt, ot).ratio()
            if r > best:
                best = r
        if best >= 0.78:
            hit += best
    coverage = hit / len(name_tokens)

    whole = difflib.SequenceMatcher(None, n, o).ratio() if len(o) <= len(n) * 2.5 else 0.0
    return round(100 * max(coverage * 0.95, whole))


def make_entry(pid, name, barcode, aliases=()):
    """Build one catalog entry (what the view caches)."""
    norm = normalize(name)
    if not norm:
        return None
    e = {'id': pid, 'name': name, 'barcode': re.sub(r'\D', '', barcode or ''),
         'names': [(name, norm, trigrams(norm))]}
    for a in aliases:
        an = normalize(a)
        if an:
            e['names'].append((a, an, trigrams(an)))
    return e


class Index:
    """Catalog + inverted trigram index.  Built once (not per request).

    The old rank() compared the text with EVERY product name on every request. Now only the names that share at
    least one trigram with the text are touched (via `postings`), and the barcode lookup is a dict.
    Results are identical to the old full scan (tests compare both).
    """
    __slots__ = ('entries', 'owner', 'size', 'postings', 'by_barcode')

    def __init__(self, catalog):
        self.entries = list(catalog)
        self.owner = []          # name id -> position of its product in entries
        self.size = []           # name id -> number of trigrams of that name
        self.postings = {}       # trigram -> [name id, ...]
        self.by_barcode = {}     # barcode digits -> [entry, ...]
        for ei, e in enumerate(self.entries):
            if e['barcode']:
                self.by_barcode.setdefault(e['barcode'], []).append(e)
            for _raw, _norm, ntg in e['names']:
                if not ntg:
                    continue
                gid = len(self.owner)
                self.owner.append(ei)
                self.size.append(len(ntg))
                for t in ntg:
                    self.postings.setdefault(t, []).append(gid)

    def __len__(self):
        return len(self.entries)

    def candidates(self, tg):
        """Entries whose best name shares >= PREFILTER_MIN of its trigrams with `tg`, best first (max PREFILTER_TOP)."""
        counts = {}
        for t in tg:
            for gid in self.postings.get(t, ()):
                counts[gid] = counts.get(gid, 0) + 1
        best = {}
        for gid, n in counts.items():
            c = n / self.size[gid]
            if c >= PREFILTER_MIN:
                ei = self.owner[gid]
                if c > best.get(ei, 0.0):
                    best[ei] = c
        order = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
        return [self.entries[ei] for ei, _c in order[:PREFILTER_TOP]]


def rank(raw_text, catalog):
    """-> (cleaned_text, [(score, catalog_entry), ...] best first).
    `catalog` = an Index (fast, cached by the view) or a plain list of make_entry() dicts (tests)."""
    index = catalog if isinstance(catalog, Index) else Index(catalog)
    text = normalize(raw_text)
    toks = tokens(raw_text)
    digit_runs = re.findall(r'\d{8,14}', re.sub(r'[\s\-]', '', raw_text or ''))

    scored = {}
    # 1) exact barcode read from the camera
    for run in digit_runs:
        for e in index.by_barcode.get(run, ()):
            scored[e['id']] = (100, e)

    # 2) trigram index -> short list, then precise scoring of the short list
    if text and toks:
        for e in index.candidates(trigrams(text)):
            if e['id'] in scored:
                continue
            s = 0
            for raw, _norm, _ntg in e['names']:
                s = max(s, score(text, toks, raw))
            if s >= MIN_LIST_SCORE:
                scored[e['id']] = (s, e)

    ranked = sorted(scored.values(), key=lambda x: (-x[0], -len(x[1]['name'])))
    return text, ranked


def rescore(raw_text, entries):
    """Score only the given catalog entries (what the browser pre-selected) with exactly the rules of rank().

    The phone ranks the whole catalog itself (static/ocr/ocr_match.js) and sends just the ids of its best products;
    the server re-scores those few, so a phone can never push a wrong score into the auto-add decision.
    -> (cleaned_text, [(score, entry), ...] best first), same shape as rank().
    """
    text = normalize(raw_text)
    toks = tokens(raw_text)
    runs = set(re.findall(r'\d{8,14}', re.sub(r'[\s\-]', '', raw_text or '')))
    scored = {}
    for e in entries:
        if e['barcode'] and e['barcode'] in runs:
            scored[e['id']] = (100, e)
            continue
        s = 0
        if text and toks:
            for raw, _norm, _ntg in e['names']:
                s = max(s, score(text, toks, raw))
        if s >= MIN_LIST_SCORE:
            scored[e['id']] = (s, e)
    return text, sorted(scored.values(), key=lambda x: (-x[0], -len(x[1]['name'])))


def outcome_rates(counts):
    """Dashboard numbers from {outcome: count}. Every rate is a percent of ALL scans, one decimal.

    auto_added / tapped_top = the machine's first answer was right; corrected = the cashier had to pick another
    product; no_match = nothing found; pending = shown but the cashier did nothing (left, or typed instead).
    """
    total = sum(counts.values())
    out = {'total': total}
    for k in ('auto_added', 'tapped_top', 'corrected', 'no_match', 'pending'):
        out[k] = counts.get(k, 0)
        out[k + '_pct'] = round(100.0 * out[k] / total, 1) if total else 0.0
    right = out['auto_added'] + out['tapped_top']
    decided = right + out['corrected']
    out['first_answer_right_pct'] = round(100.0 * right / decided, 1) if decided else 0.0
    return out


def apply_stock_boost(ranked, in_stock_ids, boost=None):
    """Products that HAVE stock in the selected warehouse get a few extra points, so when two names are
    nearly equal (180ml vs 90ml) the one you can actually sell comes first. Real exact matches (100) stay 100."""
    boost = STOCK_BOOST if boost is None else boost
    if not boost or not in_stock_ids:
        return ranked
    out = [((min(100, s + boost) if e['id'] in in_stock_ids else s), e) for s, e in ranked]
    out.sort(key=lambda x: (-x[0], -len(x[1]['name'])))
    return out


def batch_summary(batches, inv_stock, has_warehouse):
    """Price / stock / batch fields of one product from its batches (FIFO = oldest batch with stock first).

    batches   : [(batch_id, remaining_qty, cost_price, selling_price), ...] oldest first, remaining_qty > 0
    inv_stock : Inventory.stock in the selected warehouse (None if there is no row)
    Same rules as the old per-product code, but the caller loads the rows for ALL products in one query.
    """
    stock = (inv_stock if inv_stock is not None else 0) if has_warehouse else 0
    selling = 0.0
    latest = 0.0
    remaining = 0.0
    batch_id = None
    warning = ''
    first = batches[0] if batches else None
    if first:
        bid, rem, price, sp = first
        latest = float(price)
        selling = float(sp) if sp and sp > 0 else 0.0
        remaining = float(rem)
        batch_id = bid
        if not has_warehouse:
            stock = sum(float(b[1]) for b in batches)
        if selling <= 0 and stock > 0:
            warning = 'No selling price set for this batch!'
    else:
        warning = 'No stock batch found!' if has_warehouse else 'Select a warehouse to check price!'
    return {'stock': stock, 'selling_price': selling, 'latest_batch_price': latest,
            'batch_remaining': remaining, 'batch_id': batch_id, 'batch_count': len(batches), 'warning': warning}


def is_confident(top):
    """top = [(score, entry), ...] best first (max 5). True => the page may add the first one by itself."""
    if not top:
        return False
    first = top[0][0]
    second = top[1][0] if len(top) > 1 else 0
    confident = first >= AUTO_ADD_MIN_SCORE and (first - second) >= AUTO_ADD_MIN_GAP
    if not confident and len(top) > 1 and first >= 90:
        # "Rice" and "Basmati Rice 5kg" both found: the longer, more specific name is the answer
        confident = normalize(top[1][1]['name']) in normalize(top[0][1]['name'])
    return confident


def alias_candidate(text, product_name):
    """The text worth remembering as an alias of a product, or '' when it is not worth it."""
    n = normalize(text)
    words = [w for w in n.split() if len(w) >= 2 and w not in STOP_WORDS]
    n = ' '.join(words[:12])[:ALIAS_MAX_LEN].strip()
    if len(_LETTER_RE.findall(n)) < ALIAS_MIN_LETTERS:
        return ''
    if n == normalize(product_name):
        return ''
    return n


def should_learn(outcome, confident):
    """Learn an alias only from a HUMAN decision on a result the machine was NOT sure about.

    corrected  : the cashier picked another product than the first one  -> learn
    tapped_top : the cashier confirmed the first one, but we had not auto-added it -> learn
    auto_added / confident taps: the machine was already right -> nothing to learn
    """
    if outcome == 'corrected':
        return True
    return outcome == 'tapped_top' and not confident
