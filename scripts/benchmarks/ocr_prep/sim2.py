import json, os, re, subprocess, csv, io, difflib
from concurrent.futures import ThreadPoolExecutor
D='data'
meta=json.load(open(D+'/meta.json'))
def norm(t): return re.sub(r'[^a-z0-9]+',' ',t.lower()).split()
def run(var,ps,psm,m):
    OUT='out_old' if var=='old' else 'out2'
    r=subprocess.run(['tesseract',f"{OUT}/{m['id']}.{ps}.{'full' if var=='old' else var}.pgm",'stdout','--psm',str(psm),'-c','preserve_interword_spaces=1','--dpi','300','tsv'],capture_output=True,text=True)
    w,c=[],[]
    for row in csv.reader(io.StringIO(r.stdout),delimiter='\t',quoting=csv.QUOTE_NONE):
        if len(row)>=12 and row[0]!='level' and row[11].strip() and float(row[10])>=45: w.append(row[11]); c.append(float(row[10]))
    txt=' '.join(w); return txt,(sum(c)/len(c) if c else 0),len(re.findall('[a-z]',txt.lower()))
def score(gt,got):
    g,o=norm(gt),norm(got); hit=sum(1 for w in g if any(difflib.SequenceMatcher(None,w,x).ratio()>=.99 for x in o))
    return hit/len(g), difflib.SequenceMatcher(None,' '.join(g),' '.join(o)).ratio()
P=[('old','gray',6),('old','bin',11),('old','inv',6),('full','gray',6),('full','bin',11),('crop','bin',6),('crop','bin',11),('crop','gray',6),('crop','inv',6),('full','inv',6)]
def job(m): return {f'{v}.{p}.{s}':run(v,p,s,m) for v,p,s in P}
with ThreadPoolExecutor(8) as ex: R=list(ex.map(job,meta))
COST={'old.gray.6':33,'old.bin.11':26.5,'old.inv.6':41,'full.gray.6':33,'full.bin.11':26.5,'crop.bin.6':27,'crop.bin.11':19,'crop.gray.6':29,'crop.inv.6':41,'full.inv.6':41}
PREP={'v1':2.5,'v2':16.0,'v3':10.0}
def flow(passes,quick,prep):
    rec=sim=cost=npass=0
    for m,r in zip(meta,R):
        best=None; cost+=prep
        for k in passes:
            t,c,l=r[k]; cost+=COST[k]; npass+=1
            if l>=4 and (best is None or c>best[1]): best=(t,c,l)
            if best and best[1]>=quick and best[2]>=6: break
        a,b=score(m['gt'],best[0]) if best else (0,0); rec+=a; sim+=b
    n=len(meta); return 100*rec/n,100*sim/n,cost/n,npass/n
for name,passes,prep in [('v1 original  (old prep, gray6>bin11)',['old.gray.6','old.bin.11'],PREP['v1']),
                         ('v2 (prev)    (new prep full, gray6>bin11)',['full.gray.6','full.bin.11'],PREP['v2']),
                         ('v3 (now)     (new prep crop, bin6>gray6)',['crop.bin.6','crop.gray.6'],PREP['v3'])]:
    rr=flow(passes,65,prep); print(f"{name:44s} recall {rr[0]:5.1f}%  sim {rr[1]:5.1f}%  ~{rr[2]:5.1f} ms/frame  passes {rr[3]:.2f}")
