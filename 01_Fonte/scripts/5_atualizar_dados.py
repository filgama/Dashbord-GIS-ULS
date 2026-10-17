"""Atualiza os dados do dashboard a partir de uma nova extração BD_Urgencia_Admissoes.csv.

Recalcula, a partir do CSV, tudo o que vem das admissões: dias, cubo por freguesia (R),
horas (H), utentes frequentes (freq) e unidades de cuidados primários (cs). Mantém o que não
vem do CSV: geometria das freguesias, população (Censos), médico de família (SNS) e hospitais.
Depois volta a pôr os dados no "Origem das Urgencias.html" da raiz.

Uso (a partir da raiz do repositório):
    python 01_Fonte/scripts/5_atualizar_dados.py 02_Dados/BD_Urgencia_Admissoes.csv --verificar
    python 01_Fonte/scripts/5_atualizar_dados.py 02_Dados/BD_Urgencia_Admissoes.csv

--verificar   não escreve nada; compara o que sairia com os dados atuais (com o mesmo CSV
              que gerou o dashboard, tudo deve dar "igual").
--coluna-hora NOME   coluna com a hora de admissão, se não for detetada sozinha.
--sem-html    atualiza só 01_Fonte/urgencias-data.js, sem mexer no HTML da raiz.

As freguesias do CSV vêm por nome; a correspondência nome -> código (dicofre) fica em
freguesias_csv.json, ao lado deste script. Na primeira vez é reconstruída a partir dos dados
atuais (com o CSV que os gerou). Nomes novos aparecem na lista "sem correspondência": essas
admissões contam como "sem freguesia" até se acrescentar o nome ao ficheiro.

Os dados pessoais (cartão de utente) só são usados para contar utentes frequentes e por unidade;
nada disso sai para o dashboard além de contagens agregadas.
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTE = os.path.join(AQUI, '..')
DADOS = os.path.join(FONTE, 'urgencias-data.js')
MAPA = os.path.join(AQUI, 'freguesias_csv.json')
MARCAS = ['pop', 'sns', 'freq', 'hosp', 'cs', 'snsm', 'soc']
LOCK = ['GERAL', 'PEDIATRICA', 'BASICA', 'OBSTETRICA', 'GINECOLOGICA']
K_FREQ = 4          # utentes com K ou mais idas = frequentes
CS_MIN_ADM = 20     # unidades com menos admissões vão para "fora"
SEM_CS = {'', 'HEALT_CARE_UNIT_CODE CRIADO PELO ALERT', 'SEM CENTRO DE SAUDE', 'DESCONHECIDO'}
HORA_CANDIDATAS = ['Hora', 'Hora_Admissao', 'Hora_Entrada', 'Data_Hora', 'DataHora', 'Data_Hora_Admissao', 'Hora_Admissão']


def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', (s or '').upper()) if unicodedata.category(c) != 'Mn').strip()


def ler_dados():
    s = open(DADOS, encoding='utf-8').read()
    base, _ = json.JSONDecoder().raw_decode(s[s.index('{'):])
    extra = {}
    for k in MARCAS:
        m = re.search(r';window\.URG\.' + k + r'=', s)
        if m:
            extra[k], _ = json.JSONDecoder().raw_decode(s[m.end():])
    return s, base, extra


def escrever_dados(base, extra):
    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
    out = 'window.URG=' + j(base) + ';\n'
    out += ';window.URG.pop=' + j(extra['pop']) + ';window.URG.sns=' + j(extra['sns']) + ';\n'
    out += ';window.URG.freq=' + j(extra['freq']) + ';window.URG.hosp=' + j(extra['hosp']) + ';\n'
    out += ';window.URG.cs=' + j(extra['cs']) + ';\n'
    if 'snsm' in extra:  # séries mensais do Portal da Transparência (7_dados_sns.py): não dependem do CSV, mantêm-se
        out += ';window.URG.snsm=' + j(extra['snsm']) + ';\n'
    if 'soc' in extra:  # contexto social (6_contexto_social.py): não depende do CSV, mantém-se
        out += ';window.URG.soc=' + j(extra['soc']) + ';\n'
    return out


def data_iso(v):
    v = (v or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(v[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError(f'data não reconhecida: {v!r}')


def hora_de(v):
    m = re.search(r'(?:^|[ T])(\d{1,2})[:h]\d{2}', (v or '').strip()) or re.match(r'^(\d{1,2})$', (v or '').strip())
    if not m:
        raise ValueError(f'hora não reconhecida: {v!r}')
    h = int(m.group(1))
    if not 0 <= h <= 23:
        raise ValueError(f'hora fora de 0-23: {v!r}')
    return h


def detetar_hora(cab, pedida):
    if pedida:
        if pedida not in cab:
            sys.exit(f'Coluna de hora "{pedida}" não existe. Colunas: {", ".join(cab)}')
        return pedida
    for c in HORA_CANDIDATAS:
        if c in cab:
            return c
    for c in cab:
        if 'HORA' in norm(c):
            return c
    return None


def reconstruir_mapa(rows, base):
    """Nome do CSV -> dicofre, por encaixe nas contagens do cubo atual (mesmo método do script 2)."""
    U = base; R = U['R']; dia = {d: i for i, d in enumerate(U['days'])}
    cube = defaultdict(Counter)
    for j in range(0, len(R), 6):
        if R[j + 1]:
            cube[U['pd'][R[j + 1]]][(R[j], R[j + 2], R[j + 4])] += R[j + 5]
    sig = defaultdict(Counter); tot = Counter()
    for r in rows:
        nm = norm(r['Freguesia'])
        if not nm or r['_dia'] not in dia:
            continue
        sig[nm][(dia[r['_dia']], r['_l'], r['_a'])] += 1; tot[nm] += 1
    left = {d: Counter(c) for d, c in cube.items()}; out = {}; falta = sorted(sig, key=lambda n: -tot[n])
    for _ in range(4):
        resto = []
        for nm in falta:
            cands = [d for d, c in left.items() if all(c.get(k, 0) >= v for k, v in sig[nm].items())]
            if len(cands) == 1:
                out[nm] = cands[0]; left[cands[0]].subtract(sig[nm])
            else:
                resto.append(nm)
        if len(resto) == len(falta):
            break
        falta = resto
    return out, falta


def calcular(rows, base, mapa):
    U = base
    d0 = min(r['_data'] for r in rows); d1 = max(r['_data'] for r in rows)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    di = {d: i for i, d in enumerate(days)}
    pd = list(U['pd']); pix = {d: i for i, d in enumerate(pd) if d}
    for d in sorted(set(mapa.values()) - set(pix)):
        pix[d] = len(pd); pd.append(d)
    cr = Counter(); ch = Counter(); sem_map = Counter()
    for r in rows:
        nm = norm(r['Freguesia']); dc = mapa.get(nm)
        if nm and not dc:
            sem_map[r['Freguesia'].strip()] += 1
        p = pix[dc] if dc else 0
        cr[(di[r['_dia']], p, r['_l'], r['_p'], r['_a'])] += 1
        if r['_h'] is not None:
            ch[(di[r['_dia']], r['_h'], r['_l'], r['_p'], r['_a'])] += 1
    R = [v for k in sorted(cr) for v in (*k, cr[k])]
    H = [v for k in sorted(ch) for v in (*k, ch[k])]
    novo = dict(U); novo.update(days=days, pd=pd, R=R, H=H)
    novo['meta'] = dict(U['meta'], n=len(rows), de=days[0], ate=days[-1])
    return novo, sem_map


def calcular_freq(rows, mapa):
    per = defaultdict(list)
    for r in rows:
        if r['Cartao_Utente'].strip():
            per[r['Cartao_Utente'].strip()].append(norm(r['Freguesia']))
    by = defaultdict(lambda: [0, 0, 0, 0]); T = [0, 0, 0, 0]
    for u, fl in per.items():
        n = len(fl); fq = n >= K_FREQ
        T[0] += 1; T[1] += fq; T[2] += n * fq; T[3] += n
        d = mapa.get(Counter(fl).most_common(1)[0][0])
        if d:
            b = by[d]; b[0] += 1; b[1] += fq; b[2] += n * fq; b[3] += n
    return {'k': K_FREQ, 'tot': T, 'sem': sum(1 for r in rows if not r['Cartao_Utente'].strip()), 'by': dict(by)}


SIG = {'USF', 'UCSP', 'UCC', 'CS', 'CSP', 'SAC', 'SAUSM', 'ULS', 'UCSC', 'SCM', 'SCML', 'EDP', 'RRE', 'II', 'III', 'IV', 'I', 'AS', 'HSM'}
SMALL = {'DE', 'DA', 'DO', 'DAS', 'DOS', 'E', 'A', 'EM'}


def tc(n):
    out = []
    for i, w in enumerate(n.split(' ')):
        u = w.upper()
        if u in SIG:
            out.append(u)
        elif i > 0 and u in SMALL:
            out.append(u.lower())
        else:
            out.append('-'.join(p[:1].upper() + p[1:].lower() for p in w.split('-')))
    return ' '.join(out)


def calcular_cs(rows):
    sp = lambda x: re.sub(r'\s+', ' ', x or '').strip()
    key = lambda x: ''.join(c for c in unicodedata.normalize('NFKD', sp(x)) if not unicodedata.combining(c)).upper()
    for r in rows:
        r['_k'] = key(r['Centro_Saude'])
    com = [r for r in rows if r['_k'] not in SEM_CS]
    variantes = defaultdict(Counter)
    for r in com:
        variantes[r['_k']][sp(r['Centro_Saude'])] += 1
    disp = {k: c.most_common(1)[0][0] for k, c in variantes.items()}
    uc = Counter(r['Cartao_Utente'] for r in rows if r['Cartao_Utente'].strip())
    pu = Counter((r['Cartao_Utente'], r['_k']) for r in com if r['Cartao_Utente'].strip())
    umap = {}
    for (u, k), n in sorted(pu.items(), key=lambda x: (x[0][0], -x[1], x[0][1])):
        umap.setdefault(u, k)
    by = defaultdict(list)
    for u, k in umap.items():
        by[k].append(u)
    grupos = defaultdict(list)
    for r in com:
        grupos[r['_k']].append(r)
    out = []
    for k, g in grupos.items():
        us = by.get(k, []); fr = [u for u in us if uc[u] >= K_FREQ]; nm = tc(disp[k])
        ag = Counter(r['_a'] for r in g)
        out.append({'n': nm, 't': nm.split(' ')[0].upper() if nm.split(' ')[0].upper() in ('USF', 'UCSP') else 'outro',
                    'ag': max(ag, key=lambda a: (ag[a], -a)),
                    'c': [sum(1 for r in g if r['_p'] == i) for i in range(7)], 'loc': [sum(1 for r in g if r['_l'] == i) for i in range(5)],
                    'u': len(us), 'f': len(fr), 'af': sum(uc[u] for u in fr), 'ai': sum(uc[u] for u in us)})
    out.sort(key=lambda r: -sum(r['c']))
    dentro = [r for r in out if r['ag'] in (0, 1) and sum(r['c']) >= CS_MIN_ADM]
    fora = [r for r in out if r not in dentro]
    return {'k': K_FREQ, 'sem': len(rows) - len(com), 'fora': {'u': len(fora), 'a': sum(sum(r['c']) for r in fora)}, 'rows': dentro}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    pedida = sys.argv[sys.argv.index('--coluna-hora') + 1] if '--coluna-hora' in sys.argv else None
    if pedida in args:
        args.remove(pedida)
    verificar = '--verificar' in sys.argv
    with open(args[0], encoding='utf-8-sig', newline='') as fh:
        leitor = csv.DictReader(fh, delimiter=';')
        cab = leitor.fieldnames or []
        precisa = ['Data', 'Local_Entrada', 'Prioridade', 'Agrupamento_Freg', 'Freguesia', 'Centro_Saude', 'Cartao_Utente']
        falta = [c for c in precisa if c not in cab]
        if falta:
            sys.exit(f'Faltam colunas no CSV: {", ".join(falta)}. Colunas encontradas: {", ".join(cab)}')
        col_h = detetar_hora(cab, pedida)
        rows = list(leitor)
    print(f'{len(rows)} admissões lidas; hora: {col_h or "SEM COLUNA DE HORA (o quadro hora x dia fica vazio)"}')
    erros = Counter()
    for r in rows:
        r['_data'] = data_iso(r['Data']); r['_dia'] = r['_data'].isoformat()
        loc = norm(r['Local_Entrada']); r['_l'] = next((i for i, k in enumerate(LOCK) if k in loc), None)
        pr = (r['Prioridade'] or '').strip()[:1]; r['_p'] = int(pr) - 1 if pr.isdigit() and 1 <= int(pr) <= 7 else None
        ag = (r['Agrupamento_Freg'] or '').strip()[:1]; r['_a'] = int(ag) - 1 if ag in ('1', '2', '3') else None
        r['_h'] = None
        if col_h:
            try:
                r['_h'] = hora_de(r[col_h])
            except ValueError:
                erros['hora'] += 1
        for c in ('_l', '_p', '_a'):
            if r[c] is None:
                erros[c] += 1
    if erros['_l'] or erros['_p'] or erros['_a']:
        sys.exit(f'Valores não reconhecidos: local {erros["_l"]}, prioridade {erros["_p"]}, agrupamento {erros["_a"]}. Corrija o CSV ou o script.')
    if erros['hora']:
        print(f'aviso: {erros["hora"]} admissões sem hora reconhecida ficam fora do quadro hora x dia')

    texto, base, extra = ler_dados()
    if os.path.exists(MAPA):
        mapa = json.load(open(MAPA, encoding='utf-8'))
    else:
        mapa, falta = reconstruir_mapa(rows, base)
        print(f'correspondência de freguesias reconstruída: {len(mapa)} nomes; sem solução única: {falta[:15]}')
        if not verificar:
            json.dump(dict(sorted(mapa.items())), open(MAPA, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=1)
            print('guardada em', os.path.relpath(MAPA))
    novo, sem_map = calcular(rows, base, mapa)
    nx = dict(extra, freq=calcular_freq(rows, mapa), cs=calcular_cs(rows))
    if sem_map:
        print(f'freguesias sem correspondência ({sum(sem_map.values())} admissões contam como "sem freguesia"):')
        for nm, n in sem_map.most_common(30):
            print(f'   {n:6d}  {nm}')
    print(f'período {novo["days"][0]} a {novo["days"][-1]} ({len(novo["days"])} dias)')

    if verificar:
        for k in ('days', 'pd', 'R', 'H', 'meta'):
            print(f'  {k:5s}', 'igual' if novo[k] == base[k] else 'DIFERENTE')
        for k in ('freq', 'cs'):
            print(f'  {k:5s}', 'igual' if nx[k] == extra.get(k) else 'DIFERENTE')
        print('  ficheiro', 'igual' if escrever_dados(novo, nx) == texto else 'DIFERENTE (ver linhas acima)')
        return
    open(DADOS, 'w', encoding='utf-8', newline='\n').write(escrever_dados(novo, nx))
    print('escrito', os.path.relpath(DADOS))
    if '--sem-html' not in sys.argv:
        sys.path.insert(0, AQUI)
        __import__('4_embeber_no_html').atualizar_dados()


if __name__ == '__main__':
    main()
