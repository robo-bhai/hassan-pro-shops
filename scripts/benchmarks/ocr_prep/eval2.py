import json, os, re, subprocess, sys, difflib, csv, io, time
from concurrent.futures import ThreadPoolExecutor
D, OUT = sys.argv[1], sys.argv[2]
meta = json.load(open(os.path.join(D, 'meta.json'))); info = json.load(open(os.path.join(OUT, 'info.json')))
combos = [c.split(':') for c in sys.argv[3].split(',')]     # variant:pass:psm  e.g. full:gray:6
def norm(t): return re.sub(r'[^a-z0-9]+', ' ', t.lower()).split()
def tess(path, psm):
    r = subprocess.run(['tesseract', path, 'stdout', '--psm', str(psm), '-c', 'preserve_interword_spaces=1', '--dpi', '300', 'tsv'], capture_output=True, text=True)
    words, confs = [], []
    for row in csv.reader(io.StringIO(r.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
        if len(row) >= 12 and row[0] != 'level' and row[11].strip() and float(row[10]) >= 45: words.append(row[11]); confs.append(float(row[10]))
    return ' '.join(words), (sum(confs)/len(confs) if confs else 0)
def score(gt, got):
    g, o = norm(gt), norm(got); hit = 0
    for w in g: hit += 1 if any(difflib.SequenceMatcher(None, w, x).ratio() >= .99 for x in o) else 0
    return hit/len(g), difflib.SequenceMatcher(None, ' '.join(g), ' '.join(o)).ratio()
print(f"{'variant':8s} {'pass':5s} psm  recall  sim    ms/img(batch)")
for var, ps, psm in combos:
    def job(m):
        t, c = tess(os.path.join(OUT, f"{m['id']}.{ps}.{var}.pgm"), psm); return score(m['gt'], t)
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(job, meta))
    lst = os.path.join(OUT, 'list.txt'); open(lst, 'w').write('\n'.join(os.path.abspath(os.path.join(OUT, f"{m['id']}.{ps}.{var}.pgm")) for m in meta))
    t0 = time.perf_counter(); subprocess.run(['tesseract', lst, '/tmp/lst_out', '--psm', psm, '-c', 'preserve_interword_spaces=1', '--dpi', '300'], capture_output=True, env=dict(os.environ, OMP_THREAD_LIMIT='1')); dt = (time.perf_counter()-t0)*1000/len(meta)
    n = len(res); print(f"{var:8s} {ps:5s} {psm:3s}  {100*sum(r[0] for r in res)/n:5.1f}%  {100*sum(r[1] for r in res)/n:5.1f}%  {dt:6.1f}")
