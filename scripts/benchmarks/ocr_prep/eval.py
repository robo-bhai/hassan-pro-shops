import json, os, re, subprocess, sys, difflib, csv, io
from concurrent.futures import ThreadPoolExecutor
D, OUT = sys.argv[1], sys.argv[2]
meta = json.load(open(os.path.join(D, 'meta.json')))
PASSES = [('gray', 6), ('bin', 11), ('inv', 6)]
def norm(t): return re.sub(r'[^a-z0-9]+', ' ', t.lower()).split()
def tess(path, psm):
    r = subprocess.run(['tesseract', path, 'stdout', '--psm', str(psm), '-c', 'preserve_interword_spaces=1', '--dpi', '300', 'tsv'], capture_output=True, text=True)
    words, confs = [], []
    for row in csv.reader(io.StringIO(r.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
        if len(row) >= 12 and row[0] != 'level' and row[11].strip() and float(row[10]) >= 45:
            words.append(row[11]); confs.append(float(row[10]))
    return ' '.join(words), (sum(confs)/len(confs) if confs else 0)
def score(gt, got):
    g, o = norm(gt), norm(got)
    if not g: return 0, 0
    hit = 0
    for w in g:
        b = max([difflib.SequenceMatcher(None, w, x).ratio() for x in o] or [0])
        hit += 1 if b >= 0.99 else 0
    sim = difflib.SequenceMatcher(None, ' '.join(g), ' '.join(o)).ratio()
    return hit / len(g), sim
def job(m):
    res = {}
    for name, psm in PASSES:
        txt, conf = tess(os.path.join(OUT, f"{m['id']}.{name}.pgm"), psm)
        letters = len(re.findall(r'[a-z]', txt.lower()))
        res[name] = (txt, conf, letters)
    # page logic (force): best confidence with >=4 letters
    cands = [(v[1], k) for k, v in res.items() if v[2] >= 4]
    best = max(cands)[1] if cands else None
    txt = res[best][0] if best else ''
    rec, sim = score(m['gt'], txt)
    # oracle: best of all passes by truth (shows headroom)
    orc = max([score(m['gt'], v[0])[0] for v in res.values()])
    return m['id'], m['cond'], rec, sim, orc, best
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(job, meta))
by = {}
for _id, c, rec, sim, orc, best in rows: by.setdefault(c, []).append((rec, sim, orc))
print(f"{'condition':12s} word-recall  char-sim  (oracle recall)")
allr = []
for c, v in by.items():
    n = len(v); print(f"{c:12s} {100*sum(x[0] for x in v)/n:6.1f}%    {100*sum(x[1] for x in v)/n:6.1f}%   {100*sum(x[2] for x in v)/n:6.1f}%"); allr += v
n = len(allr); print(f"{'ALL':12s} {100*sum(x[0] for x in allr)/n:6.1f}%    {100*sum(x[1] for x in allr)/n:6.1f}%   {100*sum(x[2] for x in allr)/n:6.1f}%")
json.dump(rows, open(OUT + '.json', 'w'))
