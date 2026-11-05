"""Matcher accuracy on synthetic camera reads: old rule (v2: equal words, no look-alikes) vs the current ocr_core.py.

    python3 scripts/benchmarks/ocr_match/bench.py [path/to/old_ocr_core.py]

Makes a catalog of brand + product + size names (several sizes of the same product, so size matters), then 3000 noisy
"camera reads" of random products: look-alike swaps (0/o 1/l 5/s 8/b), dropped / wrong letters, packaging words, and
a made-up per-word confidence (wrong letters get low confidence, like Tesseract does). Prints for each version:
  top-1 right   : the first product shown is the one on the pack
  top-3 right   : it is among the first three
  auto-add      : how often the page would add the first product by itself
  auto-add WRONG: ... and it was the wrong product (this is the number that hurts - keep it low)
Synthetic data is no substitute for real packs: judge the direction, then check the dashboard on real scans.
"""
import importlib.util
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BRANDS = ('Sunsilk Lux Dettol Tapal Shan National Dalda Lipton Nestle Olpers Knorr Safeguard Colgate Pepsodent '
          'Ariel Pantene Vim Lifebuoy Medimix Hamdard Mezan Gourmet Tang Rafhan Eveready Bonus').split()
KINDS = ('Shampoo Soap Handwash Tea Masala Rice Oil Milk Toothpaste Syrup Biscuit Noodles Detergent Ghee Juice '
         'Conditioner Cream Lotion').split()
SIZES = ['90ml', '180ml', '250ml', '500ml', '1L', '200g', '500g', '1kg', '5kg']
LOOK = {'o': '0', 'l': '1', 's': '5', 'b': '8', 'i': '1', 'z': '2'}
JUNK = ['MRP Rs 250', 'mfg date', 'best before', 'net wt', 'made in pakistan', 'new pack']


def make_catalog(core, seed=5):
    rnd = random.Random(seed)
    names = set()
    while len(names) < 1200:
        names.add('%s %s %s' % (rnd.choice(BRANDS), rnd.choice(KINDS), rnd.choice(SIZES)))
        if rnd.random() < 0.25:                                  # same product in a second size
            b, k, _s = list(names)[-1].split(' ', 2)
            names.add('%s %s %s' % (b, k, rnd.choice(SIZES)))
    names = sorted(names)
    return [core.make_entry(i + 1, n, '') for i, n in enumerate(names)]


def noisy_read(name, rnd):
    """-> (text, {word: confidence})"""
    words, wconf = [], {}
    for w in name.split():
        chars, bad = list(w), False
        for _ in range(rnd.choice([0, 0, 1, 1, 2])):
            if len(chars) < 3:
                break
            i = rnd.randrange(len(chars))
            op = rnd.choice('lldsx')
            c = chars[i].lower()
            if op in 'l' and c in LOOK:
                chars[i] = LOOK[c]
            elif op == 'd':
                del chars[i]
            elif op == 's':
                chars[i] = rnd.choice('abcdefghkmnprtuvw')
            else:
                chars.insert(i, rnd.choice('aeiou'))
            bad = True
        out = ''.join(chars)
        words.append(out)
        wconf[out.lower()] = rnd.randint(35, 62) if bad else rnd.randint(78, 99)
    if rnd.random() < 0.4:
        words.append(rnd.choice(JUNK))
    return ' '.join(words), wconf


def run(core, cat, reads, with_conf):
    idx = core.Index(cat)
    r1 = r3 = auto = wrong = found = 0
    for want, text, wconf in reads:
        try:
            _t, ranked = core.rank(text, idx, wconf if with_conf else None)
        except TypeError:                                         # the old module has no wconf argument
            _t, ranked = core.rank(text, idx)
        top = ranked[:5]
        ids = [e['id'] for _s, e in top]
        found += bool(ids)
        r1 += ids[:1] == [want]
        r3 += want in ids[:3]
        if core.is_confident(top):
            auto += 1
            wrong += ids[0] != want
    n = len(reads)
    return {'top-1 right': 100.0 * r1 / n, 'top-3 right': 100.0 * r3 / n, 'auto-add': 100.0 * auto / n,
            'auto-add WRONG': 100.0 * wrong / n, 'auto-add precision': 100.0 * (auto - wrong) / max(1, auto)}


def main():
    new = load(os.path.join(ROOT, 'app/utils/pos/ocr_core.py'), 'new_core')
    old_path = sys.argv[1] if len(sys.argv) > 1 else None
    rnd = random.Random(99)
    cat_new = make_catalog(new)
    reads = []
    for _ in range(3000):
        e = rnd.choice(cat_new)
        text, wc = noisy_read(e['name'], rnd)
        reads.append((e['id'], text, wc))
    rows = []
    if old_path:
        old = load(old_path, 'old_core')
        rows.append(('old (v2)', run(old, make_catalog(old), reads, False)))
    rows.append(('new', run(new, cat_new, reads, False)))
    rows.append(('new + word confidence', run(new, cat_new, reads, True)))
    keys = ['top-1 right', 'top-3 right', 'auto-add', 'auto-add WRONG', 'auto-add precision']
    print('%-24s' % '' + ''.join('%20s' % k for k in keys))
    for name, r in rows:
        print('%-24s' % name + ''.join('%19.1f%%' % r[k] for k in keys))


if __name__ == '__main__':
    main()
