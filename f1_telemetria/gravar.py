"""
Grava a telemetria UDP do F1 26 e gera o relatório HTML quando a sessão termina.

Normalmente é usado pelo painel (atalho "Telemetria F1 26"). Também roda no terminal:
    python gravar.py                    # porta 20777, pasta configurada no painel
    python gravar.py --saida D:\\F1      # outra pasta
    python gravar.py --porta 20778 --nao-abrir

Cada fim de semana vira uma pasta "GP dd-mm-aaaa" com um HTML por sessão
(Q1, Q2, Q3, Corrida...) e a subpasta "dados" com as gravações brutas.
"""

import argparse
import gzip
import os
import pathlib
import shutil
import socket
import struct
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime

import leitor
import pacotes
import relatorio
from constantes import PISTAS, SESSOES

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_TEMP = os.path.join(PASTA, "gravando")

MAGIC = b"F1REC1\n"
CABECALHO = struct.Struct("<HBBBBBQfIIBB")  # 29 bytes
TAMANHOS = {k[2]: v.size() for k, v in pacotes.HEADER_FIELD_TO_PACKET_TYPE.items()}
ESPERA_FIM = 5.0       # segundos depois do fim, para pegar os últimos históricos de volta
MIN_PACOTES = 2000     # sessões menores que isso são ignoradas (menus, saídas rápidas)


class Sessao:
    def __init__(self, uid):
        self.uid = uid
        os.makedirs(PASTA_TEMP, exist_ok=True)
        self.nome = f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{uid & 0xFFFFFFFF:08x}"
        self.caminho = os.path.join(PASTA_TEMP, self.nome + ".f1rec.gz")
        self.arq = gzip.open(self.caminho, "wb", compresslevel=1)
        self.arq.write(MAGIC)
        self.pacotes = 0
        self.tipo = None
        self.fim_em = None
        self.relatorio = None
        self.tentou = False
        self.pacotes_no_relatorio = 0
        self.hash_final = None
        self.ultimo_t = {}

    def gravar(self, dados, pid, t):
        # status e danos dos 22 carros não precisam de 60 Hz: no máximo 5 por segundo
        if pid in (7, 10):
            ult = self.ultimo_t.get(pid)
            if ult is not None and 0 <= t - ult < 0.2:
                return
            self.ultimo_t[pid] = t
        self.arq.write(struct.pack("<H", len(dados)))
        self.arq.write(dados)
        self.pacotes += 1

    def fechar(self):
        if not self.arq.closed:
            self.arq.close()


class Gravador:
    """Escuta o UDP numa thread. Avisa o que acontece por callbacks."""

    def __init__(self, porta=20777, pasta_saida=None, abrir=True, ao_log=print, ao_relatorio=None, ao_estado=None,
                 ao_info=None):
        self.porta = porta
        self.pasta_saida = pasta_saida or relatorio.pasta_padrao()
        self.abrir = abrir
        self.ao_log = ao_log
        self.ao_relatorio = ao_relatorio or (lambda caminho: None)
        self.ao_estado = ao_estado or (lambda texto: None)
        self.ao_info = ao_info or (lambda info: None)   # pista, sessão, volta e pacotes/s ao vivo
        self._parar = threading.Event()
        self.sessao = None

    def log(self, msg):
        self.ao_log(f"[{datetime.now():%H:%M:%S}] {msg}")

    # ---------------------------------------------------------------- relatório
    def gerar_relatorio(self, s):
        atualizar = s.relatorio is not None
        s.tentou = True
        s.arq.flush()
        if s.pacotes < MIN_PACOTES:
            self.log("Sessão curta demais, sem relatório.")
            return
        self.ao_estado("Gerando relatório...")
        try:
            s.relatorio = relatorio.gerar(s.caminho, self.pasta_saida, sobrescrever=atualizar)
            s.pacotes_no_relatorio = s.pacotes
        except Exception as e:
            traceback.print_exc()
            self.log(f"Erro ao gerar o relatório: {e}. A gravação ficou salva e dá para tentar de novo.")
            return
        if atualizar:
            self.log("Relatório atualizado com as voltas que terminaram depois do fim da sessão.")
            self.ao_estado("Relatório pronto, aguardando a próxima sessão")
            return
        self.log(f"Relatório pronto: {s.relatorio}")
        self.ao_estado("Relatório pronto, aguardando a próxima sessão")
        self.ao_relatorio(s.relatorio)
        if self.abrir:
            webbrowser.open(pathlib.Path(s.relatorio).resolve().as_uri())

    def encerrar(self, s, motivo):
        self.log(f"Sessão encerrada ({motivo}).")
        if not s.tentou:
            self.gerar_relatorio(s)
        elif s.relatorio and s.pacotes - s.pacotes_no_relatorio > 300:
            # chegou coisa depois do relatório (ex.: pilotos fechando a última volta): refaz
            self.gerar_relatorio(s)
        s.fechar()
        # guarda a gravação bruta junto dos relatórios do fim de semana
        if s.relatorio:
            try:
                pasta = os.path.join(os.path.dirname(s.relatorio), "dados")
                os.makedirs(pasta, exist_ok=True)
                shutil.move(s.caminho, os.path.join(pasta, os.path.basename(s.caminho)))
            except OSError:
                pass
        elif s.pacotes < MIN_PACOTES:
            try:
                os.remove(s.caminho)
            except OSError:
                pass

    # ---------------------------------------------------------------- laço
    def parar(self):
        self._parar.set()

    def rodar(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        except OSError:
            pass
        try:
            sock.bind(("0.0.0.0", self.porta))
        except OSError:
            self.log(f"A porta {self.porta} já está em uso (outro app de telemetria aberto?). "
                     "Feche o outro app ou escolha outra porta.")
            self.ao_estado("Erro: porta em uso")
            return False
        sock.settimeout(0.5)
        self.log(f"Escutando na porta {self.porta}. Relatórios em: {self.pasta_saida}")
        self.ao_estado("Aguardando o jogo...")

        avisos = set()
        ultimo_pacote = None
        ultimo_estado = 0
        info = {}
        pacotes_seg = 0
        try:
            while not self._parar.is_set():
                try:
                    dados = sock.recv(4096)
                except socket.timeout:
                    dados = None
                except ConnectionResetError:
                    continue

                agora = time.time()
                s = self.sessao
                if s and s.fim_em and not s.tentou and agora - s.fim_em > ESPERA_FIM:
                    self.log("Fim da sessão, gerando relatório...")
                    self.gerar_relatorio(s)

                if dados is None:
                    if ultimo_pacote and agora - ultimo_pacote > 10 and "parado" not in avisos:
                        self.ao_estado("Sem dados do jogo (pausado ou no menu?)")
                        avisos.add("parado")
                    continue
                if len(dados) < CABECALHO.size:
                    continue
                ultimo_pacote = agora
                avisos.discard("parado")

                fmt, _a, _b, _c, _d, pid, uid, t, _f, _g, _p, _q = CABECALHO.unpack_from(dados)
                pacotes_seg += 1
                if fmt != 2026:
                    if "formato" not in avisos:
                        self.log(f"ATENÇÃO: o jogo está mandando no formato {fmt}. Mude 'UDP Format' para 2026.")
                        self.ao_estado("Formato errado no jogo (use 2026)")
                        avisos.add("formato")
                    continue
                esperado = TAMANHOS.get(pid)
                if esperado and len(dados) != esperado and ("tam", pid) not in avisos:
                    self.log(f"Aviso: pacote {pid} veio com {len(dados)} bytes (esperado {esperado}).")
                    avisos.add(("tam", pid))
                if uid == 0:
                    continue

                if s is None or uid != s.uid:
                    if s is not None:
                        self.encerrar(s, "nova sessão começou")
                    s = self.sessao = Sessao(uid)
                    info = {}
                    self.log("Nova sessão detectada, gravando...")

                s.gravar(dados, pid, t)

                if pid == 1 and s.tipo is None:
                    s.tipo = dados[CABECALHO.size + 6]
                    self.log(f"Sessão: {SESSOES.get(s.tipo, s.tipo)}")
                if pid == 1:
                    pista = struct.unpack_from("<b", dados, CABECALHO.size + 7)[0]
                    info["pista"] = PISTAS.get(pista, f"Pista {pista}")
                    info["sessao"] = SESSOES.get(s.tipo, "")
                elif pid == 2:
                    try:
                        r = leitor.LAP.ler(dados, _p)
                        info["volta"] = r[leitor.LAP.idx["current_lap_num"]]
                        ult = r[leitor.LAP.idx["last_lap_time_in_ms"]]
                        if ult and (not info.get("melhor") or ult < info["melhor"]) and info.get("_ult") != ult:
                            info["melhor"] = ult
                        info["_ult"] = ult
                    except Exception:  # noqa: BLE001
                        pass
                elif pid == 3 and dados[CABECALHO.size:CABECALHO.size + 4] == b"SEND":
                    if s.fim_em is None:
                        self.log("O jogo sinalizou o fim da sessão.")
                        s.fim_em = agora
                elif pid == 8:
                    # a classificação final pode chegar de novo, atualizada, quando outros pilotos
                    # terminam a última volta depois do fim: nesse caso o relatório é refeito
                    h = hash(dados[CABECALHO.size:])
                    if h != s.hash_final:
                        s.hash_final = h
                        s.fim_em = agora
                        if s.tentou:
                            s.tentou = False
                if s.pacotes % 2000 == 0:
                    s.arq.flush()
                if agora - ultimo_estado > 1:
                    info["pacotes"] = round(pacotes_seg / max(0.5, agora - ultimo_estado)) if ultimo_estado else 0
                    pacotes_seg = 0
                    self.ao_info({k: v for k, v in info.items() if not k.startswith("_")})
                    ultimo_estado = agora
                    nome = SESSOES.get(s.tipo, "sessão") if s.tipo is not None else "sessão"
                    self.ao_estado("Relatório pronto, aguardando a próxima sessão" if s.relatorio
                                   else f"Gravando {nome}...")
        finally:
            sock.close()
            if self.sessao:
                self.encerrar(self.sessao, "gravação parada")
                self.sessao = None
            self.ao_estado("Parado")
        return True


def main():
    ap = argparse.ArgumentParser(description="Gravador de telemetria do F1 26")
    ap.add_argument("--porta", type=int, default=None)
    ap.add_argument("--saida", help="pasta dos relatórios (padrão: a escolhida no painel)")
    ap.add_argument("--nao-abrir", action="store_true", help="não abrir o relatório no navegador")
    a = ap.parse_args()
    cfg = relatorio.ler_config()
    g = Gravador(porta=a.porta or cfg.get("porta", 20777), pasta_saida=a.saida, abrir=not a.nao_abrir)
    t = threading.Thread(target=g.rodar)
    t.start()
    try:
        while t.is_alive():
            t.join(0.5)
    except KeyboardInterrupt:
        print()
        g.parar()
        t.join()
        print("Até a próxima!")
    sys.exit(0)


if __name__ == "__main__":
    main()
