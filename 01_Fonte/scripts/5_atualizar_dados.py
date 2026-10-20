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

Dias sem nenhuma admissão no CSV, ou sem admissões depois das 9h (falta o report do dia
seguinte), ficam em meta.falta: o dashboard mostra-os como "sem dados" em vez de dias com 0.
O último dia não entra na lista (é sempre incompleto e o dashboard já o trata assim).

Utentes frequentes (freq e unidades em cs): contados nos últimos 12 meses do período, para que
o indicador não mude de significado quando se junta histórico.

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
from datetime import date, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTE = os.path.join(AQUI, '..')
DADOS = os.path.join(FONTE, 'urgencias-data.js')
MAPA = os.path.join(AQUI, 'freguesias_csv.json')
sys.path.insert(0, AQUI)
m4 = __import__('4_embeber_no_html')
MARCAS = ['pop', 'sns', 'freq', 'hosp', 'cs', 'snsm', 'soc']
LOCK = ['GERAL', 'PEDIATRICA', 'BASICA', 'OBSTETRICA', 'GINECOLOGICA']
K_FREQ = 4          # utentes com K ou mais idas = frequentes
CS_MIN_ADM = 20     # unidades com menos admissões vão para "fora"
JANELA_FREQ = 365   # dias (contados a partir do fim do período) usados para os utentes frequentes
HORA_COMPLETA = 9   # um dia sem admissões a partir desta hora ficou sem o report seguinte
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
    """AAAA-MM-DD, AAAA/MM/DD, DD/MM/AAAA ou DD-MM-AAAA, com ou sem zeros à esquerda e hora a seguir."""
    m = re.match(r'\s*(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})(?!\d)', v or '')
    if m:
        a, b, c = m.groups()
        y, mo, d = (a, b, c) if len(a) == 4 else (c, b, a) if len(c) == 4 else (None, None, None)
        if y:
            try:
                return date(int(y), int(mo), int(d))
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
    """Nome do CSV -> dicofre, por encaixe nas contagens do cubo atual (mesmo método do script 2).

    Só usa os dias interiores do cubo atual (o primeiro e o último costumam estar incompletos e
    um CSV mais longo tem-nos completos, o que impediria o encaixe) e fora dos dias em falta.
    Devolve (mapa, nomes fora do mapa, nomes ambíguos: mais de uma freguesia possível).
    """
    U = base; R = U['R']; ex = set(U['meta'].get('falta', []))
    dia = {d: i for i, d in enumerate(U['days']) if 0 < i < len(U['days']) - 1 and d not in ex}
    usar = set(dia.values())
    cube = defaultdict(Counter)
    for j in range(0, len(R), 6):
        if R[j + 1] and R[j] in usar:
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
    ambig = [nm for nm in falta if sum(1 for c in left.values() if all(c.get(k, 0) >= v for k, v in sig[nm].items())) > 1]
    return out, [nm for nm in falta if nm not in ambig], ambig


def resolver_freguesias(rows, mapa, pop):
    """Põe em r['_dc'] o dicofre de cada admissão.

    No freguesias_csv.json um nome pode apontar para uma lista de freguesias (por exemplo
    "AGUALVA CACEM", cidade dividida entre duas uniões de freguesias). Cada admissão com esse nome
    vai para a freguesia que o mesmo utente indicou noutras admissões; se não houver, para a
    freguesia onde moram mais utentes da mesma unidade de saúde; se não houver, reparte-se na
    proporção da população (Censos). Devolve contagens para o resumo.
    """
    duplos = []
    for r in rows:
        dc = mapa.get(norm(r['Freguesia']))
        r['_dc'] = None if isinstance(dc, list) else dc
        if isinstance(dc, list):
            duplos.append((r, dc))
    if not duplos:
        return {}
    por_ut, por_cs = defaultdict(Counter), defaultdict(Counter)
    for r in rows:
        if r['_dc']:
            u = r['Cartao_Utente'].strip(); cs = norm(r['Centro_Saude'])
            if u:
                por_ut[u][r['_dc']] += 1
            if cs not in SEM_CS:
                por_cs[cs][r['_dc']] += 1
    como, feito = Counter(), Counter()
    for r, cands in duplos:
        u = r['Cartao_Utente'].strip(); cs = norm(r['Centro_Saude'])
        for fonte, cont, minimo in (('mesmo utente', por_ut.get(u) if u else None, 1),
                                    ('unidade de saúde', por_cs.get(cs) if cs not in SEM_CS else None, 5)):
            if cont and sum(cont[d] for d in cands) >= minimo:
                r['_dc'] = max(cands, key=lambda d: (cont[d], -cands.index(d))); como[fonte] += 1
                break
        else:  # a freguesia que está mais abaixo da sua parte da população
            r['_dc'] = min(cands, key=lambda d: ((feito[d] + 1) / ((pop.get(d) or [1])[0]), cands.index(d))); como['população'] += 1
        feito[r['_dc']] += 1
    return {'como': como, 'para': feito}


def calcular(rows, base, mapa):
    U = base
    d0 = min(r['_data'] for r in rows); d1 = max(r['_data'] for r in rows)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    di = {d: i for i, d in enumerate(days)}
    pd = list(U['pd']); pix = {d: i for i, d in enumerate(pd) if d}
    usados = {d for v in mapa.values() for d in (v if isinstance(v, list) else [v])}
    for d in sorted(usados - set(pix)):
        pix[d] = len(pd); pd.append(d)
    cr = Counter(); ch = Counter(); sem_map = Counter()
    for r in rows:
        nm = norm(r['Freguesia']); dc = r['_dc']
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
    novo['meta'].pop('falta', None)
    falta = dias_em_falta(rows, days)
    if falta:
        novo['meta']['falta'] = falta
    return novo, sem_map


def dias_em_falta(rows, days):
    """Dias sem admissões, ou (havendo hora) sem nenhuma a partir das HORA_COMPLETA; o último dia fica de fora."""
    com = {r['_dia'] for r in rows}
    tem_hora = any(r['_h'] is not None for r in rows)
    tarde = {r['_dia'] for r in rows if r['_h'] is not None and r['_h'] >= HORA_COMPLETA}
    return [d for d in days[:-1] if d not in com or (tem_hora and d not in tarde)]


def ultimos_12_meses(rows):
    """Admissões dos últimos JANELA_FREQ dias do período e a data inicial (None se o período for mais curto)."""
    d1 = max(r['_data'] for r in rows); d0 = d1 - timedelta(days=JANELA_FREQ - 1)
    if min(r['_data'] for r in rows) >= d0:
        return rows, None
    return [r for r in rows if r['_data'] >= d0], d0.isoformat()


def calcular_freq(rows, mapa):
    rows, de = ultimos_12_meses(rows)
    per = defaultdict(list)
    for r in rows:
        if r['Cartao_Utente'].strip():
            per[r['Cartao_Utente'].strip()].append(r['_dc'])
    by = defaultdict(lambda: [0, 0, 0, 0]); T = [0, 0, 0, 0]
    for u, fl in per.items():
        n = len(fl); fq = n >= K_FREQ
        T[0] += 1; T[1] += fq; T[2] += n * fq; T[3] += n
        d = Counter(fl).most_common(1)[0][0]
        if d:
            b = by[d]; b[0] += 1; b[1] += fq; b[2] += n * fq; b[3] += n
    out = {'k': K_FREQ, 'tot': T, 'sem': sum(1 for r in rows if not r['Cartao_Utente'].strip()), 'by': dict(by)}
    if de:
        out['de'] = de
    return out


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
    rows, de = ultimos_12_meses(rows)
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
    out = {'k': K_FREQ, 'sem': len(rows) - len(com), 'fora': {'u': len(fora), 'a': sum(sum(r['c']) for r in fora)}, 'rows': dentro}
    if de:
        out['de'] = de
    return out


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
    erros = Counter(); datas_mal = []
    for i, r in enumerate(rows, start=2):  # linha 1 é o cabeçalho
        try:
            r['_data'] = data_iso(r['Data'])
        except ValueError:
            datas_mal.append(f'linha {i}: {r["Data"]!r}'); continue
        r['_dia'] = r['_data'].isoformat()
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
    if datas_mal:
        sys.exit(f'{len(datas_mal)} datas não reconhecidas na coluna Data, por exemplo: {"; ".join(datas_mal[:5])}')
    if erros['_l'] or erros['_p'] or erros['_a']:
        sys.exit(f'Valores não reconhecidos: local {erros["_l"]}, prioridade {erros["_p"]}, agrupamento {erros["_a"]}. Corrija o CSV ou o script.')
    if erros['hora']:
        print(f'aviso: {erros["hora"]} admissões sem hora reconhecida ficam fora do quadro hora x dia')

    texto, base, extra = ler_dados()
    if os.path.exists(MAPA):
        with open(MAPA, encoding='utf-8') as fh:
            mapa = {norm(k): v for k, v in json.load(fh).items() if v}  # aceita nomes com acentos ou minúsculas; "" ou [] = sem freguesia
    else:
        mapa, fora, ambig = reconstruir_mapa(rows, base)
        print(f'correspondência de freguesias reconstruída: {len(mapa)} nomes; {len(fora)} não existem no mapa atual (ficam "sem freguesia", como antes)')
        if ambig:
            print(f'   ATENÇÃO, {len(ambig)} nomes servem a mais de uma freguesia; decidir à mão no freguesias_csv.json: {ambig}')
        if not verificar:
            m4.gravar(MAPA, json.dumps(dict(sorted(mapa.items())), ensure_ascii=False, indent=1))
            print('guardada em', os.path.relpath(MAPA))
    rep = resolver_freguesias(rows, mapa, extra.get('pop', {}))
    if rep:
        nomes = {d: f['n'] for f in base['feats'] if f['t'] == 1 for d in [f['d']]}
        print(f'nomes com mais de uma freguesia possível: {sum(rep["como"].values())} admissões repartidas, por '
              + ', '.join(f'{k} {n}' for k, n in rep['como'].most_common()))
        for d, n in rep['para'].most_common():
            print(f'   {n:6d}  -> {nomes.get(d, d)}')
    novo, sem_map = calcular(rows, base, mapa)
    nx = dict(extra, freq=calcular_freq(rows, mapa), cs=calcular_cs(rows))
    if sem_map:
        print(f'freguesias sem correspondência ({sum(sem_map.values())} admissões contam como "sem freguesia");')
        print(f'   acrescentar a {os.path.relpath(MAPA)} como  "NOME": "dicofre"')
        for nm, n in sem_map.most_common(30):
            print(f'   {n:6d}  "{norm(nm)}"')
    print(f'período {novo["days"][0]} a {novo["days"][-1]} ({len(novo["days"])} dias)')
    if novo['meta'].get('falta'):
        fl = novo['meta']['falta']
        print(f'aviso: {len(fl)} dias sem dados ou incompletos (falta o report): {", ".join(fl[:20])}' + (' …' if len(fl) > 20 else ''))

    if verificar:
        for k in ('days', 'pd', 'R', 'H', 'meta'):
            print(f'  {k:5s}', 'igual' if novo[k] == base[k] else 'DIFERENTE')
        for k in ('freq', 'cs'):
            print(f'  {k:5s}', 'igual' if nx[k] == extra.get(k) else 'DIFERENTE')
        print('  ficheiro', 'igual' if escrever_dados(novo, nx) == texto else 'DIFERENTE (ver linhas acima)')
        return
    if '--sem-html' in sys.argv:
        m4.gravar(DADOS, escrever_dados(novo, nx))
        print('escrito', os.path.relpath(DADOS))
    else:
        m4.atualizar_dados(escrever_dados(novo, nx))


if __name__ == '__main__':
    main()
