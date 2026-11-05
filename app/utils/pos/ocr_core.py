"""OCR product matching - pure Python, NO Django imports (so it can be unit-tested with plain python).

Used by app/views_frontend/pos_sales/ocr/.  Matching started as the old ocr.py (v2) and now also knows (v6):
    * pack sizes (90ml is not 180ml), UPC-A == EAN-13 barcodes
    * word rarity: a brand word counts more than "soap" / "pack"            (IdfTable, idf_weight)
    * look-alike characters: 0/o 1/l/i 5/s 8/b 2/z 6/g rn/m vv/w            (fold)
    * how sure the camera was about each word                                (parse_wconf, score(wconf=...))
static/ocr/ocr_match.js is a line-by-line port; tests/test_ocr_js_parity.py fails if the two ever disagree.
Two small helpers for the learning loop:

    is_confident(top)            -> should the page add the first product automatically?
    alias_candidate(text, name)  -> a clean alias string worth remembering, or '' if not worth it
"""
import difflib
import math
import re

# ---- tuning (raise AUTO_ADD_* if wrong products get added, lower them if too few are) ----
AUTO_ADD_MIN_SCORE = 78      # first match must score at least this ...
AUTO_ADD_MIN_GAP = 8         # ... and be this far ahead of the second one
MIN_LIST_SCORE = 45          # matches below this are not shown
PREFILTER_MIN = 0.25         # trigram share needed to enter the precise scoring
PREFILTER_TOP = 60           # how many candidates get the precise scoring
STOCK_BOOST = 3              # points added to products that have stock in the chosen warehouse (0 = off)
CANDIDATES = 10              # how many ranked products are looked at for stock before the top 5 are shown
SIZE_BONUS = 5               # points added when the size read from the pack (180ml, 1kg ...) equals the product's size
SIZE_PENALTY = 30            # points taken off when both have a size and the sizes differ (90ml pack vs a 180ml product)

# ---- v6: word rarity, look-alike characters, per-word camera confidence ----
WORD_MATCH_MIN = 0.78        # a name word counts as "seen" when the best text word is at least this similar
IDF_CAP = 4.0                # a rare word (brand) can count at most this many times more than a common word (soap)
FOLD_DISCOUNT = 0.97         # a word that only matches after 0->o, 1->l ... is trusted a little less than a clean match
CONF_LENIENT_BELOW = 65      # words the camera read with less confidence than this may differ a bit more ...
CONF_RELAX = 0.06            # ... (WORD_MATCH_MIN is lowered by this much for them)
CONF_FLOOR = 0.7             # a word read with confidence c counts CONF_FLOOR + (1 - CONF_FLOOR) * c/100 of a full match
MAX_WCONF = 40               # how many "word:confidence" pairs are read from a request

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


_FOLD_MULTI = (('rn', 'm'), ('vv', 'w'))
_FOLD_ONE = str.maketrans({'0': 'o', '1': 'l', 'i': 'l', '5': 's', '8': 'b', '2': 'z', '6': 'g'})
_HAS_LETTER = re.compile(r'[a-z]')


def fold(tok):
    """Look-alike characters of a camera read made equal: 'm1lk' == 'milk', 'l0x' == 'lox', 'rn' == 'm'.

    Only words that contain a letter and have >= 3 characters are folded (a plain size number like 250 stays 250).
    Both the product name and the text are folded the same way, so a real word still matches itself.
    Written the same way in static/ocr/ocr_match.js (parity test).
    """
    if len(tok) < 3 or not _HAS_LETTER.search(tok):
        return tok
    for a, b in _FOLD_MULTI:
        tok = tok.replace(a, b)
    return tok.translate(_FOLD_ONE)


def idf_weight(n, df):
    """How much a word of a product name counts: rare words (found in few product names) count more.

    1.0 (the word is in nearly every name) ... IDF_CAP (a brand that only one or two products carry). Integer maths
    only (no log), so Python and the browser always agree to the last digit.
    """
    r = max(1, n // max(1, df))
    return min(IDF_CAP, 1.0 + 0.5 * (r.bit_length() - 1))


class IdfTable:
    """word -> weight for one catalog. Words that are not in the table count as if only one product had them."""
    __slots__ = ('n', 'df', 'cache')

    def __init__(self, n, df):
        self.n = n
        self.df = df
        self.cache = {}

    def get(self, word):
        w = self.cache.get(word)
        if w is None:
            w = self.cache[word] = idf_weight(self.n, self.df.get(word, 1))
        return w


def parse_wconf(text):
    """'lux:92,soap:61' -> {'lux': 92, 'soap': 61}.  Garbage is skipped, values are clamped to 0..100."""
    out = {}
    for part in (text or '').split(',')[:MAX_WCONF]:
        word, _, val = part.rpartition(':')
        try:
            c = int(float(val))
        except (TypeError, ValueError, OverflowError):
            continue
        c = 0 if c < 0 else 100 if c > 100 else c
        for w in normalize(word).split():
            out[w] = min(out.get(w, 100), c)
    return out


_QTY_RE = re.compile(r'(^|[^0-9.,])(\d+(?:[.,]\d+)?)\s*(ml|ltrs?|litres?|liters?|l|kgs?|gms?|grams?|g)(?![a-z])', re.I)
_QTY_MULT = {'ml': 1, 'g': 1, 'gm': 1, 'gms': 1, 'gram': 1, 'grams': 1,
             'l': 1000, 'ltr': 1000, 'ltrs': 1000, 'litre': 1000, 'litres': 1000, 'liter': 1000, 'liters': 1000,
             'kg': 1000, 'kgs': 1000}


def quantities(text):
    """Sizes found in a text, as a sorted list of keys: 'v180' = 180 ml, 'm1000' = 1000 g.

    '180ml', '180 ML', '1.5 ltr', '1,5l', '500gm', '1kg' are all understood; litres/kg are converted to ml/g,
    so '1L' == '1000ml' and '1kg' == '1000g'. Written the same way in static/ocr/ocr_match.js (parity test).
    """
    out = set()
    for m in _QTY_RE.finditer(text or ''):
        unit = m.group(3).lower()
        if len(m.group(2)) > 9:                    # not a pack size (a long number is a barcode / batch code)
            continue
        v = float(m.group(2).replace(',', '.'))
        n = int(math.floor(v * _QTY_MULT[unit] + 0.5))
        if n > 0:
            out.add(('v' if unit in ('ml', 'l', 'ltr', 'ltrs', 'litre', 'litres', 'liter', 'liters') else 'm') + str(n))
    return sorted(out)


def _near(a, b):
    """Same kind and same number of digits, exactly one digit different: '180' vs '190' is most likely a misread."""
    if a[0] != b[0] or len(a) != len(b):
        return False
    return sum(1 for x, y in zip(a[1:], b[1:]) if x != y) == 1


def size_adjust(s, ocr_q, name_q):
    """Make the size on the pack count: same size -> a few points more, clearly different size -> many points less.

    Nothing changes when either side has no size, or when the sizes differ by one digit only (the camera may have
    misread it). Without this, 'Pepsi 90ml' and 'Pepsi 180ml' score the same for a 90ml pack.
    """
    if not s or not ocr_q or not name_q:
        return s
    matched = mismatch = False
    for d in ('v', 'm'):
        o = [q for q in ocr_q if q[0] == d]
        n = [q for q in name_q if q[0] == d]
        if not o or not n:
            continue
        if any(x in o for x in n):
            matched = True
        elif not any(_near(x, y) for x in n for y in o):
            mismatch = True
    if matched:
        return min(100, s + SIZE_BONUS)
    if mismatch:
        return max(0, s - SIZE_PENALTY)
    return s


def score(ocr_text, ocr_tokens, name, idf=None, wconf=None):
    """0-100: how well the product name matches the text read from the camera.

    idf   : IdfTable of the catalog (rare words of the name count more) - None = every word counts the same
    wconf : {text word: camera confidence 0-100} - a word the camera was unsure about counts a little less but may
            also differ a little more; None = unknown
    """
    n = normalize(name)
    if not n:
        return 0
    o = normalize(ocr_text)
    if n in o:                                    # the whole product name is visible in the text
        return min(100, 90 + len(n) // 3)         # longer (more specific) names win over short ones
    name_tokens = [t for t in n.split() if len(t) >= 2]
    if not name_tokens:
        return 0

    folded = {}
    hit = 0.0
    total = 0.0
    for nt in name_tokens:                        # words of the name found (1-2 wrong letters allowed)
        wt = idf.get(nt) if idf is not None else 1.0
        total += wt
        fnt = fold(nt)
        best = 0.0
        for ot in ocr_tokens:
            c = wconf.get(ot) if wconf else None
            thr = WORD_MATCH_MIN - (CONF_RELAX if (c is not None and c < CONF_LENIENT_BELOW) else 0.0)
            r = difflib.SequenceMatcher(None, nt, ot).ratio()
            if r < 0.95:                          # 0 vs o, 1 vs l ...: same word once look-alikes are equal
                fot = folded.get(ot)
                if fot is None:
                    fot = folded[ot] = fold(ot)
                if fnt != nt or fot != ot:
                    rf = difflib.SequenceMatcher(None, fnt, fot).ratio() * FOLD_DISCOUNT
                    if rf > r:
                        r = rf
            if r >= thr:
                v = r if c is None else r * (CONF_FLOOR + (1.0 - CONF_FLOOR) * ((0 if c < 0 else 100 if c > 100 else c) / 100.0))
                if v > best:
                    best = v
        hit += wt * best
    coverage = hit / total

    whole = difflib.SequenceMatcher(None, n, o).ratio() if len(o) <= len(n) * 2.5 else 0.0
    return round(100 * max(coverage * 0.95, whole))


def barcode_key(digits):
    """Barcode digits compared without leading zeros: UPC-A '036000291452' and EAN-13 '0036000291452' are one code."""
    return (digits or '').lstrip('0')


def make_entry(pid, name, barcode, aliases=()):
    """Build one catalog entry (what the view caches)."""
    norm = normalize(name)
    if not norm:
        return None
    e = {'id': pid, 'name': name, 'barcode': re.sub(r'\D', '', barcode or ''),
         'names': [(name, norm, trigrams(norm))], 'qty': quantities(name)}
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
    __slots__ = ('entries', 'owner', 'size', 'postings', 'by_barcode', 'idf')

    def __init__(self, catalog):
        self.entries = list(catalog)
        self.owner = []          # name id -> position of its product in entries
        self.size = []           # name id -> number of trigrams of that name
        self.postings = {}       # trigram -> [name id, ...]
        self.by_barcode = {}     # barcode digits -> [entry, ...]
        df = {}                  # word -> number of product names that contain it
        for ei, e in enumerate(self.entries):
            for w in {t for t in e['names'][0][1].split() if len(t) >= 2}:
                df[w] = df.get(w, 0) + 1
            bk = barcode_key(e['barcode'])
            if bk:
                self.by_barcode.setdefault(bk, []).append(e)
            for _raw, _norm, ntg in e['names']:
                if not ntg:
                    continue
                gid = len(self.owner)
                self.owner.append(ei)
                self.size.append(len(ntg))
                for t in ntg:
                    self.postings.setdefault(t, []).append(gid)
        self.idf = IdfTable(len(self.entries), df)

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


def rank(raw_text, catalog, wconf=None):
    """-> (cleaned_text, [(score, catalog_entry), ...] best first).
    `catalog` = an Index (fast, cached by the view) or a plain list of make_entry() dicts (tests).
    `wconf` = {text word: camera confidence} (optional, see score())."""
    index = catalog if isinstance(catalog, Index) else Index(catalog)
    text = normalize(raw_text)
    toks = tokens(raw_text)
    digit_runs = re.findall(r'\d{8,14}', re.sub(r'[\s\-]', '', raw_text or ''))
    oq = quantities(raw_text)

    scored = {}
    # 1) exact barcode read from the camera
    for run in digit_runs:
        for e in index.by_barcode.get(barcode_key(run), ()):
            scored[e['id']] = (100, e)

    # 2) trigram index -> short list, then precise scoring of the short list
    if text and toks:
        for e in index.candidates(trigrams(text)):
            if e['id'] in scored:
                continue
            s = 0
            for raw, _norm, _ntg in e['names']:
                s = max(s, score(text, toks, raw, index.idf, wconf))
            s = size_adjust(s, oq, e.get('qty'))
            if s >= MIN_LIST_SCORE:
                scored[e['id']] = (s, e)

    ranked = sorted(scored.values(), key=lambda x: (-x[0], -len(x[1]['name'])))
    return text, ranked


def rescore(raw_text, entries, idf=None, wconf=None):
    """Score only the given catalog entries (what the browser pre-selected) with exactly the rules of rank().

    The phone ranks the whole catalog itself (static/ocr/ocr_match.js) and sends just the ids of its best products;
    the server re-scores those few, so a phone can never push a wrong score into the auto-add decision.
    -> (cleaned_text, [(score, entry), ...] best first), same shape as rank().
    Pass the catalog's `index.idf` and the same `wconf` the phone used, or the scores differ from the phone's.
    """
    text = normalize(raw_text)
    toks = tokens(raw_text)
    runs = {barcode_key(r) for r in re.findall(r'\d{8,14}', re.sub(r'[\s\-]', '', raw_text or ''))}
    oq = quantities(raw_text)
    scored = {}
    for e in entries:
        bk = barcode_key(e['barcode'])
        if bk and bk in runs:
            scored[e['id']] = (100, e)
            continue
        s = 0
        if text and toks:
            for raw, _norm, _ntg in e['names']:
                s = max(s, score(text, toks, raw, idf, wconf))
            s = size_adjust(s, oq, e.get('qty'))
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
