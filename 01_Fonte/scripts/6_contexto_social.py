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

Pode correr-se de qualquer pasta (precisa de openpyxl). Sem argumentos descarrega o ficheiro
do INE; com um argumento usa um .zip ou .xlsx já descarregado:
    python 01_Fonte/scripts/6_contexto_social.py [FS2021SeccaoTot.zip]
Acrescenta (ou substitui) window.URG.soc no 01_Fonte/urgencias-data.js e volta a embeber esse
ficheiro no "Origem das Urgencias.html" da raiz.
"""
import io
import os
import sys
import urllib.request
import zipfile

import openpyxl

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
m4 = __import__('4_embeber_no_html')
m5 = __import__('5_atualizar_dados')
URL = 'https://mapas.ine.pt/download/2021FicheiroSintese/FS2021SeccaoTot.zip'
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
    _, U, extra = m5.ler_dados()
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

    extra = dict(extra, soc={'src': FONTE, 'by': by})
    m4.atualizar_dados(m5.escrever_dados(U, extra))


if __name__ == '__main__':
    main()
