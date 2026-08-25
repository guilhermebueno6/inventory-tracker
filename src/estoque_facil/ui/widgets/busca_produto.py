"""Campo de busca de produto com lista suspensa — ESCOPO.md §5.2.1.

Para ligar um item a um kit era preciso saber o código ou o nome exato: o campo
pegava o PRIMEIRO resultado da busca e adicionava sem mostrar o que tinha
achado. Com 195 SKUs parecidos (`mord.mao.rosa`, `mord.mao.azul`), digitar
`mord.mao` entrava com o item errado e nada na tela avisava.

Aqui a lista aparece enquanto ela digita, casando em qualquer pedaço do nome ou
do código, e o item só entra quando ela escolhe um da lista.
"""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QCompleter, QLineEdit, QWidget

from ...core import repo
from ...core.models import TipoProduto, normalizar_sku
from .comuns import moeda

MAX_VISIVEIS = 8
SEPARADOR = "  ·  "


def rotulo_de_busca(produto) -> str:
    """Nome e código na mesma linha: é por qualquer um dos dois que ela procura."""
    nome = (produto.nome or "").strip()
    if not nome or nome == produto.sku:
        return produto.sku
    return f"{nome}{SEPARADOR}{produto.sku}"


class CampoBuscaProduto(QLineEdit):
    """Campo de texto que abre a lista dos produtos que casam com o que foi digitado.

    Emite `escolhido(id_do_produto)` quando ela escolhe um item da lista.
    """

    escolhido = Signal(int)

    def __init__(
        self,
        session,
        *,
        tipo: str | None = TipoProduto.SIMPLES,
        ignorar: set[int] | None = None,
        pai: QWidget | None = None,
    ):
        super().__init__(pai)
        self.session = session
        self._tipo = tipo
        self._ignorar = set(ignorar or ())
        self.setPlaceholderText("Procurar item pelo nome ou código…")
        self.setClearButtonEnabled(True)

        self._modelo = QStandardItemModel(self)
        self._completador = QCompleter(self._modelo, self)
        self._completador.setCaseSensitivity(Qt.CaseInsensitive)
        # o padrão do Qt só casa o COMEÇO do texto: com nomes de anúncio longos
        # ("Kit Mordedor Mãozinha…"), procurar por "mordedor" não achava nada
        self._completador.setFilterMode(Qt.MatchContains)
        self._completador.setCompletionMode(QCompleter.PopupCompletion)
        self._completador.setMaxVisibleItems(MAX_VISIVEIS)
        self._completador.activated[QModelIndex].connect(self._escolher)
        self.setCompleter(self._completador)

        lista = self._completador.popup()
        lista.setObjectName("listaBusca")
        # o corte fica no meio do nome, não no fim: o código do produto, que é o
        # que distingue rosa de azul, continua visível na linha
        lista.setTextElideMode(Qt.ElideMiddle)

        self.recarregar()

    # ------------------------------------------------------------------ dados

    def recarregar(self) -> None:
        """Relê o catálogo. Chamar quando o que pode ser escolhido mudar."""
        self._modelo.clear()
        for p in repo.buscar(self.session, tipo=self._tipo):
            if p.id in self._ignorar:
                continue
            item = QStandardItem(rotulo_de_busca(p))
            item.setData(p.id, Qt.UserRole)
            item.setToolTip(f"{p.rotulo}\n{p.sku} — {moeda(p.custo)}")
            self._modelo.appendRow(item)

    def ignorar(self, ids) -> None:
        self._ignorar = set(ids)
        self.recarregar()

    # ------------------------------------------------------------------ lista

    def lista_aberta(self) -> bool:
        return self._completador.popup().isVisible()

    def escolha_destacada(self) -> bool:
        """Ela desceu a seta até um item da lista — o Enter é dele, não do campo.

        O QLineEdit emite `returnPressed` ANTES de o QCompleter avisar a escolha
        (medido: os dois disparam, nessa ordem). Sem esta pergunta, o Enter na
        lista adicionaria dois itens: o destacado e o que o texto casasse.
        """
        lista = self._completador.popup()
        return bool(
            lista.isVisible()
            and lista.selectionModel() is not None
            and lista.selectionModel().hasSelection()
        )

    def fechar_lista(self) -> None:
        self._completador.popup().hide()

    def abrir_lista(self, texto: str | None = None) -> None:
        """Mostra a lista sem esperar a próxima tecla — prefixo vazio mostra tudo."""
        self._completador.setCompletionPrefix(
            self.text() if texto is None else texto
        )
        if self._completador.completionCount():
            self._completador.complete()

    def opcoes(self, texto: str | None = None) -> list[tuple[str, int]]:
        """O que a lista mostraria para este texto — usado pela tela e nos testes."""
        self._completador.setCompletionPrefix(
            self.text() if texto is None else texto
        )
        modelo = self._completador.completionModel()
        return [
            (modelo.index(i, 0).data(Qt.DisplayRole), modelo.index(i, 0).data(Qt.UserRole))
            for i in range(modelo.rowCount())
        ]

    def keyPressEvent(self, evento):
        """Seta para baixo com o campo vazio abre o catálogo inteiro."""
        if evento.key() == Qt.Key_Down and not self.lista_aberta():
            self.abrir_lista()
            return
        super().keyPressEvent(evento)

    def _escolher(self, indice: QModelIndex) -> None:
        produto_id = indice.data(Qt.UserRole)
        if produto_id is None:
            return
        # o QLineEdit escreve o texto escolhido DEPOIS deste sinal; limpar agora
        # seria desfeito na linha seguinte
        QTimer.singleShot(0, self.clear)
        self.escolhido.emit(int(produto_id))

    # ---------------------------------------------------------------- teclado

    def unico_encontrado(self, texto: str):
        """O produto que o texto identifica sem ambiguidade — ou None.

        Um resultado só, ou um cujo código/nome seja exatamente o que foi
        digitado. Com mais de um candidato quem escolhe é ela, na lista.
        """
        achados = [
            p for p in repo.buscar(self.session, texto, tipo=self._tipo)
            if p.id not in self._ignorar
        ]
        if len(achados) == 1:
            return achados[0]
        alvo = normalizar_sku(texto)
        return next(
            (p for p in achados
             if p.sku_norm == alvo or (p.nome or "").strip().lower() == alvo),
            None,
        )
