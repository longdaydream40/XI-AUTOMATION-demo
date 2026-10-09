# -*- coding: utf-8 -*-
"""几何校验：只量实体边缘的亚像素位置精度（对灰底免疫：用 R-G 色度定位红色边缘）"""
import numpy as np
ref=np.load('tmp/refrgb.npy'); got=np.load('tmp/gotrgb.npy')
def crossing(p,c):
    s=np.sign(p-c); idx=np.nonzero(np.diff(s)!=0)[0]; out=[]
    for i in idx:
        v0,v1=p[i],p[i+1]
        if v1!=v0: out.append(i+(c-v0)/(v1-v0))
    return out
chr_ref=ref[...,0]-ref[...,1]; chr_got=got[...,0]-got[...,1]
print('=== 1. 红色发夹实心条边缘（用色度 R-G 的 50% 位置，中位阈值）===')
tot=[];rows=range(430,640,10)
for y in rows:
    a=crossing(chr_ref[y],chr_ref.max()*0.5); b=crossing(chr_got[y],chr_got.max()*0.5)
    if len(a)==len(b) and len(a):
        d=[b[i]-a[i] for i in range(len(a))]; tot+=d
        if y%30==0: print('  y=%3d  源 %s  重绘 %s  Δ=%s'%(y,[round(v,2) for v in a],[round(v,2) for v in b],[round(v,3) for v in d]))
    elif len(a)!=len(b): print('  y=%3d  交叉数不同 源%d 重绘%d'%(y,len(a),len(b)))
if tot: print('  → 发夹边缘偏移：平均 %+.3f px  平均绝对 %.3f px  最大 %.3f px  (n=%d)'%(np.mean(tot),np.mean(np.abs(tot)),np.max(np.abs(tot)),len(tot)))
print()
def ink(a): return np.clip((255-(a@np.array([0.299,0.587,0.114])))/255.0,0,1)
ir,ig=ink(ref),ink(got)
def edges(p,th=0.05):
    idx=np.nonzero(p>=th)[0]
    if len(idx)==0: return None
    def sub(i,d):
        j=i-d
        if not(0<=j<len(p)) or p[i]==p[j]: return float(i)
        return j+(i-j)*(th-p[j])/(p[i]-p[j])
    return sub(idx[0],1),sub(idx[-1],-1)
print('=== 2. 整体轮廓（逐行 ink=0.05 亚像素交叉）===')
L=[];R=[]
for y in range(120,1100,20):
    a=edges(ir[y]); b=edges(ig[y])
    if a and b: L.append(b[0]-a[0]); R.append(b[1]-a[1])
print('  左缘：平均 %+.3f px  σ=%.3f  max|Δ|=%.3f'%(np.mean(L),np.std(L),np.max(np.abs(L))))
print('  右缘：平均 %+.3f px  σ=%.3f  max|Δ|=%.3f'%(np.mean(R),np.std(R),np.max(np.abs(R))))
print()
print('=== 3. 发丝暗线（ink>=0.12 的像素数与峰值位置）===')
for y in range(200,900,100):
    a=ir[y]; b=ig[y]
    pa=np.nonzero(a>=0.12)[0]; pb=np.nonzero(b>=0.12)[0]
    da=np.abs(b-a)
    print('  y=%3d  暗线像素 源%3d/重绘%3d  该行最大色差 %.3f (%.1f/255)'%(y,len(pa),len(pb),da.max(),da.max()*255))
print()
print('=== 4. 发丝暗线保有率（源 ink>=0.12 的像素中有多少在重绘里仍 >=0.12）===')
sm=(ir>=0.12); gm=(ig>=0.12)
print('  源暗线像素 %d   重绘 %d   保有率 %.3f   多余 %.3f'%(sm.sum(),gm.sum(),(sm&gm).sum()/sm.sum(),(gm&~sm).sum()/gm.sum()))
