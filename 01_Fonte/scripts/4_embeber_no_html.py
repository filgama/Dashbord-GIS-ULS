"""Volta a embeber o dashboard (01_Fonte/Origem das Urgencias.dc.html) no ficheiro unico da raiz.

O "Origem das Urgencias.html" da raiz e um pacote com tudo embebido: um template (o .dc.html com
os recursos substituidos por identificadores) e um manifesto com os scripts, estilos e fontes.
Este script so troca a parte do template que vem depois de </helmet> (o corpo do dashboard e o
seu script), convertendo os atributos camelCase para o formato que o pacote usa (sc-camel-...).
Os dados (urgencias-data.js) atualizam-se com o script 5, que chama atualizar_dados() deste ficheiro.

Correr a partir da raiz do repositorio:  python3 01_Fonte/scripts/4_embeber_no_html.py
Com --verificar, so confirma que o HTML da raiz esta em dia com o .dc.html (nao escreve nada).
"""
import json
import re
import sys

FONTE = '01_Fonte/Origem das Urgencias.dc.html'
DESTINO = 'Origem das Urgencias.html'
SCRIPT_TAG = '<script type="text/x-dc" data-dc-script>'

TPL_RE = re.compile(r'(<script type="__bundler/template">)(.*?)(</script>)', re.S)
CAMEL_RE = re.compile(r'(?<=\s)([a-z]+(?:[A-Z][a-z]*)+)(?==")')


def kebab(nome):
    return 'sc-camel-' + re.sub(r'([A-Z])', lambda m: '-' + m.group(1).lower(), nome)


def corpo_do_template(dc):
    """Parte do .dc.html depois de </helmet>, no formato em que aparece dentro do pacote."""
    corpo = dc[dc.index('</helmet>'):]
    i = corpo.index(SCRIPT_TAG)
    marcacao, script = corpo[:i], corpo[i + len(SCRIPT_TAG):]
    marcacao = CAMEL_RE.sub(lambda m: kebab(m.group(1)), marcacao)
    script = script.rstrip()
    assert script.endswith('</html>')
    script = script[:script.rindex('</body>')].rstrip('\n') + '\n\n\n</body></html>'
    return marcacao + '<script type="text/x-dc" data-dc-script="">' + script


def main():
    dc = open(FONTE, encoding='utf-8').read()
    html = open(DESTINO, encoding='utf-8').read()
    m = TPL_RE.search(html)
    tpl = json.loads(m.group(2))
    novo = tpl[:tpl.index('</helmet>')] + corpo_do_template(dc)
    if '--verificar' in sys.argv:
        print('em dia' if novo == tpl else 'DESATUALIZADO')
        sys.exit(0 if novo == tpl else 1)
    # o template fica como string JSON dentro de <script>: escapar "</" para nao fechar a tag
    enc = json.dumps(novo, ensure_ascii=False).replace('</', '<\\u002F')
    html = html[:m.start(2)] + enc + html[m.end(2):]
    open(DESTINO, 'w', encoding='utf-8', newline='\n').write(html)  # LF, também no Windows
    print('HTML atualizado:', DESTINO)


def atualizar_dados():
    """Substitui no pacote o recurso urgencias-data.js pela versão atual de 01_Fonte (chamado pelo script 5)."""
    import base64
    import gzip
    novo = open(FONTE.replace('Origem das Urgencias.dc.html', 'urgencias-data.js'), encoding='utf-8').read()
    html = open(DESTINO, encoding='utf-8').read()
    m = re.search(r'(<script type="__bundler/manifest">)(.*?)(</script>)', html, re.S)
    man = json.loads(m.group(2))
    alvo = [k for k, v in man.items() if v.get('compressed') and 'javascript' in v.get('mime', '')
            and gzip.decompress(base64.b64decode(v['data']))[:11] == b'window.URG=']
    assert len(alvo) == 1, 'recurso dos dados não encontrado no pacote'
    velho = man[alvo[0]]['data']
    dados = base64.b64encode(gzip.compress(novo.encode('utf-8'), mtime=0)).decode('ascii')
    assert html.count(velho) == 1
    html = html.replace(velho, dados)
    open(DESTINO, 'w', encoding='utf-8', newline='\n').write(html)
    print('dados atualizados no HTML:', DESTINO)


if __name__ == '__main__':
    main()
