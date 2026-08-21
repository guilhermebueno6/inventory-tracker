"""Protótipo da lógica de kits — valida ESCOPO.md §4.2 e §5.2.

Regras provadas aqui:
  1. Kit não tem estoque próprio; disponibilidade = min(saldo // qtd).
  2. Vender kit explode em baixas de componentes.
  3. Componente compartilhado entre kits e venda avulsa se comporta corretamente.
"""
from collections import defaultdict

class Estoque:
    def __init__(self, saldos, composicoes):
        self.saldo = dict(saldos)               # sku_simples -> qtd
        self.comp = {k: dict(v) for k, v in composicoes.items()}  # sku_kit -> {componente: qtd}
        self.movimentos = []

    def eh_kit(self, sku):
        return sku in self.comp

    def disponivel(self, sku):
        """§4.2 — kit não tem saldo; é derivado do gargalo."""
        if not self.eh_kit(sku):
            return self.saldo.get(sku, 0)
        return min(self.saldo.get(c, 0) // q for c, q in self.comp[sku].items())

    def gargalo(self, sku):
        if not self.eh_kit(sku):
            return None
        return min(self.comp[sku], key=lambda c: self.saldo.get(c, 0) // self.comp[sku][c])

    def explode(self, sku, qtd):
        """§5.1 passo 4 — 1 linha de venda vira N baixas de componentes."""
        if not self.eh_kit(sku):
            return [(sku, qtd)]
        return [(c, q * qtd) for c, q in self.comp[sku].items()]

    def vender(self, ref, sku, qtd):
        for componente, q in self.explode(sku, qtd):
            self.saldo[componente] = self.saldo.get(componente, 0) - q
            # produto_vendido_id = sku → é o que explica o histórico (§4.3)
            self.movimentos.append(dict(ref=ref, produto=componente, qtd=-q,
                                        vendido_como=sku))

    def kits_afetados(self, componente):
        """§5.2 — alerta em cascata."""
        return [k for k, c in self.comp.items() if componente in c]


if __name__ == "__main__":
    e = Estoque(
        saldos={"mord.mao.rosa": 14, "mord.pe.rosa": 6, "embalagem": 80,
                "mord.mao.azul": 10, "mord.pe.azul": 20},
        composicoes={
            "kit.maope.rosa":  {"mord.mao.rosa": 1, "mord.pe.rosa": 1, "embalagem": 1},
            "kit.maope.azul":  {"mord.mao.azul": 1, "mord.pe.azul": 1, "embalagem": 1},
            "kit.maope.combo": {"mord.mao.rosa": 1, "mord.mao.azul": 1, "embalagem": 2},
        })

    def mostra(titulo):
        print(f"\n{titulo}")
        for k in e.comp:
            print(f"   {k:<18} dá para montar {e.disponivel(k):>3}  (limitado por: {e.gargalo(k)})")
        print("   componentes:", {k: v for k, v in sorted(e.saldo.items())})

    mostra("estado inicial")

    assert e.disponivel("kit.maope.rosa") == 6, "gargalo é mord.pe.rosa (6)"
    assert e.gargalo("kit.maope.rosa") == "mord.pe.rosa"
    assert e.disponivel("kit.maope.combo") == 10, "combo usa 2 embalagens: min(14,10,40)=10"

    # venda mista: 2 kits rosa + 1 avulso do MESMO componente + 1 combo
    e.vender("V001", "kit.maope.rosa", 2)
    e.vender("V002", "mord.mao.rosa", 1)      # avulso, componente compartilhado
    e.vender("V003", "kit.maope.combo", 1)
    mostra("depois de: 2x kit rosa, 1x mordedor rosa avulso, 1x combo")

    assert e.saldo["mord.mao.rosa"] == 14 - 2 - 1 - 1 == 10
    assert e.saldo["mord.pe.rosa"] == 6 - 2 == 4
    assert e.saldo["embalagem"] == 80 - 2 - 2 == 76
    assert e.disponivel("kit.maope.rosa") == 4

    print("\ncascata — se 'mord.pe.rosa' cruzar o mínimo, trava:",
          e.kits_afetados("mord.pe.rosa"))
    print("cascata — 'embalagem' trava:", e.kits_afetados("embalagem"))

    # invariante do livro-razão (§11.1)
    por_produto = defaultdict(int)
    for m in e.movimentos:
        por_produto[m["produto"]] += m["qtd"]
    esperado = {"mord.mao.rosa": -4, "mord.pe.rosa": -2, "embalagem": -4, "mord.mao.azul": -1}
    assert dict(por_produto) == esperado, dict(por_produto)

    print("\nhistórico explicável (§4.3 produto_vendido_id):")
    for m in e.movimentos:
        origem = "" if m["produto"] == m["vendido_como"] else f"  ← saiu por {m['vendido_como']}"
        print(f"   {m['ref']}  {m['qtd']:>3}  {m['produto']}{origem}")

    print("\n✅ todas as invariantes de kit passaram")
