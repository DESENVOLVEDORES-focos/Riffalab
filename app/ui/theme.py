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

DESTAQUES = {
    "violeta": ("#C018E4", "#6C48F0"),
    "magenta": ("#FF2BD0", "#C018E4"),
    "ciano":   ("#22E8FF", "#6C48F0"),
    "lima":    ("#B6FF3D", "#22E8FF"),
}

FONTE = "Segoe UI"


def qss(acento: str = "violeta") -> str:
    p = PALETA
    c1, c2 = DESTAQUES.get(acento, DESTAQUES["violeta"])
    return f"""
* {{ outline: 0; }}

QWidget {{
    background: transparent;
    color: {p['texto']};
    font-family: "{FONTE}", "Inter", "Arial";
    font-size: 13px;
}}

QMainWindow, #fundoApp {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {p['bg0']}, stop:0.55 {p['bg1']}, stop:1 #1E0A2B);
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
        stop:0 #1C0629, stop:1 #150420);
    border-right: 1px solid {p['border']};
}}
QLabel#logo {{
    color: #fff;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#logoSub {{
    color: {p['texto_fraco']};
    font-size: 10px;
    letter-spacing: 2px;
}}
QPushButton#nav {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {p['texto_dim']};
    text-align: left;
    padding: 11px 16px;
    font-size: 13.5px;
    font-weight: 600;
    border-radius: 0px;
}}
QPushButton#nav:hover {{
    background: rgba(192,24,228,0.10);
    color: {p['texto']};
}}
QPushButton#nav:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(192,24,228,0.30), stop:1 rgba(192,24,228,0.02));
    border-left: 3px solid {c1};
    color: #fff;
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
    background: {p['surface2']};
    border: 1px solid {p['border']};
    border-radius: 10px;
    padding: 9px 16px;
    color: {p['texto']};
    font-weight: 600;
}}
QPushButton:hover {{ background: {p['surface3']}; border: 1px solid {c1}; }}
QPushButton:pressed {{ background: {p['surface']}; }}
QPushButton:disabled {{ color: {p['texto_fraco']}; border-color: #33203F; }}

QPushButton#primario {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c1}, stop:1 {c2});
    border: none;
    color: #fff;
    font-weight: 800;
    padding: 10px 22px;
    border-radius: 11px;
}}
QPushButton#primario:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p['magenta']}, stop:1 {c1});
}}
QPushButton#primario:disabled {{ background: #3A2050; color: {p['texto_fraco']}; }}

QPushButton#fantasma {{
    background: transparent;
    border: 1px solid {p['border']};
    color: {p['texto_dim']};
    padding: 7px 13px;
    font-weight: 600;
}}
QPushButton#fantasma:hover {{ color: #fff; border-color: {c1}; }}

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
    background: #1E0729;
}}
QLineEdit#busca {{
    font-size: 15px;
    padding: 13px 18px;
    border-radius: 14px;
    background: #1B0526;
}}
QLineEdit#busca:focus {{ border: 1px solid {c1}; }}
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
    alternate-background-color: #281036;
}}
QHeaderView::section {{
    background: #2B0E3D;
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


def aplicar_tema(app, acento: str = "violeta") -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(qss(acento))
    # paleta escura (afeta diálogos nativos e menus)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(PALETA["bg1"]))
    pal.setColor(QPalette.WindowText, QColor(PALETA["texto"]))
    pal.setColor(QPalette.Base, QColor(PALETA["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(PALETA["surface2"]))
    pal.setColor(QPalette.Text, QColor(PALETA["texto"]))
    pal.setColor(QPalette.Button, QColor(PALETA["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(PALETA["texto"]))
    pal.setColor(QPalette.Highlight, QColor(PALETA["violeta"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(PALETA["surface3"]))
    pal.setColor(QPalette.ToolTipText, QColor(PALETA["texto"]))
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
