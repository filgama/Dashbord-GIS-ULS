"""Contexto social por freguesia (INE, Censos 2021) para a secção "Urgência e contexto social".

Fonte: INE, Censos 2021, Ficheiro Síntese por secção estatística (linhas de total por freguesia),
    https://mapas.ine.pt/download/2021FicheiroSintese/FS2021SeccaoTot.zip
    (dicionário de variáveis: https://mapas.ine.pt/download/C2021_FSINTESE_VARIAVEIS.csv)

Guarda, para cada freguesia do mapa (código DICOFRE de 6 algarismos), pares numerador/denominador:
    pessoas com 65+ anos / pessoas
    desempregados (à procura de 1.º ou de novo emprego) / pessoas com atividade económica
    pessoas com ensino superior / pessoas com 25 ou mais anos (o INE conta as crianças pequenas como
        "sem escolaridade", por isso a escolaridade baixa confundir-se-ia com a idade)
    edifícios com necessidade de reparação / edifícios clássicos

Correr a partir da raiz do repositório (precisa de openpyxl). Sem argumentos descarrega o ficheiro
do INE; com um argumento usa um .zip ou .xlsx já descarregado:
    python 01_Fonte/scripts/5_contexto_social.py [FS2021SeccaoTot.zip]
Acrescenta (ou substitui) window.URG.soc no 01_Fonte/urgencias-data.js e volta a embeber esse
ficheiro no "Origem das Urgencias.html" da raiz.
"""
import base64
import gzip
import io
import json
import re
import sys
import urllib.request
import zipfile

import openpyxl

URL = 'https://mapas.ine.pt/download/2021FicheiroSintese/FS2021SeccaoTot.zip'
DADOS = '01_Fonte/urgencias-data.js'
DESTINO = 'Origem das Urgencias.html'
UUID_DADOS = '68a45299-35ec-4170-9f12-28052a2964ff'
MARCA = ';window.URG.soc='
FONTE = 'INE, Censos 2021, Ficheiro Síntese por secção (totais por freguesia)'
# cada indicador: (numerador, denominador), cada um uma lista de colunas a somar
IND = [
    (['N_INDIVIDUOS_65_OU_MAIS'], ['N_INDIVIDUOS']),
    (['N_INDIVIDUOS_DESEMPREGADOS_1EMP', 'N_INDIVIDUOS_DESEMPREGADOS_NOVOEMP'], ['N_INDIVIDUOS_COM_ATIVIDADE_ECONOMICA']),
    (['N_INDIVIDUO_ENSINCOMP_SUP'], ['N_INDIVIDUOS_25A64', 'N_INDIVIDUOS_65_OU_MAIS']),
    (['N_EDIFICIOS_COM_NEC_REPARACAO'], ['N_EDIFICIOS_CLASSICOS']),
]


def livro(arg):
    if arg and arg.lower().endswith('.xlsx'):
        return openpyxl.load_workbook(arg, read_only=True)
    raw = open(arg, 'rb').read() if arg else urllib.request.urlopen(URL, timeout=300).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    nome = next(i for i in z.infolist() if i.filename.lower().endswith('.xlsx'))
    return openpyxl.load_workbook(io.BytesIO(z.read(nome)), read_only=True)


def main():
    src = open(DADOS, encoding='utf-8', newline='').read()
    base = src[:src.index(MARCA)] if MARCA in src else src
    U = json.JSONDecoder().raw_decode(base, base.index('{'))[0]
    fregs = {f['d'] for f in U['feats'] if f['t'] == 1}

    linhas = livro(sys.argv[1] if len(sys.argv) > 1 else None).worksheets[0].iter_rows(values_only=True)
    next(linhas)  # título
    cab = next(linhas)
    ix = {k: i for i, k in enumerate(cab)}
    by = {}
    for r in linhas:
        d = r[ix['FREGUESIA']]
        if r[ix['SECCAO']] is None and d is not None and str(d) in fregs:
            soma = lambda cols: sum(int(r[ix[c]] or 0) for c in cols)
            by[str(d)] = [v for num, den in IND for v in (soma(num), soma(den))]
    print('freguesias com dados:', len(by), 'de', len(fregs), '| em falta:', sorted(fregs - set(by)))

    soc = {'src': FONTE, 'by': by}
    src = base.rstrip('\n') + '\n' + MARCA + json.dumps(soc, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(DADOS, 'w', encoding='utf-8', newline='').write(src)

    html = open(DESTINO, encoding='utf-8', newline='').read()
    m = re.search(r'(<script type="__bundler/manifest">)(.*?)(</script>)', html, re.S)
    antigo = json.loads(m.group(2))[UUID_DADOS]['data']
    novo = base64.b64encode(gzip.compress(src.encode('utf-8'), mtime=0)).decode('ascii')
    assert m.group(2).count(antigo) == 1
    html = html[:m.start(2)] + m.group(2).replace(antigo, novo) + html[m.end(2):]
    open(DESTINO, 'w', encoding='utf-8', newline='\n').write(html)
    print('dados atualizados em', DADOS, 'e embebidos em', DESTINO)


if __name__ == '__main__':
    main()
