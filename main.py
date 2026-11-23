"""RiffLab — pesquisa, comparação de qualidade e organização de músicas.

Uso:
    python main.py            (normal)
    python main.py --debug    (log detalhado no console)

Estrutura de pastas (criada automaticamente no primeiro start):
    RiffLab/
        main.py
        cookies.txt          (opcional — não é criado por você? veja LEIA-ME)
        downloads/           (saída padrão dos MP3)
        capas/               (cache de capas)
        temp/                (arquivos intermediários, limpos automaticamente)
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Console do Windows (cp850/cp1252) não aceita acentos: força UTF-8 para que
# qualquer print/log não derrube o app. Em console antigo, substitui o caractere.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Permite rodar de qualquer pasta (duplo clique, atalho, etc.)
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

DEPENDENCIAS = [
    ("PySide6", "PySide6"),
    ("mutagen", "mutagen"),
]


def _verificar_dependencias() -> None:
    faltando = []
    for modulo, pacote in DEPENDENCIAS:
        try:
            __import__(modulo)
        except ImportError:
            faltando.append(pacote)
    if faltando:
        print("=" * 62)
        print(" Dependências ausentes:", ", ".join(faltando))
        print(" Instale com:")
        print(f"   {Path(sys.executable).name} -m pip install " + " ".join(faltando))
        print("=" * 62)
        sys.exit(1)


def main() -> int:
    _verificar_dependencias()

    from app.config import APP_NOME, APP_VERSAO, preparar_ambiente
    from app.db import Banco
    from app.logging_setup import configurar

    debug = "--debug" in sys.argv
    log = configurar(10 if debug else 20)
    log.info("Iniciando %s %s", APP_NOME, APP_VERSAO)

    config = preparar_ambiente()

    # §1 da proposta: o cookies.txt é sensível — só o ESTADO é verificado,
    # o conteúdo nunca é lido, exibido ou gravado em log.
    try:
        from app import cookies as cookies_mod
        estado = cookies_mod.verificar(config.caminho_cookies)
        if estado.estado == "ausente":
            print("Autenticação: nenhuma configuração de autenticação local "
                  "encontrada — o app funciona normalmente para fontes públicas.")
        else:
            print(f"Autenticação: cookies.txt encontrado ({estado.tamanho} bytes, "
                  f"{estado.cookies_validos} cookie(s)) — conteúdo não é lido.")
        log.info("Autenticação local: %s", estado.estado)
    except Exception:                                             # noqa: BLE001
        pass

    # O QtWebEngine (player da pré-visualização) precisa ser importado ANTES do
    # QApplication. Se não estiver instalado, o app abre normalmente e a prévia
    # oferece "abrir página original".
    webengine_ok = False
    try:
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        webengine_ok = True
    except Exception:                                             # noqa: BLE001
        print("Pré-visualização embutida: indisponível (QtWebEngine não instalado) "
              "— a opção 'abrir página original' continua funcionando.")
    log.info("Pré-visualização embutida: %s", "disponível" if webengine_ok else "indisponível")

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NOME)
    app.setApplicationDisplayName(APP_NOME)
    app.setApplicationVersion(APP_VERSAO)
    app.setOrganizationName("RiffLab")

    icone = RAIZ / "assets" / "icone.png"
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))

    from app.ui.theme import aplicar_tema
    aplicar_tema(app, str(config.get("cor_destaque") or "violeta"))

    # exceções não tratadas aparecem para o usuário e vão para o log
    def tratar_excecao(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        log.error("Exceção não tratada:\n%s", texto)
        if app.instance():
            QMessageBox.critical(None, "Erro inesperado",
                                 f"Ocorreu um erro:\n\n{valor}\n\nDetalhes em rifflab.log")

    sys.excepthook = tratar_excecao

    banco = Banco()
    from app.ui.main_window import MainWindow
    from app import pipeline

    # limpeza de temporários antigos (mais de 1 dia)
    try:
        pipeline.limpar_temp(1.0)
    except Exception:
        pass

    janela = MainWindow(config, banco)
    janela.show()
    log.info("Interface pronta")
    codigo = app.exec()
    log.info("Encerrando (código %s)", codigo)
    return int(codigo)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Também cobre erros de inicialização antes de instalar sys.excepthook.
        from app.logging_setup import configurar
        configurar().error("Erro ao iniciar ou executar o aplicativo:\n%s", traceback.format_exc())
        sys.exit(1)
