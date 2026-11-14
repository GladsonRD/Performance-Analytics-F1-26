"""
Atualização do programa pelo GitHub (sem precisar de Git).

Baixa o .zip do ramo principal do repositório, compara a versão (arquivo VERSAO) e copia os
arquivos novos por cima dos atuais. Nunca mexe no que é de cada pessoa: config.json, gravações em
andamento, bordas das pistas e o registro de erros.
"""

import io
import json
import os
import shutil
import urllib.request
import zipfile

PASTA = os.path.dirname(os.path.abspath(__file__))
REPO = "GladsonRD/Performance-Analytics-F1-26"
RAMO = "main"
URL_VERSAO = f"https://raw.githubusercontent.com/{REPO}/{RAMO}/f1_telemetria/VERSAO"
URL_ZIP = f"https://github.com/{REPO}/archive/refs/heads/{RAMO}.zip"

# o que é de cada usuário e nunca é sobrescrito
PRESERVAR = {"config.json", "erro.txt", "gravando", "pistas", "__pycache__"}


def versao_local():
    try:
        with open(os.path.join(PASTA, "VERSAO"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0"


def _baixar(url, limite=30):
    req = urllib.request.Request(url, headers={"User-Agent": "telemetria-f1-26", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=limite) as r:
        return r.read()


def _num(v):
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


def versao_remota():
    return _baixar(URL_VERSAO, 10).decode("utf-8").strip()


def tem_atualizacao():
    """(há versão nova?, versão local, versão remota). Levanta erro se não conseguir consultar."""
    loc, rem = versao_local(), versao_remota()
    return _num(rem) > _num(loc), loc, rem


def atualizar():
    """Baixa e instala a versão do GitHub. Devolve a versão instalada."""
    dados = _baixar(URL_ZIP, 120)
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        nomes = z.namelist()
        raiz = nomes[0].split("/")[0] + "/"
        # o programa fica na pasta f1_telemetria do repositório
        base = raiz + "f1_telemetria/" if any(n.startswith(raiz + "f1_telemetria/") for n in nomes) else raiz
        copiados = 0
        for n in nomes:
            if not n.startswith(base) or n.endswith("/"):
                continue
            rel = n[len(base):]
            topo = rel.split("/")[0]
            if topo in PRESERVAR:
                continue
            destino = os.path.join(PASTA, *rel.split("/"))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            tmp = destino + ".novo"
            with z.open(n) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.replace(tmp, destino)
            copiados += 1
    shutil.rmtree(os.path.join(PASTA, "__pycache__"), ignore_errors=True)
    return versao_local(), copiados


if __name__ == "__main__":
    novo, loc, rem = tem_atualizacao()
    print(json.dumps({"local": loc, "remota": rem, "nova": novo}))
    if novo:
        print(atualizar())
