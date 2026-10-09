# -*- coding: utf-8 -*-
import numpy as np, subprocess, sys, os
from PIL import Image
SRC='/home/xuan/设计/20261008033832-a5acfa84-image-1.png'
svg=sys.argv[1]; tag=os.path.splitext(os.path.basename(svg))[0]
os.makedirs('out/verify',exist_ok=True)
s=np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float64)
al=s[...,3:4]/255.0
ref=s[...,:3]*al+255*(1-al)
subprocess.run(['rsvg-convert','-w','1254','-h','1254','-b','white','-o','out/verify/%s.png'%tag,svg],check=True)
got=np.asarray(Image.open('out/verify/%s.png'%tag).convert('RGBA')).astype(np.float64)
gal=got[...,3:4]/255.0
gt=got[...,:3]*gal+255*(1-gal)
d=np.abs(gt-ref).max(-1)
print('== %s  (%.2f MB)'%(svg,os.path.getsize(svg)/1048576))
print('   RMSE=%.4f  MAE=%.4f  P99=%.3f  P99.9=%.3f  MAX=%.1f   PSNR=%.2f dB'%(
   np.sqrt((d**2).mean()),d.mean(),np.quantile(d,0.99),np.quantile(d,0.999),d.max(),
   20*np.log10(255/max(np.sqrt((d**2).mean()),1e-9))))
for thr in (1,2,3,5,10,20):
    print('   |diff|>%2d : %7d px  %.4f%%'%(thr,int((d>thr).sum()),float((d>thr).mean())*100))
hm=np.clip(d*8,0,255).astype('uint8')
Image.fromarray(255-hm).save('out/verify/%s-diffmap.png'%tag)
np.save('tmp/refrgb.npy',ref); np.save('tmp/gotrgb.npy',gt)
