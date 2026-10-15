"""Draw event-origin and evidence-flow schematics directly as vector PDFs.

Requires Python 3.9+ and Matplotlib; no TeX engine or network is used.
"""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)





def draw(out):
    d=Drawing((-1.8,-2.124,7.95,2.124))
    d.box('h1',0,1.237,3.2,1.76,r'$H_1$'+'\n'+r'$A:e_1(3)$'+'\n'+r'$B:e_2(1)$'+'\n'+r'Score $(3,1)$')
    d.box('h2',0,-1.237,3.2,1.76,r'$H_2$'+'\n'+r'$B:e_1(3)$'+'\n'+r'$A:e_2(1)$'+'\n'+r'Score $(1,3)$')
    d.box('obs',6,0,3.4,1.76,'Observed squash\n'+r'author $I$'+'\n'+r'$e_1(3),e_2(1)$'+'\nOrigins absent')
    d.edge('h1','obs',sa='e',sb='w');d.edge('h2','obs',sa='e',sb='w')
    d.text(2.9,1.25,'erase origins');d.text(2.9,-1.25,'erase origins')
    d.save(out,'origin-collision')

    # Certification feeds the ledger separately from score/uncertainty analysis.
    d=Drawing((-1.8,-6.25,9.6,.515))
    for name,x,y,label in [
        ('extract',0,0,'Normalize\nchange events'),('validate',3.6,0,'Validate\nlocal evidence'),
        ('cert',7.2,0,'Check rewrite\ncertificate'),
        ('score',0,-1.714,'Score events or\nabstain'),('alias',3.6,-1.714,'Propagate alias\nuncertainty'),
        ('influence',7.2,-1.714,'Score bounds\nleader radii'),
        ('ledger',3.6,-3.428,'Serialize scalar /\ndiagnostic records'),
        ('replay',7.2,-3.428,'Independent\nreplay')]:
        d.box(name,x,y,2.7,1.0,label)
    d.edge('extract','validate',sa='e',sb='w');d.edge('validate','cert',sa='e',sb='w')
    d.edge('validate','score',sa='s',sb='n')
    d.edge('score','alias',sa='e',sb='w');d.edge('alias','influence',sa='e',sb='w')
    d.edge('alias','ledger');d.edge('influence','ledger',sa='s',sb='ne')
    d.edge('ledger','replay',sa='e',sb='w')
    d.arrow(d.point('cert','e'),d.point('ledger','s'),via=((9.25,0),(9.25,-4.45),(3.6,-4.45)))
    d.box('boundary',3.9,-5.55,10.8,1.35,
          'Missing positive-event origin causes origin abstention.\nMay-link overlap yields intervals and pairwise orders,\nbut no point ranking.',dashed=True)
    d.line([d.point('score','s'),(0,-4.875)],dashed=True)
    d.save(out,'evidence-pipeline')

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent)
    out=parser.parse_args().output
    out.mkdir(parents=True,exist_ok=True)
    draw(out)
