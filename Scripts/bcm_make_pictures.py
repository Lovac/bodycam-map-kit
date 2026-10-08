"""Any picture -> the two sizes a Bodycam card needs (22 Sep 2026, for Scripts/newmap.sh).

    python bcm_make_pictures.py <any .png/.jpg> <output folder>
      card_2048x1024.png   the map card in the game's menu
      thumb.png            1024x512, the picture in the installer window

Centre-cropped to 2:1 first, so a 16:9 screenshot and a phone photo both come out right.
"""
import os
import sys

from PIL import Image

src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert('RGB')
w, h = im.size
WANT = 2.0
if w / float(h) > WANT:
    nw = int(round(h * WANT))
    im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
elif w / float(h) < WANT:
    nh = int(round(w / WANT))
    im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
os.makedirs(out, exist_ok=True)
im.resize((2048, 1024), Image.LANCZOS).save(os.path.join(out, 'card_2048x1024.png'))
im.resize((1024, 512), Image.LANCZOS).save(os.path.join(out, 'thumb.png'))
print('   picture %dx%d -> card 2048x1024 + thumb 1024x512' % (w, h))
