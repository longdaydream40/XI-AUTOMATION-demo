# -*- coding: utf-8 -*-
import numpy as np, re, subprocess, os, json, time, pickle
from PIL import Image, ImageFilter
from collections import deque
MODE=os.environ.get('MODE','mask')
N_GRAY=int(os.environ.get('N_GRAY',64)); N_RED=int(os.environ.get('N_RED',48))
T0G=float(os.environ.get('T0G','0.004')); T0R=float(os.environ.get('T0R','0.012'))
TURD=os.environ.get('TURD','0'); AMAX=os.environ.get('AMAX','0.5')
RED_LEVELS=[float(v) for v in os.environ.get('RED_LEVELS','0.5,0.7,0.9').split(',')]
SCALE=int(os.environ.get('SCALE','1'))
SRC='/home/xuan/设计/20261008033832-a5acfa84-image-1.png'; W=H=1254; TMP='tmp'
t0=time.time()
src=np.asarray(Image.open(SRC).convert('RGBA')).astype(np.float64)
R,G,B,AL=src[...,0],src[...,1],src[...,2],src[...,3]
al=AL/255.0
comp=np.stack([R*al+255*(1-al),G*al+255*(1-al),B*al+255*(1-al)],-1)
chroma=R-np.maximum(G,B); core=(chroma>80)&(AL>230)
ink_red=comp[core].mean(0); d=255.0-ink_red
u=255.0-comp
a11=3*255.0*255.0; a12=255.0*d.sum(); a22=float((d*d).sum())
b1=u.sum(-1)*255.0; b2=(u*d).sum(-1); det=a11*a22-a12*a12
g=np.clip((b1*a22-b2*a12)/det,0,1); r=np.clip((a11*b2-a12*b1)/det,0,1)

# ---- 发夹范围：红色场最大连通块，外扩 3px（保留羽化边） ----
seed=(r>0.05); seen=np.zeros_like(seed); q=deque(); best=None
ys,xs=np.nonzero(seed)
for y0,x0 in zip(ys,xs):
    if seen[y0,x0]: continue
    q=deque([(y0,x0)]); seen[y0,x0]=True; pts=[]
    while q:
        y,x=q.popleft(); pts.append((y,x))
        for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
            yy,xx=y+dy,x+dx
            if 0<=yy<H and 0<=xx<W and seed[yy,xx] and not seen[yy,xx]: seen[yy,xx]=True; q.append((yy,xx))
    if best is None or len(pts)>len(best): best=pts
CLIPZONE=np.zeros((H,W),bool)
for y,x in best: CLIPZONE[y,x]=True
CLIPZONE=np.asarray(Image.fromarray((CLIPZONE*255).astype('uint8')).filter(ImageFilter.MaxFilter(7)))>0
print('clip zone',int(CLIPZONE.sum()),'r>0.05 total',int(seed.sum()))

# ---- 可见侧脸 ----
low=(g>0.02)|(r>0.3); outside=np.zeros_like(low,bool); q=deque()
for x in range(W):
    for y in (0,H-1):
        if not low[y,x] and not outside[y,x]: outside[y,x]=True; q.append((y,x))
for y in range(H):
    for x in (0,W-1):
        if not low[y,x] and not outside[y,x]: outside[y,x]=True; q.append((y,x))
while q:
    y,x=q.popleft()
    for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
        yy,xx=y+dy,x+dx
        if 0<=yy<H and 0<=xx<W and not low[yy,xx] and not outside[yy,xx]: outside[yy,xx]=True; q.append((yy,xx))
holes=~low&~outside; FACE=np.zeros_like(holes); sy,sx=700,950
q=deque([(sy,sx)]); FACE[sy,sx]=True
while q:
    y,x=q.popleft()
    for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
        yy,xx=y+dy,x+dx
        if 0<=yy<H and 0<=xx<W and holes[yy,xx] and not FACE[yy,xx]: FACE[yy,xx]=True; q.append((yy,xx))

ys=np.arange(H)[:,None]*np.ones((1,W)); xs=np.ones((H,1))*np.arange(W)[None,:]
def xline(p):
    py=np.array([q[1] for q in p],float); px=np.array([q[0] for q in p],float)
    return np.interp(np.arange(H),py,px,left=px[0],right=px[-1])[None,:]
A=xline([(630,40),(500,220),(400,340),(330,470),(300,600),(290,660),(285,1260)])
Bl=xline([(770,40),(850,210),(915,340),(940,480),(950,620),(955,1260)])
hair=(g>T0G)
REG=[('face',FACE),('hair-tail',(ys>975)&(xs>690)),('hair-side',(xs>720)&(ys>=535)&(ys<=935)),
     ('hair-tips-left',(ys>610)&(xs<430)),('hair-tips-bottom',(ys>615)&(xs>=430)),
     ('hair-bang',(xs>Bl)&(ys<=615)),('hair-back',(xs<=A)&(ys<=615)),
     ('hair-crown',(xs>A)&(xs<=Bl)&(ys<=615)),('hair-rest',np.ones_like(hair))]
labmap=np.zeros((H,W),np.uint8)
for i,(nm,m) in enumerate(REG): labmap[(m)&(hair|FACE)&(labmap==0)]=i+1
labmap[FACE]=1
np.save('src/labmap.npy',labmap); np.save('src/g.npy',g); np.save('src/r.npy',r)
np.save('src/ink_red.npy',ink_red); np.save('src/FACE.npy',FACE); np.save('src/CLIPZONE.npy',CLIPZONE)

def upsample(field,S):
    if S==1: return field
    im=Image.fromarray(np.clip(field*65535,0,65535).astype('uint16'))
    return np.asarray(im.resize((W*S,H*S),Image.BILINEAR)).astype(np.float64)/65535.0
def trace(mask):
    if not mask.any(): return []
    h,w=mask.shape
    open(TMP+'/x.pbm','wb').write(b'P4\n%d %d\n'%(w,h)+np.packbits(mask,axis=1).tobytes())
    subprocess.run(['potrace','-b','svg','-t',TURD,'-a',AMAX,'-o',TMP+'/x.svg',TMP+'/x.pbm'],check=True)
    return re.findall(r'<path d="([^"]+)"',open(TMP+'/x.svg').read())
def build_levels(field,levels,mask,scale=1):
    res=[]
    for v in levels:
        res.append((v,trace_level(field,v,mask,scale)))
    return res
def build_layers(field,t0,tmax,n,mask):
    gap=(tmax-t0)/n; C=[t0+(k-0.5)*gap for k in range(1,n+1)]; res=[]
    FU=upsample(field,SCALE)
    MU=np.asarray(Image.fromarray((mask*255).astype('uint8')).resize((W*SCALE,H*SCALE),Image.NEAREST))>0
    for k in range(1,n+1):
        T=t0+(k-1)*gap
        res.append((C[k-1],trace((FU>=T)&MU)))
    return res
def trace_level(field,v,mask,scale=1):
    FU=upsample(field,scale)
    MU=np.asarray(Image.fromarray((mask*255).astype('uint8')).resize((W*scale,H*scale),Image.NEAREST))>0 if scale>1 else mask
    return trace((FU>=v)&MU)

GMAX=float(g.max()); RMAX=float(r[CLIPZONE].max())
groups=[]
for i,(nm,m) in enumerate(REG):
    reg=(labmap==i+1)
    if not reg.any(): continue
    groups.append((nm,'gray',build_layers(g,T0G,GMAX,N_GRAY,reg)))
groups.append(('hair-clip','red',build_levels(r,RED_LEVELS,CLIPZONE,SCALE)))
pickle.dump(dict(groups=groups,W=W,H=H,ink_red=ink_red.tolist(),N_GRAY=N_GRAY,N_RED=N_RED,
                 T0G=T0G,T0R=T0R,GMAX=GMAX,RMAX=RMAX,MODE=MODE,AMAX=AMAX,TURD=TURD,SCALE=SCALE),
            open('src/layers3.pkl','wb'))
print('SCALE',SCALE)
print('built in %.1fs  GMAX=%.4f RMAX=%.3f'%(time.time()-t0,GMAX,RMAX))
