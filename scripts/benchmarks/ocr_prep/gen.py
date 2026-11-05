import json, os, random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
random.seed(7); np.random.seed(7)
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
B = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
R = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
S = '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'
LABELS = [
 ("Pepsi Cola", "250 ml"), ("Dettol Original Soap", "125 g"), ("Shan Biryani Masala", "50 g"),
 ("Dalda Cooking Oil", "1 litre"), ("Surf Excel Washing Powder", "500 g"), ("Olpers Full Cream Milk", "1 litre"),
 ("National Tomato Ketchup", "800 g"), ("Lipton Yellow Label Tea", "190 g"), ("Colgate Total Toothpaste", "75 g"),
 ("Nestle Pure Water", "1.5 litre"), ("Tapal Danedar Chai", "430 g"), ("Rafhan Corn Flour", "275 g"),
]
SCHEMES = [((255,255,255),(20,20,20)), ((250,215,40),(120,10,10)), ((200,30,40),(255,255,255)),
           ((20,40,110),(255,255,255)), ((235,235,225),(10,70,30)), ((25,25,25),(240,240,240))]
def make(name, size, scheme, font):
    bg, fg = scheme
    im = Image.new('RGB', (800, 300), bg); d = ImageDraw.Draw(im)
    f1 = ImageFont.truetype(font, 58 if len(name) < 20 else 46); f2 = ImageFont.truetype(R, 36)
    words = name.split(); lines = []; cur = ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=f1) > 720 and cur: lines.append(cur); cur = w
        else: cur = t
    lines.append(cur)
    y = 40
    for ln in lines:
        d.text((40, y), ln, font=f1, fill=fg); y += 70
    d.text((40, y + 10), size, font=f2, fill=fg)
    return im
def shadow(a):
    h, w = a.shape[:2]; xx, yy = np.meshgrid(np.linspace(0,1,w), np.linspace(0,1,h))
    g = 0.30 + 0.70 * np.clip(1.15 - (xx*0.9 + yy*0.4), 0, 1)
    blob = 1 - 0.35*np.exp(-(((xx-0.7)**2)/0.02 + ((yy-0.6)**2)/0.08))
    return a * (g*blob)[..., None]
def glare(a):
    h, w = a.shape[:2]; xx, yy = np.meshgrid(np.arange(w), np.arange(h))
    g = np.exp(-(((xx-520)**2)/(2*70**2) + ((yy-110)**2)/(2*45**2)))
    return a + 230*g[..., None]
def noise(a, s=22): return a + np.random.normal(0, s, a.shape)
def tilt(im, deg):
    bg = im.getpixel((2,2)); return im.rotate(-deg, resample=Image.BICUBIC, fillcolor=bg)  # PIL: +deg = CCW; we want +deg = down-right
def lowc(a): return a*0.38 + 150*0.62
def blur(im, r): return im.filter(ImageFilter.GaussianBlur(r))
def jpeg(im, q, path):
    im.save(path + '.jpg', quality=q); return Image.open(path + '.jpg').convert('RGB')
CONDS = {
 'clean':      lambda im: im,
 'shadow':     lambda im: Image.fromarray(np.clip(shadow(np.asarray(im, float)),0,255).astype('uint8')),
 'tilt8':      lambda im: tilt(im, 8),
 'tilt-11':    lambda im: tilt(im, -11),
 'noise':      lambda im: Image.fromarray(np.clip(noise(np.asarray(im,float)),0,255).astype('uint8')),
 'blur':       lambda im: blur(im, 2.4),
 'glare':      lambda im: Image.fromarray(np.clip(glare(np.asarray(im,float)),0,255).astype('uint8')),
 'lowcontrast':lambda im: Image.fromarray(np.clip(lowc(np.asarray(im,float)),0,255).astype('uint8')),
 'combo':      lambda im: Image.fromarray(np.clip(noise(shadow(np.asarray(blur(tilt(im,6),1.4),float)),14),0,255).astype('uint8')),
}
meta = []
k = 0
for li, (name, size) in enumerate(LABELS):
    sch = SCHEMES[li % len(SCHEMES)]
    base = make(name, size, sch, B if li % 3 else S)
    for cn, fn in CONDS.items():
        im = fn(base)
        if cn in ('noise','combo','shadow'): im = jpeg(im, 45, os.path.join(OUT, '_t'))
        a = np.asarray(im.convert('RGBA'), dtype=np.uint8)
        fid = f'{li:02d}_{cn}'
        a.tofile(os.path.join(OUT, fid + '.rgba')); im.save(os.path.join(OUT, fid + '.png'))
        meta.append({'id': fid, 'w': a.shape[1], 'h': a.shape[0], 'gt': name + ' ' + size, 'cond': cn, 'dark': sch == SCHEMES[5] or sch == SCHEMES[2] or sch == SCHEMES[3]})
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'))
print(len(meta), 'images')
