import csv, json, math, collections, unicodedata, sys
MARK = '\n;window.URG.freq='
src = open('urgencias-data.js', encoding='utf-8').read().split(MARK)[0].rstrip()
base = src.split('\n;window.URG.pop=')[0].rstrip()
U = json.loads(base[base.index('{'):].rstrip(';'))
norm = lambda s: ''.join(c for c in unicodedata.normalize('NFD', s.upper()) if unicodedata.category(c) != 'Mn').strip()
rows = list(csv.DictReader(open('../02_Dados/BD_Urgencia_Admissoes.csv', encoding='utf-8-sig'), delimiter=';'))

# totais por freguesia segundo o cubo ja existente (U.R: dia, pd, local, prio, ag, n)
R = U['R']; ref = collections.Counter()
for j in range(0, len(R), 6):
    if R[j + 1]: ref[U['pd'][R[j + 1]]] += R[j + 5]
csvTot = collections.Counter(norm(r['Freguesia']) for r in rows)
# mapear nome do CSV -> dicofre. O cubo original juntou nomes antigos (ex.: Reboleira, Buraca) nas freguesias atuais;
# reconstroi-se por encaixe: as contagens (dia, local, origem) de cada nome tem de caber nas do cubo, e no fim os totais batem certo.
LOCK = ['GERAL', 'PEDIATRICA', 'BASICA', 'OBSTETRICA', 'GINECOLOGICA']; dayIx = {d: i for i, d in enumerate(U['days'])}
key = lambda r: (dayIx[r['Data']], next(i for i, k in enumerate(LOCK) if k in norm(r['Local_Entrada'])), int(r['Agrupamento_Freg'][0]) - 1)
cube = collections.defaultdict(collections.Counter)
for j in range(0, len(R), 6):
    if R[j + 1]: cube[U['pd'][R[j + 1]]][(R[j], R[j + 2], R[j + 4])] += R[j + 5]
sig = collections.defaultdict(collections.Counter)
for r in rows: sig[norm(r['Freguesia'])][key(r)] += 1
name2d = {}; bad = []; left = {d: collections.Counter(c) for d, c in cube.items()}
for nm in sorted(sig, key=lambda n: -csvTot[n]):
    if not nm: continue
    cands = [d for d, c in left.items() if all(c.get(k, 0) >= v for k, v in sig[nm].items())]
    if len(cands) == 1: name2d[nm] = cands[0]; left[cands[0]].subtract(sig[nm])
    else: bad.append((nm, csvTot[nm], len(cands)))
for _ in range(3):  # segunda passagem para os ambiguos, ja com o que sobra
    for nm, tot, _n in list(bad):
        cands = [d for d, c in left.items() if all(c.get(k, 0) >= v for k, v in sig[nm].items())]
        if len(cands) == 1: name2d[nm] = cands[0]; left[cands[0]].subtract(sig[nm]); bad.remove((nm, tot, _n))
got = collections.Counter()
for nm, d in name2d.items(): got[d] += csvTot[nm]
print('freguesias com total identico ao cubo', sum(1 for d in ref if got[d] == ref[d]), 'de', len(ref))
print('diferencas', [(d, ref[d], got[d]) for d in ref if got[d] != ref[d]][:20])
print('nao mapeadas', bad[:20], 'adm', sum(b[1] for b in bad), 'sem freguesia no CSV', csvTot[''])
if '--check' in sys.argv: sys.exit()

K = 4
per = collections.defaultdict(list)
for r in rows:
    if r['Cartao_Utente']: per[r['Cartao_Utente']].append(norm(r['Freguesia']))
by = collections.defaultdict(lambda: [0, 0, 0, 0]); T = [0, 0, 0, 0]
for u, fl in per.items():
    n = len(fl); fq = n >= K
    T[0] += 1; T[1] += fq; T[2] += n * fq; T[3] += n
    d = name2d.get(collections.Counter(fl).most_common(1)[0][0])
    if d: b = by[d]; b[0] += 1; b[1] += fq; b[2] += n * fq; b[3] += n
print('total', T, 'sem cartao', sum(1 for r in rows if not r['Cartao_Utente']))
freq = {'k': K, 'tot': T, 'sem': sum(1 for r in rows if not r['Cartao_Utente']), 'by': dict(by)}

m = U['meta']
def proj(lat, lon):
    wx = (lon + 180) / 360; la = math.radians(lat)
    wy = (1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2
    return round((wx - m['wx0']) * m['s'], 2), round((wy - m['wy0']) * m['s'], 2)
# coordenadas: OpenStreetMap (Nominatim), consultadas a 2026-10-13
hosp = []
for n, t, lat, lon in [('HFF', 'Hospital Prof. Doutor Fernando Fonseca', 38.7436, -9.24676), ('H. Sintra', 'Hospital de Sintra', 38.809639, -9.354054)]:
    x, y = proj(lat, lon); hosp.append({'n': n, 't': t, 'x': x, 'y': y})
cen = {f['n']: (f['x'], f['y']) for f in U['feats'] if f['t'] == 1 and f['n'] in ('Venteira', 'Algueirão-Mem Martins')}
print(hosp, cen)
out = src + MARK + json.dumps(freq, separators=(',', ':')) + ';window.URG.hosp=' + json.dumps(hosp, ensure_ascii=False, separators=(',', ':')) + ';\n'
open('urgencias-data.js', 'w', encoding='utf-8', newline='').write(out)
print('ok', len(out))
