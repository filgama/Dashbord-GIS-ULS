import pandas as pd, json, re, unicodedata, sys, os
from collections import Counter, defaultdict
P=r"C:\Users\filipe.c.gama\OneDrive - SPMS - Serviços Partilhados do Ministério da Saúde, EPE\Ambiente de Trabalho\urgencias\Mockup"
OUT=os.path.dirname(os.path.abspath(__file__))
d=pd.read_csv(P+r"\data\BD_Urgencia_Admissoes.csv",sep=';',encoding='utf-8-sig',dtype=str,keep_default_na=False)
N=len(d)
PRI={'1':0,'2':1,'3':2,'4':3,'5':4,'6':5,'7':6}
LOCM={'URGENCIA GERAL':0,'URGENCIA PEDIATRICA':1,'URGENCIA BASICA':2,'URGENCIA OBSTETRICA':3,'URGENCIA GINECOLOGICA':4}
d['p']=d.Prioridade.str.strip().str[0].map(PRI)
d['l']=d.Local_Entrada.str.strip().str.upper().map(LOCM)
d['a']=d.Agrupamento_Freg.str.strip().str[0].astype(int)-1
assert d.p.notna().all() and d.l.notna().all()
# validação contra urgencias-data.js
s=open(P+r"\urgencias-data.js",encoding='utf-8').read()
o,_=json.JSONDecoder().raw_decode(s[s.index('{'):])
R=o['R']; tp=[0]*7; tl=[0]*5
for i in range(0,len(R),6):
    tl[R[i+2]]+=R[i+5]; tp[R[i+3]]+=R[i+5]
cp=d.p.value_counts().reindex(range(7)).tolist(); cl=d.l.value_counts().reindex(range(5)).tolist()
print('prioridade CSV',cp,'JS',tp,cp==tp); print('local CSV',cl,'JS',tl,cl==tl)
assert cp==tp and cl==tl
def norm(x): return re.sub(r'\s+',' ',x).strip()
def key(x):
    x=unicodedata.normalize('NFKD',norm(x)); return ''.join(c for c in x if not unicodedata.combining(c)).upper()
SEM={'','HEALT_CARE_UNIT_CODE CRIADO PELO ALERT','SEM CENTRO DE SAUDE','DESCONHECIDO'}
d['k']=d.Centro_Saude.map(key)
d['isem']=d.k.isin(SEM)
# nome de exibição: variante mais frequente por chave
disp={}; fus={}
for k,g in d[~d.isem].groupby('k').Centro_Saude:
    c=Counter(map(norm,g)); disp[k]=c.most_common(1)[0][0]
    if len(c)>1: fus[k]=dict(c)
SIG={'USF','UCSP','UCC','CS','CSP','SAC','SAUSM','ULS','UCSC','SCM','SCML','EDP','RRE','II','III','IV','I','AS','HSM'}
SMALL={'DE','DA','DO','DAS','DOS','E','A','EM'}
def tc(n):
    out=[]
    for i,w in enumerate(n.split(' ')):
        u=w.upper()
        if u in SIG: out.append(u)
        elif i>0 and u in SMALL: out.append(u.lower())
        else: out.append('-'.join(p[:1].upper()+p[1:].lower() for p in w.split('-')))
    return ' '.join(out)
def tipo(n):
    f=n.split(' ')[0].upper(); return f if f in('USF','UCSP') else 'outro'
# atribuição de utentes
dc=d[(d.Cartao_Utente.str.strip()!='')]
uc=dc.groupby('Cartao_Utente').size()
um=dc[~dc.isem].groupby(['Cartao_Utente','k']).size().reset_index(name='n').sort_values(['Cartao_Utente','n','k'],ascending=[True,False,True]).drop_duplicates('Cartao_Utente')
umap=dict(zip(um.Cartao_Utente,um.k))
rows=[]
for k,g in d[~d.isem].groupby('k'):
    ut=[u for u,kk in umap.items() if kk==k] if False else None
by=defaultdict(list)
for u,kk in umap.items(): by[kk].append(u)
for k,g in d[~d.isem].groupby('k'):
    us=by.get(k,[]); fr=[u for u in us if uc[u]>=4]
    nm=tc(disp[k])
    rows.append({'n':nm,'t':tipo(nm),'ag':int(g.a.value_counts().idxmax()),
     'c':g.p.value_counts().reindex(range(7),fill_value=0).tolist(),
     'loc':g.l.value_counts().reindex(range(5),fill_value=0).tolist(),
     'u':len(us),'f':len(fr),'af':int(sum(uc[u] for u in fr)),'ai':int(sum(uc[u] for u in us))})
rows.sort(key=lambda r:-sum(r['c']))
sem=int(d.isem.sum()); tot=sum(sum(r['c']) for r in rows)+sem
print('unidades',len(rows),'sem',sem,'soma',tot); assert tot==N==51666
assert all(sum(r['c'])==sum(r['loc']) for r in rows)
json.dump({'k':4,'sem':sem,'rows':rows},open(OUT+r"\cs.json",'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
print('fusoes',fus)
print('tipos',Counter(r['t'] for r in rows)); print('ag',Counter(r['ag'] for r in rows))
print('utentes sem unidade',len(uc)-len(umap),'ai total',sum(r['ai'] for r in rows),'cartao',len(dc))
for r in rows[:10]:
    t=sum(r['c']); print(r['n'],r['t'],t,round(100*(r['c'][3]+r['c'][4])/t,1))
# fora ULS: unidades com ag 3 dominante
print('outros ag=2 (3-Outros):',sum(1 for r in rows if r['ag']==2),'admissoes',sum(sum(r['c']) for r in rows if r['ag']==2))
print('nao-USF/UCSP:',sum(1 for r in rows if r['t']=='outro'),sum(sum(r['c']) for r in rows if r['t']=='outro'))
