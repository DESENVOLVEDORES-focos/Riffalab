"""Tema visual "neon graffiti": paleta, folha de estilo (QSS) e utilitários."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QLinearGradient, QPalette, QPixmap, QPainter
from PySide6.QtCore import Qt

# --------------------------------------------------------------------- paleta
# Extraída da arte de referência (spray neon sobre parede roxa escura)
PALETA = {
    "bg0":        "#12001A",   # fundo mais escuro
    "bg1":        "#1A0526",
    "surface":    "#240A33",
    "surface2":   "#2E0F40",
    "surface3":   "#3A1550",
    "border":     "#4B1A66",
    "border_hi":  "#7A2BA8",

    "violeta":    "#C018E4",   # cor primária (do "VINYL!")
    "magenta":    "#FF2BD0",
    "rosa":       "#C00C6C",
    "azul":       "#6C48F0",
    "ciano":      "#22E8FF",
    "lima":       "#B6FF3D",
    "amarelo":    "#FFE13D",
    "laranja":    "#FF6B3D",
    "vermelho":   "#FF4D6D",

    "texto":      "#F4ECFF",
    "texto_dim":  "#A98BC8",
    "texto_fraco": "#7B5C97",
}

PALETA_ORIGINAL = dict(PALETA)

DESTAQUES = {
    "violeta": ("#C018E4", "#6C48F0"),
    "magenta": ("#FF2BD0", "#C018E4"),
    "ciano":   ("#22E8FF", "#6C48F0"),
    "lima":    ("#B6FF3D", "#22E8FF"),
}

FONTE = "Segoe UI"


# Chaves em config.json. Valores não reconhecidos nunca entram no QSS.
CHAVES_CORES = ('cor_fundo', 'cor_lateral', 'cor_cartoes', 'cor_botoes', 'cor_texto')


def validar_cor(valor: object) -> str:
    import re
    if not isinstance(valor, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', valor):
        return ''
    return valor.upper()


def cores_do_config(config) -> dict:
    return {chave: validar_cor(config.get(chave)) for chave in CHAVES_CORES}


def contraste(cor: str) -> str:
    """Escolhe texto preto ou branco para manter legíveis os botões."""
    c = QColor(cor)
    def canal(v):
        v = v / 255
        return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    luz = .2126 * canal(c.red()) + .7152 * canal(c.green()) + .0722 * canal(c.blue())
    return '#000000' if luz > .179 else '#FFFFFF'


def _misturar(cor: str, outra: str, peso: float) -> str:
    a, b = QColor(cor), QColor(outra)
    valores = [round(x * (1 - peso) + y * peso) for x, y in
               zip((a.red(), a.green(), a.blue()), (b.red(), b.green(), b.blue()))]
    return QColor(*valores).name().upper()


def paleta_personalizada(cores=None) -> dict:
    cores = cores if isinstance(cores, dict) else {}
    c = {k: validar_cor(cores.get(k)) for k in CHAVES_CORES}
    p = dict(PALETA_ORIGINAL)
    if c['cor_fundo']:
        p['bg0'] = c['cor_fundo']
        p['bg1'] = _misturar(c['cor_fundo'], '#FFFFFF', .035)
    if c['cor_cartoes']:
        p['surface'] = c['cor_cartoes']
        oposto = contraste(c['cor_cartoes'])
        p['surface2'] = _misturar(c['cor_cartoes'], oposto, .07)
        p['surface3'] = _misturar(c['cor_cartoes'], oposto, .14)
        p['border'] = _misturar(c['cor_cartoes'], oposto, .26)
        p['border_hi'] = _misturar(c['cor_cartoes'], oposto, .42)
    if c['cor_texto']:
        p['texto'] = c['cor_texto']
        p['texto_dim'] = _misturar(c['cor_texto'], p['surface'], .20)
        p['texto_fraco'] = _misturar(c['cor_texto'], p['surface'], .32)
    return p


def qss(acento: str = "violeta", cores=None) -> str:
    cores = cores if isinstance(cores, dict) else {}
    p = paleta_personalizada(cores)
    fundo = validar_cor(cores.get('cor_fundo'))
    lateral = validar_cor(cores.get('cor_lateral'))
    cartoes = validar_cor(cores.get('cor_cartoes'))
    botoes = validar_cor(cores.get('cor_botoes'))
    c1, c2 = DESTAQUES.get(acento, DESTAQUES["violeta"])
    if botoes:
        c1, c2 = botoes, _misturar(botoes, '#FFFFFF', .12)
    texto_botao = contraste(c1) if botoes else '#FFFFFF'
    texto_hover = contraste(c2) if botoes else '#FFFFFF'
    fundo_fim = p['bg1'] if fundo else '#1E0A2B'
    lateral_inicio = lateral or ('#1C0629' if not fundo else p['bg1'])
    lateral_fim = _misturar(lateral, '#000000', .12) if lateral else ('#150420' if not fundo else p['bg0'])
    texto_lateral = contraste(lateral) if lateral else p['texto_dim']
    logo_lateral = contraste(lateral) if lateral else '#FFFFFF'
    selecao_lateral = alfa(c1, '35') if botoes else 'rgba(192,24,228,0.30)'
    hover_lateral = alfa(c1, '20') if botoes else 'rgba(192,24,228,0.10)'
    fundo_botao = c1 if botoes else p['surface2']
    fundo_botao_hover = c2 if botoes else p['surface3']
    texto_botao_normal = texto_botao if botoes else p['texto']
    fundo_fantasma = c1 if botoes else 'transparent'
    texto_fantasma = texto_botao if botoes else p['texto_dim']
    fundo_campo_foco = p['bg1'] if fundo else '#1E0729'
    fundo_busca = p['bg1'] if fundo else '#1B0526'
    fundo_cabecalho = p['surface2'] if cartoes else '#2B0E3D'
    fundo_alternado = p['surface2'] if cartoes else '#281036'
    fundo_primario_hover = c2 if botoes else p['magenta']
    return f"""
* {{ outline: 0; }}

QWidget {{
    background: transparent;
    color: {p['texto']};
    font-family: "{FONTE}", "Inter", "Arial";
    font-size: 13px;
}}

QDialog {{ background: {p['bg1']}; }}

QMainWindow, #fundoApp {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['bg0']}, stop:0.55 {p['bg1']}, stop:1 {fundo_fim});
}}

/* ---------------------------------------------------------------- cartões */
QFrame#cartao, QWidget#cartao {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 14px;
}}
QFrame#cartaoDestaque {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(192,24,228,0.16), stop:1 rgba(108,72,240,0.10));
    border: 1px solid {p['border_hi']};
    border-radius: 14px;
}}
QFrame#cartaoResultado {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 14px;
}}
QFrame#cartaoResultado:hover {{
    border: 1px solid {c1};
    background: {p['surface2']};
}}

/* --------------------------------------------------------------- barra lat */
QFrame#barraLateral {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {lateral_inicio}, stop:1 {lateral_fim});
    border-right: 1px solid {p['border']};
}}
QLabel#logo {{
    color: {logo_lateral};
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#logoSub {{
    color: {texto_lateral};
    font-size: 10px;
    letter-spacing: 2px;
}}
QPushButton#nav {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {texto_lateral};
    text-align: left;
    padding: 11px 16px;
    font-size: 13.5px;
    font-weight: 600;
    border-radius: 0px;
}}
QPushButton#nav:hover {{
    background: {hover_lateral};
    color: {texto_lateral};
}}
QPushButton#nav:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {selecao_lateral}, stop:1 transparent);
    border-left: 3px solid {c1};
    color: {logo_lateral};
}}

/* ---------------------------------------------------------------- títulos */
QLabel#titulo {{ font-size: 22px; font-weight: 800; letter-spacing: .4px; }}
QLabel#subtitulo {{ color: {p['texto_dim']}; font-size: 12.5px; }}
QLabel#rotulo {{ color: {p['texto_fraco']}; font-size: 11px; letter-spacing: 1px; font-weight: 600; }}
QLabel#destaque {{
    color: #fff; font-weight: 700;
    background: rgba(192,24,228,0.18);
    border: 1px solid {p['border_hi']};
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
}}

/* ------------------------------------------------------------------ botões */
QPushButton {{
    background: {fundo_botao};
    border: 1px solid {p['border']};
    border-radius: 10px;
    padding: 9px 16px;
    color: {texto_botao_normal};
    font-weight: 600;
}}
QPushButton:hover {{ background: {fundo_botao_hover}; color: {texto_hover}; border: 1px solid {c1}; }}
QPushButton:pressed {{ background: {fundo_botao_hover}; color: {texto_hover}; }}
QPushButton:disabled {{ color: {p['texto_fraco']}; border-color: #33203F; }}

QPushButton#primario {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c1}, stop:1 {c2});
    border: none;
    color: {texto_botao};
    font-weight: 800;
    padding: 10px 22px;
    border-radius: 11px;
}}
QPushButton#primario:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {fundo_primario_hover}, stop:1 {c1});
    color: {texto_hover};
}}
QPushButton#primario:disabled {{ background: #3A2050; color: {p['texto_fraco']}; }}

QPushButton#fantasma {{
    background: {fundo_fantasma};
    border: 1px solid {p['border']};
    color: {texto_fantasma};
    padding: 7px 13px;
    font-weight: 600;
}}
QPushButton#fantasma:hover {{ background: {fundo_botao_hover}; color: {texto_hover}; border-color: {c1}; }}

QPushButton#perigo {{
    background: rgba(255,77,109,0.14);
    border: 1px solid rgba(255,77,109,0.5);
    color: #FF9BB0;
}}
QPushButton#perigo:hover {{ background: rgba(255,77,109,0.26); }}

/* ------------------------------------------------------------------ campos */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
    background: {p['bg1']};
    border: 1px solid {p['border']};
    border-radius: 11px;
    padding: 10px 13px;
    selection-background-color: {c1};
    selection-color: #fff;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {c1};
    background: {fundo_campo_foco};
}}
QLineEdit#busca {{
    font-size: 15px;
    padding: 13px 18px;
    border-radius: 14px;
    background: {fundo_busca};
}}
QLineEdit#busca:focus {{ border: 1px solid {c1}; }}
QComboBox#seletorFormatos {{ padding: 5px 9px; border-radius: 8px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p['surface']};
    border: 1px solid {p['border_hi']};
    selection-background-color: {c1};
    outline: none;
    padding: 4px;
}}

QCheckBox {{ spacing: 8px; color: {p['texto_dim']}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid {p['border_hi']}; background: {p['bg1']};
}}
QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c1}, stop:1 {c2});
    border: 1px solid {c1};
}}
QRadioButton {{ spacing: 8px; color: {p['texto_dim']}; }}
QRadioButton::indicator {{ width: 15px; height: 15px; border-radius: 8px;
    border: 1px solid {p['border_hi']}; background: {p['bg1']}; }}
QRadioButton::indicator:checked {{ border: 4px solid {c1}; }}

/* ------------------------------------------------------------- progresso */
QProgressBar {{
    background: {p['bg0']};
    border: 1px solid {p['border']};
    border-radius: 7px;
    height: 12px;
    text-align: center;
    font-size: 10px;
    color: {p['texto']};
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c1}, stop:1 {p['ciano']});
}}

/* ---------------------------------------------------------------- tabelas */
QTableWidget, QTableView {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 12px;
    gridline-color: #33194A;
    selection-background-color: rgba(192,24,228,0.28);
    selection-color: #fff;
    alternate-background-color: {fundo_alternado};
}}
QHeaderView::section {{
    background: {fundo_cabecalho};
    color: {p['texto_dim']};
    border: none;
    border-bottom: 1px solid {p['border']};
    padding: 9px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: .6px;
}}
QTableWidget::item {{ padding: 6px; }}

/* ---------------------------------------------------------------- rolagem */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p['border_hi']}; border-radius: 5px; min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: {c1}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{ background: {p['border_hi']}; border-radius: 5px; }}

/* ---------------------------------------------------------------- diversos */
QToolTip {{
    background: {p['surface3']};
    color: {p['texto']};
    border: 1px solid {c1};
    padding: 6px;
    border-radius: 8px;
}}
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 7px; }}
QMenu::item:selected {{ background: rgba(192,24,228,0.3); }}
QStatusBar {{ background: {p['bg1']}; color: {p['texto_fraco']}; border-top: 1px solid {p['border']}; }}
QSplitter::handle {{ background: {p['border']}; }}
#separador {{ background: {p['border']}; max-height: 1px; min-height: 1px; }}
QLabel#ok {{ color: {p['lima']}; font-weight: 700; }}
QLabel#alerta {{ color: {p['amarelo']}; font-weight: 700; }}
QLabel#erro {{ color: {p['vermelho']}; font-weight: 700; }}
QLabel#dim {{ color: {p['texto_dim']}; }}
QLabel#fraco {{ color: {p['texto_fraco']}; font-size: 11.5px; }}
QLabel[papel_tema="dim"] {{ color: {p['texto_dim']}; }}
QLabel[papel_tema="fraco"] {{ color: {p['texto_fraco']}; }}
"""


def alfa(cor: str, valor: str = "1A") -> str:
    """Cor com transparência no formato que o Qt entende: #AARRGGBB.

    `alfa("#B6FF3D", "1A")` → `"#1AB6FF3D"` (verde-lima a 10%).
    Escrever `#B6FF3D1A` é aceito pelo Qt como AARRGGBB e sai LARANJA — foi
    exatamente o bug dos selos coloridos.
    """
    limpa = (cor or "#FFFFFF").lstrip("#")
    if len(limpa) == 3:
        limpa = "".join(c * 2 for c in limpa)
    return f"#{valor}{limpa}"


def aplicar_tema(app, acento: str = "violeta", cores=None) -> None:
    p = paleta_personalizada(cores)
    app.setStyle("Fusion")
    app.setStyleSheet(qss(acento, cores))
    botoes = validar_cor((cores or {}).get('cor_botoes')) if isinstance(cores, dict) else ''
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p["bg1"]))
    pal.setColor(QPalette.WindowText, QColor(p["texto"]))
    pal.setColor(QPalette.Base, QColor(p["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(p["surface2"]))
    pal.setColor(QPalette.Text, QColor(p["texto"]))
    pal.setColor(QPalette.Button, QColor(botoes or p["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(contraste(botoes) if botoes else p["texto"]))
    pal.setColor(QPalette.Highlight, QColor(botoes or p["violeta"]))
    pal.setColor(QPalette.HighlightedText, QColor(contraste(botoes) if botoes else "#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(p["surface3"]))
    pal.setColor(QPalette.ToolTipText, QColor(p["texto"]))
    app.setPalette(pal)


def fonte(tamanho: int = 13, peso: QFont.Weight = QFont.Normal) -> QFont:
    f = QFont(FONTE, tamanho)
    f.setWeight(peso)
    return f


def pixmap_placeholder(lado: int = 64) -> QPixmap:
    """Capa "vazia" com degradê neon (usada enquanto a imagem carrega)."""
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    pintor = QPainter(pm)
    pintor.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, lado, lado)
    grad.setColorAt(0, QColor(PALETA["surface3"]))
    grad.setColorAt(1, QColor(PALETA["bg1"]))
    pintor.fillRect(0, 0, lado, lado, grad)
    pintor.setPen(QColor(PALETA["border_hi"]))
    pintor.drawText(pm.rect(), Qt.AlignCenter, "♪")
    pintor.end()
    return pm
