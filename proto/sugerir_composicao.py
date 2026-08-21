# -*- coding: utf-8 -*-
"""Sugestão de componentes por nome + conferência por custo (ESCOPO.md §5.2.2 e §5.2.3).

Substitui a tentativa de INFERIR composição por custo, que foi medida e descartada
— ver Anexo B do escopo. Aqui o custo só CONFERE o que a usuária montou.

Uso:
    python3 sugerir_composicao.py atributosprodutos.csv
    python3 sugerir_composicao.py atributosprodutos.csv KIT.MAOPE.ROSA
"""
import csv, sys, unicodedata


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def eh_kit(sku: str) -> bool:
    """Heurística da §5.3 passo 3. Sugere; a usuária confirma."""
    return "kit" in norm(sku) or "+" in sku


def tokens(sku: str) -> set:
    return {t for t in norm(sku).replace("+", ".").split(".") if len(t) >= 3}


def carregar(caminho: str) -> dict:
    texto = open(caminho, encoding="utf-8").read().splitlines()
    linhas = [r for r in csv.DictReader(texto, delimiter=";") if r.get("SKU")]
    return {r["SKU"].strip(): {"custo": float(r["CUSTO"]),
                               "imposto": float(r["IMPOSTO"])} for r in linhas}


def sugerir(kit: str, simples, n=6):
    """§5.2.2 — ranqueia os simples pela fração de tokens que aparecem no nome do kit."""
    alvo = norm(kit).replace(".", "").replace("+", "")
    out = []
    for s in simples:
        ts = tokens(s)
        if not ts:
            continue
        hits = sum(1 for t in ts if t[:4] in alvo)
        if hits:
            out.append((hits / len(ts), s))
    return sorted(out, reverse=True)[:n]


def conferir(kit: str, composicao: dict, cat: dict):
    """§5.2.3 — a soma dos componentes bate com o custo do kit?

    composicao: {sku_componente: quantidade}
    Devolve (ok, soma, diferenca, mensagem). NUNCA bloqueia — só avisa.
    """
    soma = round(sum(cat[c]["custo"] * q for c, q in composicao.items()), 2)
    alvo = cat[kit]["custo"]
    dif = round(soma - alvo, 2)
    if abs(dif) < 0.01:
        return True, soma, dif, "✅ soma dos componentes bate com o custo do kit"
    if dif < 0:
        return False, soma, dif, f"⚠️ faltam R$ {-dif:.2f} — esqueceu algum item?"
    return False, soma, dif, f"⚠️ passou R$ {dif:.2f} — quantidade a mais, ou custo desatualizado?"


if __name__ == "__main__":
    cat = carregar(sys.argv[1])
    kits = sorted(s for s in cat if eh_kit(s))
    simples = sorted(s for s in cat if not eh_kit(s))
    print(f"{len(cat)} SKUs — {len(kits)} candidatos a kit, {len(simples)} simples\n")

    alvos = [sys.argv[2]] if len(sys.argv) > 2 else kits[:6]
    for k in alvos:
        print(f"── {k}   (custo R$ {cat[k]['custo']:.2f})")
        for score, s in sugerir(k, simples):
            print(f"     {score:>4.0%}  {s:<38} R$ {cat[s]['custo']:>6.2f}")
        print()

    print("── conferência por custo (§5.2.3) ──")
    for kit, comp in [("KIT.MAOPE.ROSA", {"mord.mao.rosa": 1, "mord.pe.rosa": 1}),
                      ("KIT.MAOPE.AZUL", {"mord.mao.azul": 1, "mord.pe.azul": 1}),
                      ("KIT.MAOPE.ROSA", {"mord.mao.rosa": 1}),
                      ("KIT.MAOPE.ROSA", {"mord.mao.rosa": 1, "mord.pe.rosa": 1, "manta.rosa": 1})]:
        ok, soma, dif, msg = conferir(kit, comp, cat)
        itens = " + ".join(f"{q}x {c}" if q > 1 else c for c, q in comp.items())
        print(f"   {kit} = {itens}")
        print(f"      R$ {soma:.2f}  {msg}")
