import math,itertools
import validate_palette as vp
def lin2s(c):
    c=max(0.0,min(1.0,c)); return 12.92*c if c<=0.0031308 else 1.055*c**(1/2.4)-0.055
def oklch2hex(L,C,Hdeg,strict=True):
    h=math.radians(Hdeg); a=C*math.cos(h); b=C*math.sin(h)
    l_=L+0.3963377774*a+0.2158037573*b
    m_=L-0.1055613458*a-0.0638541728*b
    s_=L-0.0894841775*a-1.2914855480*b
    l,m,s=l_**3,m_**3,s_**3
    r= 4.0767416621*l-3.3077115913*m+0.2309699292*s
    g=-1.2684380046*l+2.6097574011*m-0.3413193965*s
    bb=-0.0041960863*l-0.7034186147*m+1.7076147010*s
    ing=all(-0.001<=x<=1.001 for x in (r,g,bb))
    if strict and not ing: return None
    return '#%02x%02x%02x'%tuple(round(255*lin2s(x)) for x in (r,g,bb))
def hue(h):
    L,a,b=vp.oklab_lin(vp.lin(h)); return (math.degrees(math.atan2(b,a))%360)
def snap(Hdeg,L,cmax=0.4):
    # max in-gamut chroma at (L,H), stepped down
    C=cmax
    while C>0.02:
        hx=oklch2hex(L,C,Hdeg)
        if hx: return hx,round(C,3)
        C-=0.005
    return None,None
if __name__=='__main__':
    for name,src in [('green','#3b811f'),('cyan','#01b1fc'),('red','#bd2f42'),('amber','#e9b12c'),('mint','#01d77f'),('slate','#476f8b'),('blue','#4267b2')]:
        print(name, src, round(hue(src),1))
