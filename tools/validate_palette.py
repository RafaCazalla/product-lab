import math,sys,json,itertools
BAND={"light":(0.43,0.77),"dark":(0.48,0.67)}
CHROMA_FLOOR=0.10; CVD_TARGET=8.0; CVD_FLOOR=6.0; NORMAL_FLOOR=15.0; CONTRAST_MIN=3.0
MACHADO={"protan":[[0.152286,1.052583,-0.204868],[0.114503,0.786281,0.099216],[-0.003882,-0.048116,1.051998]],
"deutan":[[0.367322,0.860646,-0.227968],[0.280085,0.672501,0.047413],[-0.011820,0.042940,0.968881]],
"tritan":[[1.255528,-0.076749,-0.178779],[-0.078411,0.930809,0.147602],[0.004733,0.691367,0.303900]]}
def hex2srgb(h):
    h=h.strip().lstrip('#'); return [int(h[i:i+2],16)/255 for i in (0,2,4)]
def s2lin(c): return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
def lin(h): return [s2lin(c) for c in hex2srgb(h)]
def rellum(h):
    r,g,b=lin(h); return 0.2126*r+0.7152*g+0.0722*b
def contrast(a,b):
    x,y=sorted([rellum(a),rellum(b)],reverse=True); return (x+0.05)/(y+0.05)
def oklab_lin(rgb):
    r,g,b=rgb
    l=(0.4122214708*r+0.5363325363*g+0.0514459929*b)**(1/3) if (0.4122214708*r+0.5363325363*g+0.0514459929*b)>=0 else 0
    m=(0.2119034982*r+0.6806995451*g+0.1073969566*b)**(1/3)
    s=(0.0883024619*r+0.2817188376*g+0.6299787005*b)**(1/3)
    return [0.2104542553*l+0.7936177850*m-0.0040720468*s,1.9779984951*l-2.4285922050*m+0.4505937099*s,0.0259040371*l+0.7827717662*m-0.8086757660*s]
def oklch(h):
    L,a,b=oklab_lin(lin(h)); return (L,math.hypot(a,b))
def simulate(h,kind):
    r,g,b=lin(h); M=MACHADO[kind]
    return [max(0,min(1,M[i][0]*r+M[i][1]*g+M[i][2]*b)) for i in range(3)]
def dE(h1,h2,kind=None):
    a=oklab_lin(simulate(h1,kind) if kind else lin(h1)); b=oklab_lin(simulate(h2,kind) if kind else lin(h2))
    return 100*math.dist(a,b)
def validate(pal,mode="light",surface=None,pairs="adjacent"):
    surface=surface or ("#fcfcfb" if mode=="light" else "#1a1a19")
    lo,hi=BAND[mode]; rep=[]; ok=True
    off=[(c,round(oklch(c)[0],3)) for c in pal if not (lo<=oklch(c)[0]<=hi)]
    if off: ok=False
    rep.append(("Lightness band","FAIL "+str(off) if off else f"pass (L {lo}-{hi})"))
    lowc=[(c,round(oklch(c)[1],3)) for c in pal if oklch(c)[1]<CHROMA_FLOOR]
    if lowc: ok=False
    rep.append(("Chroma floor","FAIL "+str(lowc) if lowc else "pass"))
    n=len(pal)
    pl=list(itertools.combinations(range(n),2)) if pairs=="all" else [(i,i+1) for i in range(n-1)]
    worst=None
    for k in ("protan","deutan"):
        for i,j in pl:
            d=dE(pal[i],pal[j],k)
            if worst is None or d<worst[0]: worst=(d,k,pal[i],pal[j])
    tri=min(dE(pal[i],pal[j],"tritan") for i,j in pl) if pl else 99
    wd=worst[0] if worst else 99
    st="pass" if wd>=CVD_TARGET else ("WARN-floor" if wd>=CVD_FLOOR else "FAIL")
    if st=="FAIL": ok=False
    rep.append(("CVD separation",f"{st} worst {worst[2]}<->{worst[3]} dE {wd:.1f} ({worst[1]}) tritan {tri:.1f}"))
    nw=None
    for i,j in pl:
        d=dE(pal[i],pal[j])
        if nw is None or d<nw[0]: nw=(d,pal[i],pal[j])
    nd=nw[0] if nw else 99
    st2="pass" if nd>=NORMAL_FLOOR else "FAIL"
    if st2=="FAIL": ok=False
    rep.append(("Normal-vision floor",f"{st2} worst {nw[1]}<->{nw[2]} dE {nd:.1f}"))
    low=[(c,round(contrast(c,surface),2)) for c in pal if contrast(c,surface)<CONTRAST_MIN]
    rep.append(("Contrast vs surface",("relief "+str(low)) if low else "pass"))
    return ok,rep
if __name__=="__main__":
    pal=[x.strip() for x in sys.argv[1].split(',')]
    mode=sys.argv[2] if len(sys.argv)>2 else "light"
    surf=sys.argv[3] if len(sys.argv)>3 else None
    pairs=sys.argv[4] if len(sys.argv)>4 else "adjacent"
    ok,rep=validate(pal,mode,surf,pairs)
    print(f"mode={mode} surface={surf} pairs={pairs} -> {'OK' if ok else 'FAILURES'}")
    for a,b in rep: print(f"  {a:22} {b}")
