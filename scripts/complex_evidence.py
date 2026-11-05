"""Crop only relevant vendor controls/counters, omitting account headers."""
import argparse
from pathlib import Path
from PIL import Image,ImageDraw
BASE=Path(__file__).resolve().parents[1]/'results/e3d_complex'
parser=argparse.ArgumentParser();parser.add_argument('case');parser.add_argument('--phase',default='run');args=parser.parse_args()
files=list(BASE.glob(args.case+'_'+args.phase+'_*.png'))
if not files:raise RuntimeError('No actual screenshot')
source=max(files,key=lambda p:p.stat().st_mtime)
with Image.open(source) as frame:
    board=Image.new('RGB',(1160,580),'white');draw=ImageDraw.Draw(board)
    draw.text((10,8),source.name,fill='black')
    board.paste(frame.crop((15,650,325,1000) if args.case in ('c_hcur','c_h2') else (15,200,325,690)),(0,40))
    board.paste(frame.crop((1890,215,2110,285)),(330,40))
    board.paste(frame.crop((350,1425,1150,1487)),(330,130))
    board.paste(frame.crop((2120,1160,2540,1400)),(330,220))
    board.save(BASE/'evidence'/(args.case+'_'+args.phase+'.png'))
print(BASE/'evidence'/(args.case+'_'+args.phase+'.png'))
