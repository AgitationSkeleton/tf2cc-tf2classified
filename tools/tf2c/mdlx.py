import sys, struct
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))), ''))
from mdlinfo import parse, cstr
p=sys.argv[1]; m=parse(p); b=open(p,'rb').read()
i=lambda o: struct.unpack_from('<i',b,o)[0]
print('name',m['name'],'ver',m['version'],'bones',len(m['bones']),'seqs',len(m['sequences']),'tex',len(m['textures']),'skinref',m['skinref'],'families',m['skinfamilies'],'flags',hex(m['flags']))
if '--skins' in sys.argv:
  # show only columns that differ between families
  sk=m['skins']; cols=[r for r in range(m['skinref']) if len(set(f[r] for f in sk))>1]
  print('varying skinref cols',cols)
  for fi,f in enumerate(sk): print(' fam',fi,[m['textures'][f[r]] for r in cols])
  print(' fam0 all',[m['textures'][x] for x in sk[0]])
nbp,bpi=i(232),i(236)
for k in range(nbp):
  o=bpi+k*16; nm=cstr(b,o+i(o)); nmod=i(o+4); mi=i(o+12)
  mods=[]
  for j in range(nmod):
    mo=o+mi+j*148; mods.append(b[mo:mo+64].split(b'\0')[0].decode('latin-1')+'(v%d)'%i(mo+80))
  print('bodypart',nm,mods)
