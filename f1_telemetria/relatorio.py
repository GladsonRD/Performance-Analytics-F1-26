"""
Gera o relatório HTML de uma gravação.

    python relatorio.py gravacao.f1rec.gz                 # salva na pasta configurada no painel
    python relatorio.py gravacao.f1rec.gz --saida PASTA   # escolhe a pasta

Os relatórios ficam organizados por fim de semana:
    PASTA/Brasil 11-11-2026 19h07/Q1 11-11-2026 19h07.html
    PASTA/Brasil 11-11-2026 19h07/Corrida 11-11-2026 19h40.html
"""

import argparse
import json
import os
import re
import sys

import analise

PASTA = os.path.dirname(os.path.abspath(__file__))
MODELO = os.path.join(PASTA, "modelo_relatorio.html")
CONFIG = os.path.join(PASTA, "config.json")


def ler_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def salvar_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def pasta_padrao():
    return ler_config().get("pasta_saida") or os.path.join(PASTA, "relatorios")


def _limpo(txt):
    return re.sub(r'[<>:"/\\|?*]+', "-", txt).strip(" .")


def pasta_do_evento(meta, pasta_base):
    """Pasta do fim de semana: "GP dd-mm-aaaa HHhMM" (horário da primeira sessão).
    Sessões do mesmo GP no mesmo dia, com até 4 h de diferença, ficam na mesma pasta."""
    import glob
    from datetime import datetime
    prefixo = _limpo(f"{meta['gp']} {meta['dia']}")
    inicio = datetime.fromtimestamp(meta["inicio_ts"])
    melhor = None
    for p in glob.glob(os.path.join(glob.escape(pasta_base), prefixo + " *h*")):
        m = re.search(r"(\d{2})h(\d{2})$", os.path.basename(p))
        if not m or not os.path.isdir(p):
            continue
        hora = inicio.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        if 0 <= (inicio - hora).total_seconds() <= 4 * 3600 and (melhor is None or hora > melhor[0]):
            melhor = (hora, p)
    if melhor:
        return melhor[1]
    return os.path.join(pasta_base, f"{prefixo} {meta['hora']}")


def _livre(caminho):
    """Não sobrescreve: Corrida.html, Corrida (2).html, ..."""
    if not os.path.exists(caminho):
        return caminho
    base, ext = os.path.splitext(caminho)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def gerar(caminho, pasta_base=None, sobrescrever=False):
    """Gera o HTML e devolve o caminho do arquivo criado."""
    dados = analise.analisar(caminho)
    meta = dados["meta"]
    destino = pasta_do_evento(meta, pasta_base or pasta_padrao())
    os.makedirs(destino, exist_ok=True)
    with open(MODELO, encoding="utf-8") as f:
        modelo = f.read()
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    titulo = f"{meta['pista']} · {meta['sessao']}"
    html = modelo.replace("/*__DADOS__*/null", js).replace("__TITULO__", titulo)
    saida = os.path.join(destino, _limpo(f"{meta['sessao']} {meta['dia']} {meta['hora']}") + ".html")
    if not sobrescrever:
        saida = _livre(saida)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(html)
    return saida


def main():
    ap = argparse.ArgumentParser(description="Gera o relatório HTML de uma gravação do F1 26")
    ap.add_argument("gravacao", help="arquivo .f1rec.gz")
    ap.add_argument("--saida", help="pasta onde ficam as pastas de cada fim de semana")
    ap.add_argument("--sobrescrever", action="store_true", help="substitui o relatório se já existir")
    a = ap.parse_args()
    if not os.path.exists(a.gravacao):
        sys.exit(f"Arquivo não encontrado: {a.gravacao}")
    print("Relatório gerado:", gerar(a.gravacao, a.saida, a.sobrescrever))


if __name__ == "__main__":
    main()
