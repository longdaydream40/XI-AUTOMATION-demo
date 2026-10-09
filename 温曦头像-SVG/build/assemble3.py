# -*- coding: utf-8 -*-
import pickle, json, os, numpy as np
D=pickle.load(open('src/layers3.pkl','rb'))
S=D.get('SCALE',1)
FACE=np.load('src/FACE.npy')
import os as _os
RED_LEVELS=[float(v) for v in _os.environ.get('RED_LEVELS','0.5,0.7,0.9').split(',')]
groups=D['groups']; W=D['W']; H=D['H']; ink_red=D['ink_red']
redhex='#%02x%02x%02x'%tuple(int(round(v)) for v in ink_red)
META=[('face','face','面部（可见侧脸）','face.profile','被头发围合、未被遮挡的侧脸区域：额头—眉弓—鼻梁—鼻尖—人中—唇—下巴—下颌。'),
      ('hair-crown','haircrown','颅顶发','hair.crown','头顶主发流，自发旋向左右分股。'),
      ('hair-bang','hairbang','刘海','hair.bangs','覆于额前、自右上向左下散开的刘海束。'),
      ('hair-back','hairback','后脑发','hair.back','后脑一侧的整块发量。'),
      ('hair-side','hairsidelock','脸侧垂发','hair.sidelock','贴脸垂落的一束，遮住耳际，内侧即面部轮廓线。'),
      ('hair-tips-left','hairtipsleft','左侧发尾','hair.tips.left','左下缘一排向外翘起的参差发尾（尖角发梢）。'),
      ('hair-tips-bottom','hairtipsbottom','下缘发尾','hair.tips.bottom','底缘一排向下的尖角发尾。'),
      ('hair-tail','hairtail','长垂发','hair.tail','颈侧向下延伸、末端收细的一缕长发。'),
      ('hair-rest','hairrest','发块余部','hair.misc','未被细分规则命中的发丝余部。'),
      ('hair-clip','hairclip','红色发夹','accessory.hairclip','红色 K 形发夹：上下两道平行斜条，右侧一个「>」；置于头发之上，墨色 %s。')]
IDM={m[0]:m for m in META}
order=[m[0] for m in META]
def mask_paths(L):
    out=[]
    for C,ds in L:
        if not ds: continue
        v=int(round(C*255)); out.append('<path fill="#%02x%02x%02x" d="%s"/>'%(v,v,v,' '.join(ds)))
    return out
A=[];P=A.append
P('<?xml version="1.0" encoding="UTF-8"?>')
P('<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-labelledby="wensi-title wensi-desc" data-artwork="wensi-side-profile">'%(W,H,W,H))
P('<title id="wensi-title">温曦 · 侧颜头像（白发 / 红色发夹）</title>')
P('<desc id="wensi-desc">分层矢量重绘的侧颜头像。全部图形按语义区块分组：头发（颅顶/刘海/后脑/脸侧垂发/两侧发尾/长垂发）、面部、红色发夹。</desc>')
P('<metadata id="wensi-regions">%s</metadata>'%json.dumps(dict(
  version=1,canvas=[W,H],compositing='luminance-mask',levels=dict(gray=D['N_GRAY'],red=RED_LEVELS,supersample=S,
    tracer=dict(engine='potrace 1.16',alphamax=D.get('AMAX','0.5'),turdsize=D.get('TURD','0'))),
  ink_gray='#000000',ink_red=redhex,
  face_profile_guide=[[int(np.nonzero(FACE[y])[0].max()),int(y)] for y in range(0,H,16) if FACE[y].any()],
  regions=[dict(id=i,box=b,label_zh=z,semantic=s,note=(n%redhex if '%s' in n else n)) for i,(_,b,z,s,n) in enumerate(META)]),
  ensure_ascii=False,separators=(',',':')))
P('<g id="wensi-head" data-semantic="head" data-label="温曦头像">')
for nm in order:
    G=[g for g in groups if g[0]==nm]
    if not G: continue
    _,kind,L=G[0]
    _,box,z,sem,note=IDM[nm]
    P('  <g id="%s" data-semantic="%s" data-label="%s">'%(box,sem,z))
    P('    <title>%s</title><desc>%s</desc>'%(z,note%redhex if '%s' in note else note))
    P('    <mask id="%s-m" maskUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d">'%(box,W,H))
    P('      <g transform="translate(0,%d) scale(%.8f,-%.8f)" data-levels="%d">'%(H,0.1/S,0.1/S,len(L)))
    for l in mask_paths(L): P('        '+l)
    P('      </g></mask>')
    P('    <rect x="0" y="0" width="%d" height="%d" fill="%s" mask="url(#%s-m)"/>'%(W,H,'#000000' if kind=='gray' else redhex,box))
    P('  </g>')
P('</g>')
P('</svg>')
svg='\n'.join(A); os.makedirs('out',exist_ok=True)
open('out/wensi-head.svg','w',encoding='utf-8').write(svg)
print('bytes %.2f MB  paths %d'%(len(svg)/1048576,svg.count('<path')))
