import numpy as np, subprocess, math
from PIL import Image, ImageDraw, ImageFont
W,H,FPS,DUR = 1080,1920,30,30
B="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F=lambda s: ImageFont.truetype(B,s)
maps={y:np.asarray(Image.open(f"map_{y}.png").convert("RGB")).astype(np.float32) for y in [1800,1815,1880,1914,2010]}
# (año, segundo en que empieza la transición hacia ese mapa); cada transición dura 1 s
segs=[(1800,0),(1815,9),(1880,14),(1914,21),(2010,26)]
LON0,LAT1=-84,14; top,bot=300,1760; scale=(bot-top)/71; x_off=(W-52*scale)/2
proj=lambda lon,lat:(x_off+(lon-LON0)*scale, top+(LAT1-lat)*scale)
caps=[(3,8,"1800: casi todo era de\nEspaña y Portugal"),
      (9.3,13,"1810–1825: estallan\nlas independencias"),
      (14.3,20,"1830: la Gran Colombia se divide\nen Colombia, Venezuela y Ecuador"),
      (21.3,25,"1884: Bolivia pierde su salida\nal mar en la Guerra del Pacífico"),
      (26.3,30,"Hoy son 12 países.\n¿Cuál es el tuyo? Coméntalo")]
rings=[(14.3,20,proj(-78.3,-1.6),"#FFD166"),(21.3,25,proj(-70.3,-22.5),"#FF5A5F")]
def frame_map(t):
    cur=segs[0]
    for i,(y,ts) in enumerate(segs):
        if t>=ts: cur=i
    y,ts=segs[cur]
    if cur>0 and t<ts+1:
        a=(t-ts); a=a*a*(3-2*a)
        img=maps[segs[cur-1][0]]*(1-a)+maps[y]*a
        yr=round(segs[cur-1][0]+(y-segs[cur-1][0])*a)
    else:
        img=maps[y]; yr=y
    return Image.fromarray(img.astype(np.uint8)), yr
def text_box(d,xy,txt,font,fill,bg,pad=22,anchor="mm",radius=18):
    bb=d.multiline_textbbox(xy,txt,font=font,anchor=anchor,align="center",spacing=10)
    d.rounded_rectangle([bb[0]-pad,bb[1]-pad,bb[2]+pad,bb[3]+pad],radius=radius,fill=bg)
    d.multiline_text(xy,txt,font=font,fill=fill,anchor=anchor,align="center",spacing=10)
ff=subprocess.Popen(["ffmpeg","-y","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-",
   "-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-preset","medium","demo_sudamerica.mp4"],stdin=subprocess.PIPE)
for n in range(FPS*DUR):
    t=n/FPS
    im,yr=frame_map(t)
    z=1+0.03*t/DUR  # slow zoom
    cw,ch=int(W/z),int(H/z); im=im.crop(((W-cw)//2,(H-ch)//2,(W-cw)//2+cw,(H-ch)//2+ch)).resize((W,H),Image.BICUBIC)
    d=ImageDraw.Draw(im)
    for (a,b,(x,y),col) in rings:
        if a<=t<b:
            x=W/2+(x-W/2)*z; y=H/2+(y-H/2)*z
            r=55+10*math.sin((t-a)*6)
            d.ellipse([x-r,y-r,x+r,y+r],outline=col,width=8)
    d.text((W/2,120),("HOY" if yr==2010 else str(yr)),font=F(120),fill="#FFD166",anchor="mm")
    if t<3:
        text_box(d,(W/2,262),"Hace 200 años, Ecuador\nno existía como país",F(50),"#FFFFFF","#C1121F",pad=16)
    for a,b,txt in caps:
        if a<=t<b:
            text_box(d,(W/2,1745),txt,F(46),"#14212B","#F4F1EA")
    d.text((W/2,1880),"Mapas: historical-basemaps · fronteras aproximadas",font=F(22),fill="#7F8C99",anchor="mm")
    ff.stdin.write(im.tobytes())
ff.stdin.close(); ff.wait(); print("done")
