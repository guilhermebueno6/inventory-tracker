"""Protótipo do parser do relatório de vendas do ML — valida as regras do ESCOPO.md §2."""
import re, warnings, unicodedata
from datetime import datetime
import openpyxl
warnings.filterwarnings("ignore")

MESES = {m: i for i, m in enumerate(
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split(), 1)}

# índices 1-based, conforme §2.2
C = dict(venda=1, data=2, deposito=3, estado=4, unidades=8, cancel=18,
         total=19, sku=23, mlb=24, titulo=25, variacao=26, preco=27,
         dev_unid=49, dev_resultado=59, dev_destino=60, forma_entrega=43)

# §2.5 — classificar por Forma de entrega, NUNCA pelo nome do depósito (texto livre)
def classifica_local(forma_entrega: str) -> str:
    f = forma_entrega.lower()
    return "FULL" if ("fulfillment" in f or "full" in f) else "CASA"

def limpa(v):
    if v is None: return ""
    return str(v).strip()

def parse_data(txt):
    m = re.match(r"(\d{1,2}) de (\w+) de (\d{4})(?:\s+(\d{1,2}):(\d{2}))?", limpa(txt), re.I)
    if not m: return None
    d, mes, a, h, mi = m.groups()
    mes = unicodedata.normalize("NFC", mes.lower())
    if mes not in MESES: return None
    return datetime(int(a), MESES[mes], int(d), int(h or 0), int(mi or 0))

def acha_cabecalho(rows):
    for i, r in enumerate(rows[:15]):
        if any(limpa(c) == "N.º de venda" for c in r):
            return i
    raise ValueError("Não parece ser o relatório de vendas do Mercado Livre.")

def parse(caminho):
    ws = openpyxl.load_workbook(caminho, read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    h = acha_cabecalho(rows)
    g = lambda r, k: limpa(r[C[k] - 1])
    out = []
    for r in rows[h + 1:]:
        if not limpa(r[0]): continue
        un = g(r, "unidades")
        qtd = int(float(un)) if un else 0
        dev = g(r, "dev_unid")
        out.append(dict(
            venda=g(r, "venda"), data=parse_data(g(r, "data")),
            deposito=g(r, "deposito"), estado=g(r, "estado"),
            sku=g(r, "sku").strip().lower(), mlb=g(r, "mlb"),
            titulo=g(r, "titulo"), variacao=g(r, "variacao"),
            forma_entrega=g(r, "forma_entrega"),
            local=classifica_local(g(r, "forma_entrega")),
            qtd=qtd, devolvidas=int(float(dev)) if dev else 0,
            cancelado=bool(g(r, "cancel")), total=g(r, "total")))
    return out

if __name__ == "__main__":
    import sys, collections
    linhas = parse(sys.argv[1])
    print(f"linhas lidas: {len(linhas)}")
    print(f"datas: {min(l['data'] for l in linhas):%d/%m/%Y} a {max(l['data'] for l in linhas):%d/%m/%Y}")
    print(f"datas não parseadas: {sum(1 for l in linhas if l['data'] is None)}")
    print(f"sem SKU: {sum(1 for l in linhas if not l['sku'])}")
    print(f"N.º de venda únicos: {len(set(l['venda'] for l in linhas))}")
    print(f"depósitos: {set(l['deposito'] for l in linhas)}")
    print(f"formas de entrega: {collections.Counter(l['forma_entrega'] for l in linhas)}")
    print(f"local do estoque: {collections.Counter(l['local'] for l in linhas)}")
    print(f"devoluções: {sum(l['devolvidas'] for l in linhas)} | cancelados: {sum(l['cancelado'] for l in linhas)}")
    print(f"unidades totais a abater: {sum(l['qtd'] for l in linhas)}")
    print("\nbaixa por SKU (case-insensitive):")
    for sku, q in collections.Counter({s: sum(l['qtd'] for l in linhas if l['sku'] == s)
                                       for s in set(l['sku'] for l in linhas)}).most_common():
        print(f"  {q:>3}x  {sku}")
    # idempotência: reimportar não muda nada
    vistos = set(l["venda"] for l in linhas)
    novas = [l for l in parse(sys.argv[1]) if l["venda"] not in vistos]
    print(f"\n>>> reimportação do mesmo arquivo: {len(novas)} vendas novas (esperado: 0)")
