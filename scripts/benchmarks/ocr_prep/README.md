# OCR picture-preparation benchmark (v1 vs v2)

Makes 108 synthetic product labels (12 products x 9 conditions: clean, shadow, tilt, noise, blur, glare, low contrast,
combined), runs both preparation versions, reads the result with the `tesseract` CLI exactly like the page does
(passes gray/psm6, bin/psm11, inv/psm6; best confidence wins) and prints word recall + character similarity.

```
cd scripts/benchmarks/ocr_prep
python3 gen.py data                                                   # needs Pillow + numpy
node run_prep.js ./ocr_prep_v1.js data out_v1                         # old
node run_prep.js ../../../static/ocr/ocr_prep.js data out_v2          # new
OMP_THREAD_LIMIT=1 python3 eval.py data out_v1 ; OMP_THREAD_LIMIT=1 python3 eval.py data out_v2
```
Needs `node` and `tesseract` (eng) installed. Synthetic labels are not a substitute for real photos: re-run with a
folder of your own packaging photos (same `meta.json` format) before changing thresholds in `CFG`.

## Speed / pass-order study (v3)
`run_prep2.js` writes full and text-box-cropped variants, `eval2.py` scores one (variant:pass:psm) per run and prints
ms/image (native tesseract, one process for the whole batch), `sim2.py` replays the page's early-exit logic.
Results on the 108 synthetic labels (native tesseract - Tesseract.js/wasm on a phone is much slower, so check the
"prep ... ms | read ... ms" line in the scan window's details panel on real devices):

| flow                                   | word recall | char sim | ms/frame (native) |
|----------------------------------------|-------------|----------|-------------------|
| v1 original (gray6 > bin11, full frame)|   66.2 %    |  92.3 %  |  36.5             |
| v2 (new prep, full frame)              |   71.1 %    |  96.3 %  |  49.2             |
| v3 (new prep, text-box crop, bin6 first)|  75.6 %    |  96.1 %  |  37.3             |

Findings: adaptive black/white is the best single pass (so it runs first); the inverted pass is the slowest and almost
never wins (last); unsharp mask gave no gain (off); Tesseract `tessedit_do_invert=0` / dictionary switches saved little
and cost accuracy (not used); shrinking the crop to a fixed text height lost ~3 points (not used).
