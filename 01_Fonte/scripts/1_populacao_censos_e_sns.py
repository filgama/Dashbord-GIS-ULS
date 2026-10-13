import json,sys,re
sp=sys.argv[1]
src=open('urgencias-data.js',encoding='utf-8').read()
src=src.split('\n;window.URG.pop=')[0].rstrip()
U=json.loads(src[src.index('{'):].rstrip(';'))
ine=json.load(open(sp+'/ine.json',encoding='utf-8'))[0]['Dados']['2021']
tab={}
for r in ine:
    if r['dim_3']=='T' and len(r['geocod'])==6: tab.setdefault(r['geocod'],{})[r['dim_4']]=int(r['valor'])
pop={};miss=[]
for f in U['feats']:
    if f['t']!=1: continue
    t=tab.get(f['d'])
    if not t: miss.append((f['d'],f['n'])); continue
    pop[f['d']]=[t['T'],t['1'],t['4']]
print('freguesias',len(pop),'em falta',miss)
for c in ('Amadora','Sintra'): print(c,sum(pop[f['d']][0] for f in U['feats'] if f['t']==1 and f['c']==c and f['d'] in pop))
sns=json.load(open(sp+'/sns.json',encoding='utf-8'))['results']
print([(r['periodo'],r['aces'],r['utentes_inscritos_csp'],r['total_utentes_sem_mdf_atribuido']) for r in sns])
r=next(x for x in sns if x['periodo']=='2026-03')
S={'per':r['periodo'],'insc':r['utentes_inscritos_csp'],'sem':r['total_utentes_sem_mdf_atribuido'],'ent':r['aces']}
out=src+'\n;window.URG.pop='+json.dumps(pop,separators=(',',':'))+';window.URG.sns='+json.dumps(S,ensure_ascii=False,separators=(',',':'))+';\n'
open('urgencias-data.js','w',encoding='utf-8',newline='').write(out)
print(S, src[-60:])
