# -*- coding: utf-8 -*-
"""发丝暗线位置精度：在扫描线上找 ink 局部极大值，配对后比较亚像素位置与峰值"""
import numpy as np
ref=np.load('tmp/refrgb.npy'); got=np.load('tmp/gotrgb.npy')
def ink(a): return np.clip((255-(a@np.array([0.299,0.587,0.114])))/255.0,0,1)
ir,ig=ink(ref),ink(got)
def peaks(p,th=0.06):
    out=[]
    for i in range(1,len(p)-1):
        if p[i]>=th and p[i]>=p[i-1] and p[i]>p[i+1]:
            # 抛物线亚像素
            d=(p[i-1]-p[i+1])/(2*(p[i-1]-2*p[i]+p[i+1])) if (p[i-1]-2*p[i]+p[i+1])!=0 else 0
            out.append((i+max(-1,min(1,d)),p[i]))
    return out
tot=[];pk=[]
for y in range(120,1120,6):
    A=peaks(ir[y]); B=peaks(ig[y])
    for ax,av in A:
        cand=[b for b in B if abs(b[0]-ax)<2.5]
        if cand:
            bx,bv=min(cand,key=lambda t:abs(t[0]-ax)); tot.append(bx-ax); pk.append(bv-av)
tot=np.array(tot); pk=np.array(pk)
print('=== 发丝暗线 ===')
print('  配对数 %d'%len(tot))
print('  位置偏移：平均 %+.3f px  平均绝对 %.3f px  σ=%.3f  P99=%.3f  max=%.3f'%(tot.mean(),np.abs(tot).mean(),tot.std(),np.quantile(np.abs(tot),0.99),np.abs(tot).max()))
print('  峰值墨量差：平均 %+.4f  平均绝对 %.4f (=%.2f/255)  P99=%.2f/255  max=%.2f/255'%(
      pk.mean(),np.abs(pk).mean(),np.abs(pk).mean()*255,np.quantile(np.abs(pk),0.99)*255,np.abs(pk).max()*255))
for th in (0.05,0.08,0.10,0.12,0.15):
    sm=ir>=th; gm=ig>=th
    print('  阈值 %.2f：源 %6d px  重绘 %6d px  保有率 %.3f'%(th,sm.sum(),gm.sum(),(sm&gm).sum()/sm.sum()))
