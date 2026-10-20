"""Dados mensais da ULS Amadora/Sintra no Portal da Transparência do SNS (API pública, sem registo).

Vai buscar, desde janeiro de 2024:
  urgência hospitalar: atendimentos por tipo (geral, pediátrica, obstétrica) e por cor da triagem;
  internamento: taxa de ocupação (acumulada no ano);
  cuidados de saúde primários: consultas médicas (presenciais, não presenciais, domicílio),
      contactos de enfermagem, utentes inscritos e sem médico de família, taxa de utilização.
As séries de urgência vêm acumuladas no ano no portal; aqui guardam-se já como valores do mês.
Atualiza também o indicador "Sem médico de família" do topo (window.URG.sns) com o mês mais recente.

Grava window.URG.snsm no 01_Fonte/urgencias-data.js e volta a embeber os dados no HTML da raiz.
Pode correr-se de qualquer pasta (só precisa de internet):
    python 01_Fonte/scripts/7_dados_sns.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
API = 'https://transparencia.sns.gov.pt/api/explore/v2.1/catalog/datasets'
DESDE = '2024-01'
FONTE = 'Portal da Transparência do SNS (transparencia.sns.gov.pt)'


def registos(ds, onde, ordem):
    out, off = [], 0
    while True:
        q = urllib.parse.urlencode({'where': onde, 'order_by': ordem, 'limit': 100, 'offset': off})
        r = urllib.request.Request(f'{API}/{ds}/records?{q}', headers={'User-Agent': 'dashboard-uls-amadora-sintra'})
        lote = json.load(urllib.request.urlopen(r, timeout=60))['results']
        out += lote; off += len(lote)
        if len(lote) < 100:
            return out


def mensal(acum, nome, avisos):
    """De valores acumulados no ano para valores do mês (janeiro fica igual; meses em falta ficam None).

    Um acumulado menor do que o do mês anterior (correção do portal, mês incompleto) daria um valor
    negativo: fica None e entra nos avisos.
    """
    out = {}
    for m in sorted(acum):
        y, mo = int(m[:4]), int(m[5:])
        ant = f'{y}-{mo - 1:02d}'
        if mo == 1:
            out[m] = acum[m]
        elif ant in acum:
            out[m] = [None if a is None or b is None else a - b for a, b in zip(acum[m], acum[ant])]
            if any(v is not None and v < 0 for v in out[m]):
                avisos.append(f'{nome} {m}: acumulado menor do que em {ant}; o mês fica sem valor')
                out[m] = [None if v is not None and v < 0 else v for v in out[m]]
        else:
            out[m] = [None] * len(acum[m])
    return out


def invulgares(serie, nome, avisos, i=None, fator=3):
    """Avisa de meses muito longe da mediana da série (mais de 'fator' vezes acima ou abaixo)."""
    val = {m: (v[i] if i is not None else v) for m, v in serie.items()}
    ok = sorted(v for v in val.values() if v is not None and v > 0)
    if len(ok) < 6:
        return
    med = ok[len(ok) // 2]
    for m, v in sorted(val.items()):
        if v is not None and (v > med * fator or v < med / fator):
            avisos.append(f'{nome} {m}: {v} muito longe da mediana ({med}); confirmar no portal')


def recolher():
    uls = f'instituicao like "Amadora/Sintra" and tempo >= "{DESDE}"'
    csp = f'entidade like "ULS Amadora / Sintra" and tempo >= "{DESDE}"'
    urg = {r['tempo']: [r['urgencias_geral'], r['urgencias_pediatricas'], r['urgencia_obstetricia'], r['total_urgencias']]
           for r in registos('atendimentos-por-tipo-de-urgencia-hospitalar-link', uls, 'tempo asc')}
    cores = ['vermelha', 'laranja', 'amarela', 'verde', 'azul', 'branca']
    tri = {r['tempo']: [r[f'no_de_atendimentos_em_urgencia_su_triagem_manchester_{c}'] for c in cores] + [r['no_de_atendimentos_em_sem_triagem_manchester']]
           for r in registos('atendimentos-em-urgencia-triagem-manchester', uls, 'tempo asc')}
    ocup = {r['tempo']: r['taxa_anual_de_ocupacao_em_internamento'] for r in registos('ocupacao-do-internamento', uls, 'tempo asc')}
    cons = {r['tempo']: [r['no_de_consultas_medicas_presencias_qt'], r['no_de_consultas_medicas_nao_presenciais_ou_inespecificas_qt'], r['no_de_consultas_medicas_ao_domicilio_qt']]
            for r in registos('evolucao-das-consultas-medicas-nos-csp', csp, 'tempo asc')}
    enf = {r['tempo']: [r['no_de_contactos_de_enfermagem_presenciais_qt'], r['no_de_contactos_de_enfermagem_nao_presenciais_qt']]
           for r in registos('evolucao-dos-contactos-de-enfermagem-nos-csp', csp, 'tempo asc')}
    acesso = {r['tempo']: [r['taxa_de_utilizacao_global_de_consultas_medicas_1_ano'], r['taxa_de_utilizacao_de_consultas_medicas_3_anos']]
              for r in registos('acesso-de-consultas-medicas-pela-populacao-inscrita', csp, 'tempo asc')}
    insc_r = registos('utentes-inscritos-em-cuidados-de-saude-primarios', f'aces like "ULS Amadora / Sintra" and periodo >= "{DESDE}"', 'periodo asc')
    insc = {r['periodo']: [r['utentes_inscritos_csp'], r['total_utentes_sem_mdf_atribuido'], r['total_utentes_sem_mdf_atribuido_por_opcao']] for r in insc_r}
    avisos = []
    snsm = {'fonte': FONTE, 'obtido': date.today().isoformat(), 'desde': DESDE,
            'urg': mensal(urg, 'urgência', avisos), 'tri': mensal(tri, 'triagem', avisos), 'ocup': ocup, 'cons': cons, 'enf': enf, 'acesso': acesso, 'insc': insc}
    invulgares(snsm['urg'], 'urgência (total)', avisos, 3)
    invulgares(cons, 'consultas presenciais', avisos, 0)
    invulgares(enf, 'enfermagem presencial', avisos, 0)
    return snsm, insc_r, avisos


def main():
    sys.path.insert(0, AQUI)
    m5 = __import__('5_atualizar_dados')
    texto, base, extra = m5.ler_dados()
    snsm, insc_r, avisos = recolher()
    for k in ('urg', 'tri', 'cons', 'enf', 'insc'):
        meses = sorted(snsm[k])
        print(f'{k:5s} {len(meses):3d} meses  {meses[0] if meses else "-"} a {meses[-1] if meses else "-"}')
    for a in avisos:
        print('aviso:', a)
    ult = max(snsm['urg'], default=None)
    if ult:
        print(f'nota: o último mês publicado ({ult}) pode ainda ser corrigido pelo portal; voltar a correr no mês seguinte')
    if not snsm['urg'] or not snsm['insc']:
        sys.exit('A API não devolveu dados da ULS; nada foi alterado.')
    ult = insc_r[-1]
    sns = {'per': ult['periodo'], 'insc': ult['utentes_inscritos_csp'], 'sem': ult['total_utentes_sem_mdf_atribuido'], 'ent': ult['aces']}
    print('sem médico de família:', sns['per'], sns['sem'], 'de', sns['insc'], f'(antes: {extra.get("sns", {}).get("per")})')
    extra = dict(extra, sns=sns, snsm=snsm)
    novo = m5.escrever_dados(base, extra)
    if novo == texto:
        print('sem alterações'); return
    m5.m4.atualizar_dados(novo)


if __name__ == '__main__':
    main()
