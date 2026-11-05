"""OCR tests that need no Django (same style as the other files in tests/).

Run from the project root:  python -I tests/test_ocr_pure.py
"""
import ast
import importlib.util
import os
import random
import re
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_source(rel):
    """Source text of a file. 'app/views_frontend/pos_sales/ocr.py' now means the whole ocr/ package (all its files)."""
    if rel == 'app/views_frontend/pos_sales/ocr.py':
        d = os.path.join(ROOT, 'app/views_frontend/pos_sales/ocr')
        return '\n'.join(open(os.path.join(d, n), encoding='utf-8').read() for n in sorted(os.listdir(d)) if n.endswith('.py'))
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load('app/utils/pos/ocr_core.py', 'ocr_core')
cache_mod = _load('app/utils/pos/ocr_cache.py', 'ocr_cache')
E = core.make_entry

CATALOG = [
    E(1, 'Sunsilk Shampoo 180ml', '8901030123456'),
    E(2, 'Sunsilk Shampoo 90ml', '8901030999999'),
    E(3, 'Rice', ''),
    E(4, 'Basmati Rice 5kg', ''),
    E(5, 'Lux Soap', '', ['lux sop', '\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646']),
    E(6, 'Surf Excel 1kg', ''),
    E(7, 'Dettol Handwash 250ml', ''),
]


def best(text):
    _t, ranked = core.rank(text, CATALOG)
    return ranked


class NormalizeTests(unittest.TestCase):
    def test_punctuation_case_spaces(self):
        self.assertEqual(core.normalize('  Sunsilk,  SHAMPOO-180ml! '), 'sunsilk shampoo 180ml')

    def test_none_and_empty(self):
        self.assertEqual(core.normalize(None), '')
        self.assertEqual(core.normalize(''), '')

    def test_urdu_letters_are_kept(self):
        self.assertEqual(core.normalize('\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646'), '\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646')

    def test_tokens_drop_stop_words_and_short_words(self):
        self.assertEqual(core.tokens('The new Lux pack of 2 pcs'), ['lux'])


class ScoreTests(unittest.TestCase):
    def sc(self, text, name):
        return core.score(text, core.tokens(text), name)

    def test_whole_name_visible_scores_90_plus(self):
        self.assertGreaterEqual(self.sc('buy surf excel 1kg now', 'Surf Excel 1kg'), 90)

    def test_longer_name_beats_shorter_name(self):
        self.assertGreater(self.sc('basmati rice 5kg', 'Basmati Rice 5kg'), self.sc('basmati rice 5kg', 'Rice'))

    def test_one_wrong_letter_still_scores_high(self):
        self.assertGreaterEqual(self.sc('Surf Exel 1kg', 'Surf Excel 1kg'), 85)

    def test_unrelated_is_low(self):
        self.assertLess(self.sc('xyz qqq', 'Surf Excel 1kg'), core.MIN_LIST_SCORE)

    def test_empty_name_scores_zero(self):
        self.assertEqual(self.sc('rice', '!!!'), 0)


class RankTests(unittest.TestCase):
    def test_bad_reading_still_finds_the_product(self):
        r = best('Sunsilk Shampo0 18Oml')            # the example from the old docstring
        self.assertEqual(r[0][1]['id'], 1)

    def test_extra_packaging_words_are_ignored(self):
        r = best('sunsilk shampoo 180ml new pack')
        self.assertEqual(r[0][1]['id'], 1)
        self.assertTrue(core.is_confident(r[:5]))

    def test_barcode_digits_win_immediately(self):
        r = best('xx 8901030999999 yy')
        self.assertEqual((r[0][0], r[0][1]['id']), (100, 2))

    def test_barcode_with_spaces_and_dashes(self):
        r = best('8901 0309-99999')
        self.assertEqual(r[0][1]['id'], 2)

    def test_alias_is_found(self):
        self.assertEqual(best('lux sop')[0][1]['id'], 5)

    def test_urdu_alias_is_found(self):
        self.assertEqual(best('\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646')[0][1]['id'], 5)

    def test_garbage_finds_nothing(self):
        self.assertEqual(best('xyz qqq'), [])

    def test_empty_text(self):
        self.assertEqual(core.rank('', CATALOG), ('', []))

    def test_split_word_is_found(self):
        self.assertEqual(best('dettol hand wash 250 ml')[0][1]['id'], 7)

    def test_results_sorted_best_first(self):
        scores = [s for s, _e in best('sunsilk shampoo')]
        self.assertEqual(scores, sorted(scores, reverse=True))


class ConfidenceTests(unittest.TestCase):
    def test_rice_vs_basmati_rice_longer_name_wins(self):
        r = best('Basmati Rice 5kg')
        self.assertEqual([e['id'] for _s, e in r[:2]], [4, 3])
        self.assertTrue(core.is_confident(r[:5]))

    def test_plain_rice_is_confident(self):
        self.assertTrue(core.is_confident(best('rice')[:5]))

    def test_look_alike_misreads_still_find_the_right_size(self):
        # "Shampo0 18Oml" (zero for o, letter O for 0): once look-alike characters count as equal the 180ml one
        # is clearly ahead of the 90ml one (this used to be a known weak spot - the cashier had to choose)
        r = best('Sunsilk Shampo0 18Oml')
        self.assertEqual([e['id'] for _s, e in r[:2]], [1, 2])
        self.assertTrue(core.is_confident(r[:5]))

    def test_two_close_sizes_without_a_size_on_the_pack_are_not_confident(self):
        r = best('Sunsilk Shampoo')
        self.assertFalse(core.is_confident(r[:5]))

    def test_nothing_found_is_not_confident(self):
        self.assertFalse(core.is_confident([]))

    def test_gap_rule(self):
        a, b = {'name': 'aaa'}, {'name': 'bbb'}
        self.assertTrue(core.is_confident([(80, a), (70, b)]))
        self.assertFalse(core.is_confident([(80, a), (75, b)]))
        self.assertFalse(core.is_confident([(70, a)]))


class LearningTests(unittest.TestCase):
    def test_alias_candidate_is_cleaned(self):
        self.assertEqual(core.alias_candidate('Sunsilk Shampo0 18Oml!', 'Sunsilk Shampoo 180ml'), 'sunsilk shampo0 18oml')

    def test_too_short_is_not_remembered(self):
        self.assertEqual(core.alias_candidate('ab', 'Rice'), '')

    def test_same_as_product_name_is_not_remembered(self):
        self.assertEqual(core.alias_candidate('Basmati  RICE 5kg', 'Basmati Rice 5kg'), '')

    def test_barcode_only_text_is_not_remembered(self):
        self.assertEqual(core.alias_candidate('8901030999999', 'Sunsilk Shampoo 90ml'), '')

    def test_alias_fits_the_database_column(self):
        long_text = ' '.join('word%d' % i for i in range(60))
        self.assertLessEqual(len(core.alias_candidate(long_text, 'x')), core.ALIAS_MAX_LEN)

    def test_stop_words_are_removed(self):
        self.assertEqual(core.alias_candidate('the new lux soap pack', 'Lux Soap 100g'), 'lux soap')

    def test_learning_rules(self):
        self.assertTrue(core.should_learn('corrected', True))
        self.assertTrue(core.should_learn('tapped_top', False))
        self.assertFalse(core.should_learn('tapped_top', True))
        self.assertFalse(core.should_learn('auto_added', False))
        self.assertFalse(core.should_learn('pending', False))
        self.assertFalse(core.should_learn('no_match', False))

    def test_learned_alias_makes_the_next_scan_find_it(self):
        text = 'sunsilk shmpo 18 oml pink'
        cat = [E(1, 'Sunsilk Shampoo 180ml', ''), E(2, 'Other Thing', '')]
        before = core.rank(text, cat)[1]
        alias = core.alias_candidate(text, 'Sunsilk Shampoo 180ml')
        cat2 = [E(1, 'Sunsilk Shampoo 180ml', '', [alias]), E(2, 'Other Thing', '')]
        after = core.rank(text, cat2)[1]
        self.assertEqual(after[0][1]['id'], 1)
        self.assertGreaterEqual(after[0][0], max(90, before[0][0] if before else 0))


class WiringTests(unittest.TestCase):
    """Cheap checks that the pieces are connected (no Django needed)."""

    def read(self, rel):
        return read_source(rel)

    def test_view_module_defines_both_views(self):
        tree = ast.parse(self.read('app/views_frontend/pos_sales/ocr.py'))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'ocr_match_product', 'ocr_feedback', 'rank_products'} <= names)

    def test_feedback_view_is_post_only_and_permission_checked(self):
        src = self.read('app/views_frontend/pos_sales/ocr.py')
        i = src.index('def ocr_feedback')
        head = src[max(0, i - 120):i]
        self.assertIn('@require_POST', head)
        self.assertIn('@perm_required', head)
        self.assertIn('@login_required', head)

    def test_models_declared_in_models_package_and_admin(self):
        self.assertIn('class OcrScanLog', self.read('app/models/pos/ocr.py'))
        self.assertIn('class OcrAliasSuggestion', self.read('app/models/pos/ocr.py'))
        self.assertIn('"pos.ocr"', self.read('app/models/__init__.py'))
        self.assertIn('"ocr"', self.read('app/admin/__init__.py'))

    def test_migration_follows_0030_and_creates_both_models(self):
        src = self.read('app/migrations/0031_ocr_log_alias.py')
        self.assertIn("('app', '0030_agri_usage_snapshot')", src)
        self.assertIn("name='OcrScanLog'", src)
        self.assertIn("name='OcrAliasSuggestion'", src)

    def test_urls_and_page_use_the_feedback_endpoint(self):
        self.assertIn('views_frontend.ocr_feedback', self.read('app/urls.py'))
        page = self.read('templates/sales/pos.html')
        self.assertIn('/ajax/ocr-feedback/', page)
        # Urdu is still supported: English loads first (fast), the Urdu+English reader follows in the background
        self.assertIn("OCR_LANGS = ['eng']", page)
        self.assertIn("OCR_LANGS_URDU = ['eng+urd']", page)
        self.assertIn('\\u0600-\\u06ff', page)           # Urdu letters survive the text cleaning

    def test_old_ocr_py_logic_moved_out_of_the_view(self):
        src = self.read('app/views_frontend/pos_sales/ocr.py')
        self.assertNotIn('difflib', src)


# ---------------------------------------------------------------- B: speed / stock / rate limit
def old_rank(raw_text, catalog):
    """The v2/v3 algorithm (full scan of every product), kept here as the reference the new index must equal."""
    text = core.normalize(raw_text)
    tokens = core.tokens(raw_text)
    digit_runs = re.findall(r'\d{8,14}', re.sub(r'[\s\-]', '', raw_text or ''))
    scored = {}
    if digit_runs:
        for e in catalog:
            if core.barcode_key(e['barcode']) and core.barcode_key(e['barcode']) in [core.barcode_key(r) for r in digit_runs]:
                scored[e['id']] = (100, e)
    if text and tokens:
        tg = core.trigrams(text)
        pre = []
        for e in catalog:
            best = 0.0
            for _raw, _norm, ntg in e['names']:
                if ntg:
                    c = len(tg & ntg) / len(ntg)
                    if c > best:
                        best = c
            if best >= core.PREFILTER_MIN:
                pre.append((best, e))
        pre.sort(key=lambda x: -x[0])
        for _c, e in pre[:core.PREFILTER_TOP]:
            if e['id'] in scored:
                continue
            sc = 0
            for raw, _norm, _ntg in e['names']:
                sc = max(sc, core.score(text, tokens, raw, _idf_of(catalog)))
            sc = core.size_adjust(sc, core.quantities(raw_text), e.get('qty'))   # size on the pack counts (B6)
            if sc >= core.MIN_LIST_SCORE:
                scored[e['id']] = (sc, e)
    return text, sorted(scored.values(), key=lambda x: (-x[0], -len(x[1]['name'])))


_IDF_CACHE = {}


def _idf_of(catalog):
    """Word-rarity table of a catalog (what Index builds), computed once per catalog list."""
    key = id(catalog)
    if key not in _IDF_CACHE:
        _IDF_CACHE[key] = (catalog, core.Index(catalog).idf)      # keep the list alive so the id stays unique
    return _IDF_CACHE[key][1]


WORDS = ('sunsilk shampoo lux soap surf excel rice basmati dettol handwash pepsi cola milk pack tea lipton '
         'colgate paste brush oil sunflower dalda ghee sugar salt flour atta wheat daal masoor chana biscuit '
         'candy tissue napkin detergent bleach vim bar liquid cream lotion powder 90ml 180ml 250ml 1kg 5kg 500g').split()


def make_catalog(n, seed=7):
    rnd = random.Random(seed)
    cat = []
    for i in range(n):
        name = ' '.join(rnd.choice(WORDS) for _ in range(rnd.randint(2, 4)))
        bc = ''.join(rnd.choice('0123456789') for _ in range(13)) if i % 3 == 0 else ''
        cat.append(E(i + 1, name, bc, [rnd.choice(WORDS) + ' ' + rnd.choice(WORDS)] if i % 5 == 0 else ()))
    return cat


def noisy(text, rnd):
    chars = list(text)
    for _ in range(rnd.randint(0, 2)):
        if chars:
            chars[rnd.randrange(len(chars))] = rnd.choice('abcdefghijklmnopqrstuvwxyz0')
    return ''.join(chars) + (' ' + rnd.choice(WORDS) if rnd.random() < .5 else '')


class IndexEqualsFullScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = make_catalog(1500)
        cls.index = core.Index(cls.cat)

    def test_same_results_as_the_old_full_scan(self):
        rnd = random.Random(1)
        for _ in range(150):
            e = rnd.choice(self.cat)
            q = noisy(e['name'], rnd)
            if rnd.random() < .15 and e['barcode']:
                q += ' ' + e['barcode']
            want = old_rank(q, self.cat)
            got = core.rank(q, self.index)
            self.assertEqual(got[0], want[0])
            self.assertEqual([(s, x['id']) for s, x in got[1]], [(s, x['id']) for s, x in want[1]], q)

    def test_plain_list_and_index_give_the_same_answer(self):
        self.assertEqual([(s, x['id']) for s, x in core.rank('lux soap 90ml', self.cat)[1]],
                         [(s, x['id']) for s, x in core.rank('lux soap 90ml', self.index)[1]])

    def test_index_is_not_slower_than_the_full_scan(self):
        cat = make_catalog(6000, seed=3)
        idx = core.Index(cat)
        qs = ['sunsilk shampo0 18oml', 'basmati rice 5kg', 'dettol hand wash 250ml', 'lipton tea pack', 'colgate paste']
        t0 = time.perf_counter()
        for q in qs:
            old_rank(q, cat)
        t_old = time.perf_counter() - t0
        t0 = time.perf_counter()
        for q in qs:
            core.rank(q, idx)
        t_new = time.perf_counter() - t0
        print('\n  [6000 products, 5 scans] old full scan %.0f ms, index %.0f ms' % (t_old * 1000, t_new * 1000))
        self.assertLess(t_new, t_old * 1.5)       # timing varies by machine; only guard against a big slowdown

    def test_empty_catalog(self):
        self.assertEqual(core.rank('rice', core.Index([])), ('rice', []))


class StockBoostTests(unittest.TestCase):
    def setUp(self):
        self.a = E(1, 'Sunsilk Shampoo 180ml', '')
        self.b = E(2, 'Sunsilk Shampoo 90ml', '')

    def test_in_stock_product_moves_up_when_scores_are_close(self):
        ranked = [(90, self.a), (88, self.b)]
        out = core.apply_stock_boost(ranked, {2}, 3)
        self.assertEqual([e['id'] for _s, e in out], [2, 1])
        self.assertEqual(out[0][0], 91)

    def test_big_difference_is_not_overturned(self):
        out = core.apply_stock_boost([(95, self.a), (70, self.b)], {2}, 3)
        self.assertEqual(out[0][1]['id'], 1)

    def test_score_is_capped_at_100(self):
        self.assertEqual(core.apply_stock_boost([(99, self.a)], {1}, 3)[0][0], 100)

    def test_nothing_in_stock_or_boost_off_changes_nothing(self):
        ranked = [(90, self.a), (88, self.b)]
        self.assertEqual(core.apply_stock_boost(ranked, set(), 3), ranked)
        self.assertEqual(core.apply_stock_boost(ranked, {2}, 0), ranked)


class BatchSummaryTests(unittest.TestCase):
    B = [(10, 5, 100, 130), (11, 7, 110, 140)]      # oldest first

    def test_fifo_uses_the_oldest_batch(self):
        r = core.batch_summary(self.B, 12, True)
        self.assertEqual((r['batch_id'], r['selling_price'], r['latest_batch_price'], r['batch_remaining']),
                         (10, 130.0, 100.0, 5.0))
        self.assertEqual((r['stock'], r['batch_count'], r['warning']), (12, 2, ''))

    def test_without_warehouse_stock_is_sum_of_batches(self):
        self.assertEqual(core.batch_summary(self.B, None, False)['stock'], 12.0)

    def test_no_selling_price_warns(self):
        r = core.batch_summary([(1, 5, 100, 0)], 5, True)
        self.assertEqual((r['selling_price'], r['warning']), (0.0, 'No selling price set for this batch!'))

    def test_no_batches(self):
        self.assertEqual(core.batch_summary([], None, True)['warning'], 'No stock batch found!')
        self.assertEqual(core.batch_summary([], None, False)['warning'], 'Select a warehouse to check price!')
        self.assertEqual(core.batch_summary([], None, True)['stock'], 0)


class FakeCache:
    def __init__(self, broken=False):
        self.d, self.broken = {}, broken

    def add(self, k, v, t=None):
        if self.broken:
            raise RuntimeError('down')
        self.d.setdefault(k, v)

    def incr(self, k):
        self.d[k] += 1
        return self.d[k]

    def get(self, k):
        if self.broken:
            raise RuntimeError('down')
        return self.d.get(k)

    def set(self, k, v, t=None):
        self.d[k] = v


class RateLimitAndVersionTests(unittest.TestCase):
    def test_blocks_after_the_limit_and_resets_next_minute(self):
        c = FakeCache()
        res = [cache_mod.rate_ok(1, 'm', 3, 60, _cache=c, _now=1000) for _ in range(5)]
        self.assertEqual(res, [True, True, True, False, False])
        self.assertTrue(cache_mod.rate_ok(1, 'm', 3, 60, _cache=c, _now=1000 + 61))

    def test_users_and_buckets_are_separate(self):
        c = FakeCache()
        for _ in range(3):
            cache_mod.rate_ok(1, 'm', 3, 60, _cache=c, _now=5)
        self.assertTrue(cache_mod.rate_ok(2, 'm', 3, 60, _cache=c, _now=5))
        self.assertTrue(cache_mod.rate_ok(1, 'feedback', 3, 60, _cache=c, _now=5))

    def test_broken_cache_never_blocks_the_cashier(self):
        self.assertTrue(cache_mod.rate_ok(1, 'm', 1, 60, _cache=FakeCache(broken=True)))

    def test_catalog_version_changes_after_invalidate(self):
        c = FakeCache()
        v0 = cache_mod.catalog_version(_cache=c)
        cache_mod.invalidate_catalog(_cache=c)
        self.assertNotEqual(cache_mod.catalog_version(_cache=c), v0)
        self.assertEqual(cache_mod.catalog_version(_cache=FakeCache(broken=True)), 0)


class WiringBTests(unittest.TestCase):
    def read(self, rel):
        return read_source(rel)

    def test_view_uses_batched_loaders_and_limits(self):
        src = self.read('app/views_frontend/pos_sales/ocr.py')
        for needle in ('_load_batches', '_load_stock', 'apply_stock_boost', 'rate_ok', 'status=429', 'invalidate_catalog'):
            self.assertIn(needle, src)
        # no query inside the per-product loop any more
        loop = src[src.index('products = []'):src.index('confident = core.is_confident(top)')]
        self.assertNotIn('objects.', loop)

    def test_page_handles_429(self):
        self.assertIn('r.status === 429', self.read('templates/sales/pos.html'))

    def test_admin_uses_the_version_helper(self):
        self.assertIn('invalidate_catalog', self.read('app/admin/ocr.py'))


class RescoreTests(unittest.TestCase):
    """The phone sends ids, the server re-scores them: the result must equal what rank() gave for those products."""

    QUERIES = ['sunsilk shampoo 180ml', 'sunsilk shampo 90 ml', 'lux sop', 'basmati rice', 'surf excel',
               'barcode 8901030999999 here', '', 'zzzz qqqq', '\u0644\u06a9\u0633 \u0635\u0627\u0628\u0646']

    def test_rescore_equals_rank_for_the_same_products(self):
        for q in self.QUERIES:
            text, ranked = core.rank(q, CATALOG)
            by_id = {e['id']: e for e in CATALOG}
            t2, again = core.rescore(q, [by_id[e['id']] for _s, e in ranked])
            self.assertEqual(text, t2, q)
            self.assertEqual([(s, e['id']) for s, e in ranked], [(s, e['id']) for s, e in again], q)

    def test_rescore_ignores_products_that_do_not_match(self):
        _t, got = core.rescore('lux soap', CATALOG)          # whole catalog handed in: only real matches come back
        self.assertEqual([e['id'] for _s, e in got][:1], [5])
        self.assertNotIn(6, [e['id'] for _s, e in got])

    def test_rescore_empty(self):
        self.assertEqual(core.rescore('lux soap', [])[1], [])


class OutcomeRatesTests(unittest.TestCase):
    def test_rates(self):
        r = core.outcome_rates({'auto_added': 60, 'tapped_top': 10, 'corrected': 20, 'no_match': 10})
        self.assertEqual(r['total'], 100)
        self.assertEqual(r['auto_added_pct'], 60.0)
        self.assertEqual(r['corrected_pct'], 20.0)
        self.assertEqual(r['first_answer_right_pct'], 77.8)      # 70 right of 90 decided
        self.assertEqual(r['pending'], 0)

    def test_no_scans_no_division_by_zero(self):
        r = core.outcome_rates({})
        self.assertEqual((r['total'], r['first_answer_right_pct'], r['no_match_pct']), (0, 0.0, 0.0))


class SizeAwareTests(unittest.TestCase):
    """B6: the size on the pack (90ml / 180ml / 1.5L / 500g / 1kg) decides between products with the same name."""

    def cat(self, *names):
        return [core.make_entry(i + 1, n, '') for i, n in enumerate(names)]

    def top(self, text, *names):
        _t, ranked = core.rank(text, self.cat(*names))
        return [(s, e['name']) for s, e in ranked]

    def test_quantities_are_read_in_every_common_spelling(self):
        q = core.quantities
        self.assertEqual(q('Pepsi 180ml'), ['v180'])
        self.assertEqual(q('PEPSI 180 ML'), ['v180'])
        self.assertEqual(q('1.5 ltr'), ['v1500'])
        self.assertEqual(q('1,5L'), ['v1500'])
        self.assertEqual(q('1L'), q('1000ml'))
        self.assertEqual(q('500gm tea'), ['m500'])
        self.assertEqual(q('1kg'), q('1000 g'))
        self.assertEqual(q('x250ml 3kg'), ['m3000', 'v250'])

    def test_words_and_plain_numbers_are_not_sizes(self):
        for t in ('12 large', 'Rs 250', 'batch 180', 'mrp 90 pack', 'glass 5 gold', ''):
            self.assertEqual(core.quantities(t), [], t)

    def test_entry_carries_the_size_of_its_name(self):
        self.assertEqual(core.make_entry(1, 'Pepsi 1.5L', '')['qty'], ['v1500'])
        self.assertEqual(core.make_entry(2, 'Lux Soap', '')['qty'], [])

    def test_the_right_size_wins_even_when_the_names_are_otherwise_equal(self):
        names = ('Pepsi Cola 180ml', 'Pepsi Cola 90ml', 'Pepsi Cola 1.5L')
        self.assertEqual(self.top('pepsi cola 90ml', *names)[0][1], 'Pepsi Cola 90ml')
        self.assertEqual(self.top('pepsi cola 180 ml', *names)[0][1], 'Pepsi Cola 180ml')
        self.assertEqual(self.top('pepsi cola 1.5 ltr', *names)[0][1], 'Pepsi Cola 1.5L')

    def test_wrong_sizes_are_pushed_down_and_the_gap_is_big_enough_to_auto_add(self):
        ranked = self.top('pepsi cola 90ml', 'Pepsi Cola 180ml', 'Pepsi Cola 90ml')
        self.assertGreaterEqual(ranked[0][0] - (ranked[1][0] if len(ranked) > 1 else 0), core.AUTO_ADD_MIN_GAP)

    def test_units_are_converted_1kg_is_1000g(self):
        ranked = self.top('basmati rice 1 kg', 'Basmati Rice 1000g', 'Basmati Rice 5kg')
        self.assertEqual(ranked[0][1], 'Basmati Rice 1000g')

    def test_no_size_on_either_side_changes_nothing(self):
        self.assertEqual(core.size_adjust(80, [], ['v90']), 80)
        self.assertEqual(core.size_adjust(80, ['v90'], []), 80)
        self.assertEqual(core.size_adjust(0, ['v90'], ['v180']), 0)
        names = ('Pepsi Cola 180ml', 'Pepsi Cola 90ml')
        got = dict((n, sc) for sc, n in self.top('pepsi cola', *names))
        toks = core.tokens('pepsi cola')
        for n in names:                                          # no size read from the pack -> plain old score
            self.assertEqual(got[n], core.score('pepsi cola', toks, n))

    def test_a_one_digit_misread_is_not_punished(self):
        # the camera read 190ml, the pack says 180ml: do not push the real product below an unsized one
        self.assertEqual(core.size_adjust(90, ['v190'], ['v180']), 90)
        self.assertEqual(core.size_adjust(90, ['v90'], ['v180']), 90 - core.SIZE_PENALTY)

    def test_bonus_is_capped_at_100_and_penalty_at_0(self):
        self.assertEqual(core.size_adjust(99, ['v90'], ['v90']), 100)
        self.assertEqual(core.size_adjust(10, ['v90'], ['v250']), 0)

    def test_rescore_uses_the_same_rule_as_rank(self):
        cat = self.cat('Pepsi Cola 180ml', 'Pepsi Cola 90ml')
        _t, a = core.rank('pepsi cola 90ml', cat)
        _t, b = core.rescore('pepsi cola 90ml', cat)
        self.assertEqual([(s, e['id']) for s, e in a], [(s, e['id']) for s, e in b])

    def test_a_barcode_hit_is_never_changed_by_size(self):
        e = core.make_entry(1, 'Pepsi Cola 180ml', '8961234567890')
        _t, ranked = core.rank('8961234567890 pepsi 90ml', [e])
        self.assertEqual(ranked[0][0], 100)


class MatcherV6Tests(unittest.TestCase):
    """Word rarity (IDF), look-alike characters, per-word camera confidence, hardening."""

    def test_fold_makes_look_alikes_equal(self):
        f = core.fold
        self.assertEqual(f('m1lk'), f('milk'))
        self.assertEqual(f('rnilk'), f('milk'))          # r+n looks like m
        self.assertEqual(f('l1pt0n'), f('lipton'))
        self.assertEqual(f('vvater'), f('water'))
        self.assertEqual(f('250'), '250')                # a plain number is never folded
        self.assertEqual(f('ab'), 'ab')                  # too short
        self.assertEqual(f(''), '')

    def test_idf_weight_values(self):
        w = core.idf_weight
        self.assertEqual(w(1, 1), 1.0)
        self.assertEqual(w(900, 900), 1.0)               # in every name: normal weight
        self.assertEqual(w(4, 1), 2.0)
        self.assertEqual(w(900, 1), core.IDF_CAP)        # a brand only one product has: capped
        self.assertEqual(w(900, 0), core.IDF_CAP)        # unknown word = like df 1
        vals = [w(1000, df) for df in (1000, 500, 100, 10, 2, 1)]
        self.assertEqual(vals, sorted(vals))             # rarer never counts less

    def test_index_builds_the_rarity_table_from_product_names(self):
        idx = core.Index([E(1, 'Lux Soap', ''), E(2, 'Dettol Soap', ''), E(3, 'Medimix Soap', ''), E(4, 'Lifebuoy Soap', '')])
        self.assertEqual(idx.idf.get('soap'), 1.0)
        self.assertEqual(idx.idf.get('lux'), 2.0)
        self.assertEqual(idx.idf.get('neverseen'), 2.0)

    def test_the_rare_word_counts_more_than_the_common_one(self):
        idx = core.Index([E(1, 'Lux Beauty Soap', ''), E(2, 'Dettol Soap', ''), E(3, 'Medimix Soap', ''), E(4, 'Lifebuoy Soap', '')])
        toks = core.tokens('lux')
        with_idf = core.score('lux', toks, 'Lux Beauty Soap', idx.idf)
        plain = core.score('lux', toks, 'Lux Beauty Soap')
        self.assertGreater(with_idf, plain)

    def test_a_brand_read_with_look_alike_characters_is_found(self):
        cat = [E(1, 'Lipton Tea', ''), E(2, 'Tapal Tea', '')]
        _t, r = core.rank('L1pt0n Tea', cat)
        self.assertEqual(r[0][1]['id'], 1)
        self.assertGreaterEqual(r[0][0], 85)
        self.assertTrue(core.is_confident(r[:5]))

    def test_confidence_of_a_word_scales_its_vote(self):
        text = 'dettal handwash junk words here more stuff padding text extra filler and more words'   # long: only word votes count
        toks = core.tokens(text)
        sure = core.score(text, toks, 'Dettol Handwash 250ml', None, {'dettal': 95, 'handwash': 95})
        unsure = core.score(text, toks, 'Dettol Handwash 250ml', None, {'dettal': 50, 'handwash': 50})
        unknown = core.score(text, toks, 'Dettol Handwash 250ml')
        self.assertGreater(sure, unsure)
        self.assertGreaterEqual(unknown, sure)           # no information = full trust (old behaviour)

    def test_a_shaky_word_may_differ_a_little_more(self):
        text = 'lxptn junk words here more stuff padding text extra'      # long text: only the word votes count
        toks = core.tokens(text)
        self.assertEqual(core.score(text, toks, 'Lipton'), 0)               # 0.73 similar: not enough normally
        self.assertGreaterEqual(core.score(text, toks, 'Lipton', None, {'lxptn': 50}), 45)
        self.assertEqual(core.score(text, toks, 'Lipton', None, {'lxptn': 90}), 0)   # a sure read must be closer

    def test_parse_wconf(self):
        p = core.parse_wconf
        self.assertEqual(p('lux:92,soap:61'), {'lux': 92, 'soap': 61})
        self.assertEqual(p('a1:150,b2:-5,c3:inf,d4:nan,e5,:7,f6:x'), {'a1': 100, 'b2': 0})
        self.assertEqual(p('lux:90,lux:40'), {'lux': 40})                   # the weaker read of a repeated word
        self.assertEqual(p('1.5ltr:80'), {'1': 80, '5ltr': 80})
        self.assertEqual(p(''), {})
        self.assertEqual(p(None), {})
        self.assertEqual(len(p(','.join('w%d:50' % i for i in range(200)))), core.MAX_WCONF)

    def test_a_huge_number_before_a_unit_cannot_break_the_scan(self):
        self.assertEqual(core.quantities('9' * 400 + 'ml'), [])
        self.assertEqual(core.quantities('1234567890ml'), [])
        self.assertEqual(core.quantities('250ml'), ['v250'])
        self.assertEqual(core.rank('sunsilk shampoo ' + '9' * 400 + 'ml', CATALOG)[1][0][1]['id'] in (1, 2), True)

    def test_rescore_equals_rank_with_idf_and_confidence(self):
        idx = core.Index(CATALOG)
        w = {'sunsilk': 90, 'shampo0': 40, '180ml': 70}
        text = 'Sunsilk Shampo0 180ml'
        _t, ranked = core.rank(text, idx, w)
        _t2, again = core.rescore(text, CATALOG, idx.idf, w)
        self.assertEqual([(s, e['id']) for s, e in ranked], [(s, e['id']) for s, e in again])

    def test_without_catalog_context_scores_are_the_old_ones(self):
        # score() with no idf / wconf is exactly the v2 rule (equal weights, no confidence)
        self.assertEqual(core.score('lux soap', core.tokens('lux soap'), 'Lux Soap'), 92)
        self.assertEqual(core.score('', [], 'Lux Soap'), 0)


class WiringDTests(unittest.TestCase):
    def test_server_reads_wc_and_rescores_with_the_catalog_table(self):
        src = read_source('app/views_frontend/pos_sales/ocr.py')
        self.assertIn("core.parse_wconf(", src)
        self.assertIn("_catalog().idf, wconf", src)
        self.assertIn("rank_products(raw, wconf)", src)

    def test_both_pages_send_the_word_confidence(self):
        for rel in ('templates/sales/pos.html',):
            page = read_source(rel)
            for needle in ('function ocrWordConf(', 'function ocrWcParam(', 'ocrWcParam(meta.wc)',
                           'OcrMatch.Local.rank(text, meta.wc)', "{ source: 'camera', conf: r.conf, wc: r.wc }",
                           "{ source: 'photo', conf: r.conf, wc: r.wc }"):
                self.assertIn(needle, page, rel + ': ' + needle)


class WiringCTests(unittest.TestCase):
    """v5 wiring: new endpoints, dashboard, and the page features exist and point at each other."""

    def read(self, rel):
        return read_source(rel)

    def test_urls_and_views_exist(self):
        urls, view = self.read('app/urls.py'), self.read('app/views_frontend/pos_sales/ocr.py')
        for name in ('ocr_catalog', 'ocr_details', 'ocr_dashboard', 'ocr_alias_action'):
            self.assertIn('views_frontend.%s' % name, urls)
            self.assertIn('def %s(' % name, view)
        ast.parse(view)

    def test_details_never_trusts_phone_scores(self):
        view = self.read('app/views_frontend/pos_sales/ocr.py')
        body = view[view.index('def ocr_details('):]
        self.assertIn('core.rescore', body)
        self.assertNotIn("GET.get('scores')", body)

    def test_dashboard_template_and_permissions(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'templates/sales/ocr_dashboard.html')))
        view = self.read('app/views_frontend/pos_sales/ocr.py')
        self.assertIn("@perm_required('manage_inventory')\n@require_POST\ndef ocr_alias_action", view)

    def test_page_features(self):
        page = self.read('templates/sales/pos.html')
        for needle in ('ocrFeedback(', 'ocrUndo()', 'ocrBump(', 'ocrRequest(', '/ajax/ocr-details/', 'ocrPrep(',
                       'ocrAssistLight(', 'ocrAssistZoom(', 'ocrSceneBreak', "static 'ocr/ocr_match.js'",
                       "static 'ocr/ocr_prep.js'"):
            self.assertIn(needle, page, needle)
        for rel in ('static/ocr/ocr_match.js', 'static/ocr/ocr_prep.js'):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)


if __name__ == '__main__':
    unittest.main()
