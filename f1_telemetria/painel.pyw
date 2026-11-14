"""Janela do Performance Analytics F1 26 (aberta pelo atalho da Área de Trabalho)."""

import glob
import os
import pathlib
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import filedialog, messagebox, ttk

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
os.chdir(PASTA)

import relatorio  # noqa: E402
from gravar import Gravador  # noqa: E402

# tema escuro
FUNDO = "#1C1C1C"
CARTAO = "#1C1C1C"
LINHA = "#333333"
BORDA = "#454545"
TEXTO = "#EDEDED"
TEXTO2 = "#B5B5B5"
APAGADO = "#8C8C8C"
HOVER = "#2A2A2A"
VERMELHO = "#E5484D"
AZUL = "#5EA2EF"
LOG_FUNDO = "#121212"
LOG_TEXTO = "#CFCFCF"
FONTE = "Segoe UI"
# bloco de status: (fundo, texto, bolinha)
ESTADOS = {
    "gravando": ("#13301A", "#3DC45A", "#2EB84B"),
    "aguardando": ("#33290F", "#E3B341", "#E3B341"),
    "gerando": ("#33290F", "#E3B341", "#E3B341"),
    "pronto": ("#132640", "#6AAAF2", "#5EA2EF"),
    "erro": ("#3A1517", "#F0787C", "#E5484D"),
    "parado": ("#262626", "#C9C9C9", "#8C8C8C"),
}
# ícones da fonte de ícones do Windows (com reserva em texto comum)
ICONES = {"pasta": ("", "▤"), "mapa": ("", "◈"), "atualizar": ("", "⟳"),
          "config": ("", "⚙"), "abrir": ("", "↗"), "min": ("", "—"), "fechar": ("", "✕"),
          "corrida": ("", "⚑"), "quali": ("", "◷"), "parar": ("", "■"), "iniciar": ("", "▶"),
          "registro": ("", "›"), "registro_aberto": ("", "⌄")}
FONTE_ICONE = None


def icone(nome):
    return ICONES[nome][0] if FONTE_ICONE else ICONES[nome][1]


def fonte_icone(tam):
    return (FONTE_ICONE, tam) if FONTE_ICONE else (FONTE, tam)


def abrir_no_sistema(caminho):
    if sys.platform.startswith("win"):
        os.startfile(caminho)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


def versao():
    try:
        with open(os.path.join(PASTA, "VERSAO"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def fmt_volta(ms):
    return f"{ms // 60000}:{(ms % 60000) / 1000:06.3f}" if ms else "—"


DATA = re.compile(r"\s*(\d{2})-(\d{2})-\d{4}\s+(\d{1,2}h\d{2})\s*$")


def descrever_relatorio(caminho):
    """('Las Vegas · Corrida', '13/11 14h31', é corrida?) a partir do caminho do relatório."""
    pasta = os.path.basename(os.path.dirname(caminho))
    nome = os.path.splitext(os.path.basename(caminho))[0]
    m = DATA.search(nome)
    pista = DATA.sub("", pasta).strip() or pasta
    sessao = DATA.sub("", nome).strip() or nome
    quando = f"{m.group(1)}/{m.group(2)} {m.group(3)}" if m else ""
    return f"{pista} · {sessao}", quando, sessao.lower().startswith(("corrida", "sprint"))


def rotulo(pai, texto="", tam=10, peso="normal", cor=TEXTO, bg=CARTAO, **kw):
    kw.setdefault("anchor", "w")
    return tk.Label(pai, text=texto, font=(FONTE, tam, peso), fg=cor, bg=bg, **kw)


def botao(pai, texto, comando, negrito=False, **kw):
    """Botão simples (usado na janelinha de configurações)."""
    b = tk.Button(pai, text=texto, command=comando, font=(FONTE, 10, "bold" if negrito else "normal"), fg=TEXTO,
                  bg=CARTAO, activebackground=HOVER, activeforeground=TEXTO, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2", highlightthickness=1, highlightbackground=BORDA, highlightcolor=BORDA, **kw)
    b.bind("<Enter>", lambda _e: b.configure(bg=HOVER))
    b.bind("<Leave>", lambda _e: b.configure(bg=CARTAO))
    return b


def _ret_arredondado(cv, x0, y0, x1, y1, r, **kw):
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    p = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
         x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(p, smooth=True, splinesteps=12, **kw)


class Caixa(tk.Canvas):
    """Moldura com cantos arredondados; o conteúdo vai em self.dentro."""

    def __init__(self, pai, fundo=CARTAO, borda=BORDA, raio=12, pad=12, bg_pai=CARTAO):
        super().__init__(pai, bg=bg_pai, highlightthickness=0, bd=0, height=10)
        self.fundo, self.borda, self.raio, self.pad = fundo, borda, raio, pad
        self.dentro = tk.Frame(self, bg=fundo)
        self._jan = self.create_window(pad, pad, window=self.dentro, anchor="nw")
        self.bind("<Configure>", self._redesenhar)
        self.dentro.bind("<Configure>", self._ajustar_altura)
        self.after(20, lambda: self._ajustar_altura(repetir=True))

    def _ajustar_altura(self, _ev=None, repetir=False):
        h = self.dentro.winfo_reqheight() + 2 * self.pad
        if int(self.cget("height")) != h:
            self.configure(height=h)
        if repetir:   # o conteúdo muda de tamanho sem avisar quando ainda está fora da área visível
            self.after(250, lambda: self._ajustar_altura(repetir=True))

    def _redesenhar(self, _ev=None):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("fundo")
        _ret_arredondado(self, 1, 1, w - 2, h - 2, self.raio, fill=self.fundo, outline=self.borda or self.fundo,
                         width=1, tags="fundo")
        self.tag_lower("fundo")
        self.itemconfigure(self._jan, width=max(10, w - 2 * self.pad))

    def cor(self, fundo, borda=None):
        self.fundo, self.borda = fundo, borda
        self.dentro.configure(bg=fundo)
        self._redesenhar()


class BotaoR(tk.Canvas):
    """Botão arredondado com ícone + texto."""

    def __init__(self, pai, texto, comando, ico=None, altura=40, bg_pai=CARTAO, cor_texto=TEXTO, negrito=False,
                 fundo=None, largura=None):
        super().__init__(pai, bg=bg_pai, highlightthickness=0, bd=0, height=altura, cursor="hand2",
                         **({"width": largura} if largura else {}))
        self.texto, self.ico, self.comando = texto, ico, comando
        self.cor_texto, self.negrito, self.fundo = cor_texto, negrito, fundo or bg_pai
        self.ativo, self.sobre = True, False
        self.bind("<Configure>", lambda _e: self._desenhar())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<Button-1>", lambda _e: self.ativo and self.comando and self.comando())

    def _hover(self, s):
        self.sobre = s
        self._desenhar()

    def _desenhar(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        fundo = HOVER if (self.sobre and self.ativo) else self.fundo
        _ret_arredondado(self, 1, 1, w - 2, h - 2, 10, fill=fundo, outline=BORDA, width=1)
        cor = self.cor_texto if self.ativo else APAGADO
        f_txt = tkfont.Font(family=FONTE, size=11, weight="bold" if self.negrito else "normal")
        lt = f_txt.measure(self.texto)
        li = 0
        if self.ico:
            f_ico = tkfont.Font(family=fonte_icone(11)[0], size=11)
            li = f_ico.measure(self.ico) + 8
        x = (w - lt - li) / 2
        if self.ico:
            self.create_text(x, h / 2, text=self.ico, font=fonte_icone(11), fill=cor, anchor="w")
        self.create_text(x + li, h / 2, text=self.texto, font=f_txt, fill=cor, anchor="w")

    def configure(self, cnf=None, **kw):  # noqa: D401
        mudou = False
        for k in ("text", "fg", "state", "icone", "bg_pai"):
            if k in kw:
                v = kw.pop(k)
                if k == "text":
                    self.texto = v
                elif k == "fg":
                    self.cor_texto = v
                elif k == "state":
                    self.ativo = v != "disabled"
                elif k == "icone":
                    self.ico = v
                elif k == "bg_pai":
                    self.fundo = v
                    kw["bg"] = v
                mudou = True
        r = super().configure(cnf, **kw) if (cnf or kw) else None
        if mudou:
            self._desenhar()
        return r

    config = configure


class Painel:
    def __init__(self, raiz):
        global FONTE_ICONE
        self.raiz = raiz
        familias = set(tkfont.families(raiz))
        FONTE_ICONE = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in familias), None)
        self.cfg = relatorio.ler_config()
        self.fila = queue.Queue()
        self.gravador = None
        self.thread = None
        self.fechando = False
        self.relatorios = []
        self.log_visivel = False
        self.estado_atual = "parado"
        self.info = {}

        raiz.title("Performance Analytics F1 26")
        raiz.configure(bg=FUNDO)
        raiz.geometry("520x560")
        raiz.resizable(False, False)
        try:
            raiz.iconbitmap(os.path.join(PASTA, "icone.ico"))
        except tk.TclError:
            pass
        self.sem_moldura = self._tirar_moldura()

        self.var_pasta = tk.StringVar(value=self.cfg.get("pasta_saida", ""))
        self.var_abrir = tk.BooleanVar(value=self.cfg.get("abrir", True))
        self.var_porta = tk.StringVar(value=str(self.cfg.get("porta", 20777)))

        # janela com cantos arredondados: o fundo da janela vira transparente e o cartão é desenhado arredondado
        if self.sem_moldura and (sys.platform.startswith("win") or os.environ.get("PA_ARREDONDAR")):
            chave = "#010203"
            raiz.configure(bg=chave)
            try:
                raiz.attributes("-transparentcolor", chave)
            except tk.TclError:
                pass
            moldura = Caixa(raiz, fundo=CARTAO, borda=BORDA, raio=18, pad=7, bg_pai=chave)
            moldura.pack(fill="both", expand=True)
            base = moldura.dentro
        else:
            base = tk.Frame(raiz, bg=CARTAO, highlightbackground=LINHA, highlightthickness=1)
            base.pack(fill="both", expand=True)

        # ---------------------------------------------------------------- barra de título própria
        barra = tk.Frame(base, bg=CARTAO)
        barra.pack(fill="x")
        try:
            self.img_logo = tk.PhotoImage(file=os.path.join(PASTA, "icone_28.png"))
            tk.Label(barra, image=self.img_logo, bg=CARTAO).pack(side="left", padx=(16, 10), pady=12)
        except tk.TclError:
            pass
        titulo = rotulo(barra, "Performance Analytics F1 26", 12, "bold")
        titulo.pack(side="left", pady=12)
        for nome, cmd, cor in (("fechar", self.ao_fechar, "#C42B1C"), ("min", self.minimizar, HOVER)):
            b = tk.Label(barra, text=icone(nome), font=fonte_icone(10), fg=TEXTO2, bg=CARTAO, width=5, cursor="hand2")
            b.pack(side="right", fill="y")
            b.bind("<Button-1>", lambda _e, c=cmd: c())
            b.bind("<Enter>", lambda _e, w=b, c=cor: w.configure(bg=c, fg="#FFFFFF" if c != HOVER else TEXTO))
            b.bind("<Leave>", lambda _e, w=b: w.configure(bg=CARTAO, fg=TEXTO2))
        eng = BotaoR(barra, "", self.abrir_configuracoes, ico=icone("config"), altura=34, largura=38)
        eng.pack(side="right", padx=(0, 6))
        if versao():
            rotulo(barra, f"v{versao()}", 10, cor=APAGADO).pack(side="right", padx=(0, 10))
        for w in (barra, titulo):
            w.bind("<ButtonPress-1>", self._arrastar_ini)
            w.bind("<B1-Motion>", self._arrastar)
        tk.Frame(base, bg=LINHA, height=1).pack(fill="x")

        corpo = tk.Frame(base, bg=CARTAO)
        corpo.pack(fill="both", expand=True, padx=18, pady=16)

        # ---------------------------------------------------------------- status
        f0, t0, p0 = ESTADOS["parado"]
        self.st = Caixa(corpo, fundo=f0, borda=None, raio=12, pad=16)
        self.st.pack(fill="x")
        dentro = self.st.dentro
        self.ponto = tk.Canvas(dentro, width=16, height=16, bg=f0, highlightthickness=0)
        self.ponto.pack(side="left", padx=(0, 12))
        self.bolinha = self.ponto.create_oval(1, 1, 15, 15, fill=p0, outline="")
        txt = tk.Frame(dentro, bg=f0)
        txt.pack(side="left", fill="x", expand=True)
        self.var_estado = tk.StringVar(value="Parado")
        self.var_detalhe = tk.StringVar(value="Clique em Iniciar para começar a gravar.")
        self.lbl_estado = tk.Label(txt, textvariable=self.var_estado, font=(FONTE, 12, "bold"), anchor="w",
                                   justify="left", wraplength=260, bg=f0, fg=t0)
        self.lbl_estado.pack(anchor="w", fill="x")
        self.lbl_detalhe = tk.Label(txt, textvariable=self.var_detalhe, font=(FONTE, 10), anchor="w",
                                    justify="left", wraplength=260, bg=f0, fg=t0)
        self.lbl_detalhe.pack(anchor="w", fill="x")
        self.botao = BotaoR(dentro, "Iniciar", self.alternar, ico=icone("iniciar"), altura=44, largura=130,
                            bg_pai=f0, fundo=f0, negrito=True)
        self.botao.pack(side="right")
        self.partes_status = (dentro, self.ponto, txt, self.lbl_estado, self.lbl_detalhe)

        # ---------------------------------------------------------------- ações
        acoes = tk.Frame(corpo, bg=CARTAO)
        acoes.pack(fill="x", pady=(12, 0))
        for i in range(3):
            acoes.columnconfigure(i, weight=1, uniform="a")
        BotaoR(acoes, "Abrir pasta", self.abrir_pasta, ico=icone("pasta"), altura=46).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        BotaoR(acoes, "Mapear pista", self.mapear_pista, ico=icone("mapa"), altura=46).grid(row=0, column=1, sticky="ew", padx=3)
        self.bt_atualizar = BotaoR(acoes, "Atualizar", self.atualizar_programa, ico=icone("atualizar"), altura=46)
        self.bt_atualizar.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # ---------------------------------------------------------------- últimos relatórios
        rotulo(corpo, "Últimos relatórios", 10, cor=TEXTO2).pack(anchor="w", pady=(16, 6))
        self.caixa = Caixa(corpo, fundo=CARTAO, borda=BORDA, raio=12, pad=5)
        self.caixa.pack(fill="x")
        self.caixa_rel = self.caixa.dentro

        # ---------------------------------------------------------------- registro (recolhido)
        lg = tk.Frame(corpo, bg=CARTAO, cursor="hand2")
        lg.pack(anchor="w", pady=(14, 0))
        self.ico_log = tk.Label(lg, text=icone("registro"), font=fonte_icone(9), fg=APAGADO, bg=CARTAO)
        self.ico_log.pack(side="left", padx=(2, 8))
        self.bt_log = tk.Label(lg, text="Registro (mostrar)", font=(FONTE, 10), fg=APAGADO, bg=CARTAO)
        self.bt_log.pack(side="left")
        for w in (lg, self.ico_log, self.bt_log):
            w.bind("<Button-1>", lambda _e: self.alternar_log())
        self.texto = tk.Text(corpo, height=6, wrap="word", state="disabled", font=("Consolas", 9),
                             background=LOG_FUNDO, foreground=LOG_TEXTO, relief="flat", borderwidth=0,
                             padx=10, pady=8, highlightthickness=1, highlightbackground=LINHA)

        raiz.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        threading.Thread(target=self.renovar_atalho, daemon=True).start()
        raiz.after(150, self.processar_fila)
        raiz.after(1500, self.checar_atualizacao)
        self.carregar_relatorios()
        raiz.after(50, self._ajustar_tamanho)

        if self.var_pasta.get():
            raiz.after(300, self.iniciar)
        else:
            self.escrever("Escolha a pasta onde os relatórios vão ficar para começar.")
            raiz.after(400, self.abrir_configuracoes)

    def renovar_atalho(self):
        """Troca o atalho antigo "Telemetria F1 26" da Área de Trabalho pelo novo, com o nome e o ícone novos."""
        if not sys.platform.startswith("win"):
            return
        q = lambda x: str(x).replace("'", "''")
        exe = sys.executable
        if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
            exe = exe[:-10] + "pythonw.exe"
        ps = (
            "$d=[Environment]::GetFolderPath('Desktop');"
            "$old=Join-Path $d 'Telemetria F1 26.lnk';"
            "if(Test-Path $old){"
            "$s=New-Object -ComObject WScript.Shell;"
            "$a=$s.CreateShortcut((Join-Path $d 'Performance Analytics F1 26.lnk'));"
            f"$a.TargetPath='{q(exe)}';"
            f"$a.Arguments='\"{q(os.path.join(PASTA, 'painel.pyw'))}\"';"
            f"$a.WorkingDirectory='{q(PASTA)}';"
            f"$a.IconLocation='{q(os.path.join(PASTA, 'icone.ico'))},0';"
            "$a.Description='Grava a telemetria do F1 26 e gera o relatório ao fim da sessão';"
            "$a.Save(); Remove-Item $old -Force}"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           creationflags=0x08000000, timeout=30)
        except Exception:  # noqa: BLE001
            pass

    def _ajustar_tamanho(self):
        self.raiz.update_idletasks()
        h = self.raiz.winfo_reqheight()
        self.raiz.geometry(f"520x{h}")

    # ------------------------------------------------------------ janela sem moldura (minimizar, fechar, arrastar)
    def _tirar_moldura(self):
        try:
            self.raiz.overrideredirect(True)
            if sys.platform.startswith("win"):
                import ctypes
                self.raiz.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.raiz.winfo_id())
                # sem moldura o Windows tira a janela da barra de tarefas: devolve o botão dela
                estilo = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                estilo = (estilo & ~0x00000080) | 0x00040000
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, estilo)
                # cantos arredondados do Windows 11 (no Windows 10 não faz nada)
                try:
                    pref = ctypes.c_int(2)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
                except Exception:  # noqa: BLE001
                    pass
                self.raiz.withdraw()
                self.raiz.after(10, self.raiz.deiconify)
            self.raiz.update_idletasks()
            x = (self.raiz.winfo_screenwidth() - 520) // 2
            y = (self.raiz.winfo_screenheight() - 560) // 3
            self.raiz.geometry(f"+{x}+{y}")
            self.raiz.bind("<Map>", self._ao_restaurar)
            return True
        except Exception:  # noqa: BLE001  (se der errado, fica a moldura normal do Windows)
            try:
                self.raiz.overrideredirect(False)
            except Exception:  # noqa: BLE001
                pass
            return False

    def minimizar(self):
        if self.sem_moldura:
            self.raiz.overrideredirect(False)   # o Windows só minimiza janela com moldura
        self.raiz.iconify()

    def _ao_restaurar(self, _ev=None):
        if self.sem_moldura and self.raiz.state() == "normal":
            self.raiz.after(10, lambda: self.raiz.overrideredirect(True))

    def _arrastar_ini(self, ev):
        self._dx, self._dy = ev.x_root - self.raiz.winfo_x(), ev.y_root - self.raiz.winfo_y()

    def _arrastar(self, ev):
        self.raiz.geometry(f"+{ev.x_root - self._dx}+{ev.y_root - self._dy}")

    # ------------------------------------------------------------ status
    def mostrar_estado(self, texto):
        t = texto.lower()
        if t.startswith("gravando") and self.info.get("pista"):
            texto = " · ".join(x for x in ("Gravando", self.info.get("pista"), self.info.get("sessao")) if x)
        self.var_estado.set(texto)
        chave = ("gravando" if t.startswith("gravando") else "gerando" if t.startswith("gerando")
                 else "pronto" if t.startswith("relatório pronto") else "erro" if t.startswith(("erro", "formato"))
                 else "parado" if t.startswith(("parado", "parando")) else "aguardando")
        self.estado_atual = chave
        fundo, cor_txt, cor_ponto = ESTADOS[chave]
        self.st.cor(fundo)
        for w in self.partes_status:
            w.configure(bg=fundo)
        self.botao.configure(bg_pai=fundo)
        self.lbl_estado.configure(fg=cor_txt)
        self.lbl_detalhe.configure(fg=cor_txt)
        self.ponto.itemconfigure(self.bolinha, fill=cor_ponto)
        if chave == "aguardando" and t.startswith("aguardando"):
            self.var_detalhe.set(f"Escutando na porta {self.var_porta.get()}. Entre numa sessão no jogo.")

    def mostrar_info(self, info):
        self.info = info
        if self.estado_atual == "gravando":
            cab = " · ".join(x for x in ("Gravando", info.get("pista"), info.get("sessao")) if x)
            self.var_estado.set(cab)
        partes = []
        if info.get("volta"):
            partes.append(f"Volta {info['volta']}")
        if info.get("melhor"):
            partes.append(f"{fmt_volta(info['melhor'])} melhor")
        if info.get("pacotes") is not None:
            partes.append(f"{info['pacotes']} pacotes/s")
        if partes:
            self.var_detalhe.set(" · ".join(partes))

    # ------------------------------------------------------------ relatórios
    def carregar_relatorios(self):
        p = self.var_pasta.get()
        arqs = glob.glob(os.path.join(p, "*", "*.html")) if p else []
        arqs.sort(key=os.path.getmtime, reverse=True)
        self.relatorios = [os.path.normpath(a) for a in arqs]
        self.desenhar_relatorios()

    def adicionar_relatorio(self, caminho):
        caminho = os.path.normpath(caminho)
        if caminho in self.relatorios:
            self.relatorios.remove(caminho)
        self.relatorios.insert(0, caminho)
        self.desenhar_relatorios(novo=caminho)

    def desenhar_relatorios(self, novo=None):
        for w in self.caixa_rel.winfo_children():
            w.destroy()
        if not self.relatorios:
            rotulo(self.caixa_rel, "Nenhum relatório ainda. Ao terminar uma sessão, ele aparece aqui.", 10,
                   cor=APAGADO, anchor="center").pack(fill="x", pady=20)
            return
        for k, cam in enumerate(self.relatorios[:5]):
            nome, quando, corrida = descrever_relatorio(cam)
            if k:
                tk.Frame(self.caixa_rel, bg=LINHA, height=1).pack(fill="x")
            lin = tk.Frame(self.caixa_rel, bg=CARTAO, cursor="hand2")
            lin.pack(fill="x", padx=10)
            partes = [
                tk.Label(lin, text=icone("corrida" if corrida else "quali"), font=fonte_icone(11), bg=CARTAO,
                         fg=TEXTO2, width=3),
                tk.Label(lin, text=nome, font=(FONTE, 11, "bold" if cam == novo else "normal"), bg=CARTAO, fg=TEXTO,
                         anchor="w"),
                tk.Label(lin, text=icone("abrir"), font=fonte_icone(10), bg=CARTAO, fg=AZUL, width=3),
                tk.Label(lin, text=quando, font=(FONTE, 10), bg=CARTAO, fg=APAGADO),
            ]
            partes[0].pack(side="left", pady=10)
            partes[1].pack(side="left", fill="x", expand=True, padx=(4, 0))
            partes[2].pack(side="right")
            partes[3].pack(side="right", padx=(0, 6))
            for w in [lin] + partes:
                w.bind("<Button-1>", lambda _e, c=cam: webbrowser.open(pathlib.Path(c).resolve().as_uri()))
                w.bind("<Enter>", lambda _e, ws=[lin] + partes: [x.configure(bg=HOVER) for x in ws])
                w.bind("<Leave>", lambda _e, ws=[lin] + partes: [x.configure(bg=CARTAO) for x in ws])
        if len(self.relatorios) > 5:
            tk.Frame(self.caixa_rel, bg=LINHA, height=1).pack(fill="x")
            mais = tk.Label(self.caixa_rel, text=f"Ver todos ({len(self.relatorios)}) na pasta", font=(FONTE, 10),
                            fg=AZUL, bg=CARTAO, cursor="hand2")
            mais.pack(pady=8)
            mais.bind("<Button-1>", lambda _e: self.abrir_pasta())
        self.raiz.after(30, self._ajustar_tamanho)

    def alternar_log(self):
        self.log_visivel = not self.log_visivel
        if self.log_visivel:
            self.texto.pack(fill="x", pady=(8, 0))
            self.bt_log.configure(text="Registro (ocultar)")
            self.ico_log.configure(text=icone("registro_aberto"))
        else:
            self.texto.pack_forget()
            self.bt_log.configure(text="Registro (mostrar)")
            self.ico_log.configure(text=icone("registro"))
        self._ajustar_tamanho()

    # ------------------------------------------------------------ configurações (janelinha da engrenagem)
    def abrir_configuracoes(self):
        jan = tk.Toplevel(self.raiz)
        jan.title("Configurações")
        jan.configure(bg=CARTAO)
        jan.resizable(False, False)
        jan.transient(self.raiz)
        try:
            jan.iconbitmap(os.path.join(PASTA, "icone.ico"))
        except tk.TclError:
            pass
        c = tk.Frame(jan, bg=CARTAO)
        c.pack(fill="both", expand=True, padx=20, pady=16)
        rotulo(c, "Configurações", 13, "bold").pack(anchor="w", pady=(0, 10))
        rotulo(c, "Onde salvar os relatórios:", 10).pack(anchor="w")
        lp = tk.Frame(c, bg=CARTAO)
        lp.pack(fill="x", pady=(4, 2))
        tk.Entry(lp, textvariable=self.var_pasta, state="readonly", width=46, readonlybackground=HOVER, fg=TEXTO, relief="flat", highlightthickness=1, highlightbackground=BORDA).pack(side="left", fill="x", expand=True, ipady=2)
        botao(lp, "Escolher...", lambda: self.escolher_pasta(jan)).pack(side="left", padx=(8, 0))
        rotulo(c, 'Cada fim de semana vira uma pasta, como "Brasil 11-11-2026 19h07", com a quali e a corrida.', 9,
               cor=APAGADO, wraplength=420, justify="left").pack(anchor="w", pady=(4, 12))
        tk.Checkbutton(c, text="Abrir o relatório quando ficar pronto", variable=self.var_abrir, bg=CARTAO, fg=TEXTO,
                       selectcolor=HOVER, activebackground=CARTAO, activeforeground=TEXTO, font=(FONTE, 10),
                       command=self.salvar_cfg).pack(anchor="w")
        lpo = tk.Frame(c, bg=CARTAO)
        lpo.pack(anchor="w", pady=(10, 0))
        rotulo(lpo, "Porta UDP:", 10).pack(side="left", padx=(0, 8))
        tk.Entry(lpo, textvariable=self.var_porta, width=8, bg=HOVER, fg=TEXTO, insertbackground=TEXTO, relief="flat", highlightthickness=1, highlightbackground=BORDA).pack(side="left", ipady=2)
        rotulo(lpo, "(a mesma do jogo; padrão 20777)", 9, cor=APAGADO).pack(side="left", padx=(8, 0))

        def ok():
            self.salvar_cfg()
            jan.destroy()
        botao(c, "Salvar", ok, negrito=True).pack(anchor="e", pady=(16, 0))
        jan.update_idletasks()
        x = self.raiz.winfo_x() + (self.raiz.winfo_width() - jan.winfo_width()) // 2
        y = self.raiz.winfo_y() + 60
        jan.geometry(f"+{max(0, x)}+{max(0, y)}")
        jan.grab_set()

    def salvar_cfg(self):
        self.cfg["pasta_saida"] = self.var_pasta.get()
        self.cfg["abrir"] = self.var_abrir.get()
        try:
            self.cfg["porta"] = int(self.var_porta.get())
        except ValueError:
            pass
        relatorio.salvar_config(self.cfg)

    def escolher_pasta(self, pai=None):
        atual = self.var_pasta.get() or str(pathlib.Path.home() / "Documents")
        p = filedialog.askdirectory(parent=pai or self.raiz, title="Onde salvar os relatórios do F1 26?",
                                    initialdir=atual, mustexist=False)
        if not p:
            return
        self.var_pasta.set(os.path.normpath(p))
        self.salvar_cfg()
        self.escrever(f"Pasta escolhida: {self.var_pasta.get()}")
        self.carregar_relatorios()
        if self.gravador:
            self.gravador.pasta_saida = self.var_pasta.get()
        else:
            self.iniciar()

    def abrir_pasta(self):
        p = self.var_pasta.get()
        if not p:
            self.abrir_configuracoes()
            return
        os.makedirs(p, exist_ok=True)
        abrir_no_sistema(p)

    # ------------------------------------------------------------ atualização pelo GitHub
    def checar_atualizacao(self):
        def trabalho():
            try:
                import atualizar
                novo, loc, rem = atualizar.tem_atualizacao()
                if novo:
                    self.fila.put(("log", f"Versão nova disponível ({rem}; você tem a {loc}). Clique em Atualizar."))
                    self.fila.put(("novaversao", rem))
            except Exception:  # noqa: BLE001  (sem internet: segue sem avisar)
                pass
        threading.Thread(target=trabalho, daemon=True).start()

    def atualizar_programa(self):
        if self.gravador:
            messagebox.showinfo("Atualizar", "Pare a gravação antes de atualizar.")
            return
        self.escrever("Procurando atualização no GitHub...")
        self.bt_atualizar.configure(state="disabled")

        def trabalho():
            try:
                import atualizar
                novo, loc, rem = atualizar.tem_atualizacao()
                if not novo:
                    self.fila.put(("aviso", ("Atualizar", f"Você já está na versão mais nova ({loc}).", False)))
                else:
                    ver, n = atualizar.atualizar()
                    self.fila.put(("aviso", ("Atualizado", f"Versão {ver} instalada ({n} arquivos). "
                                             "Feche esta janela e abra de novo pelo atalho para usar a versão nova.", False)))
            except Exception as e:  # noqa: BLE001
                self.fila.put(("aviso", ("Não deu para atualizar",
                                         f"Verifique a internet e tente de novo.\n\n{type(e).__name__}: {e}", True)))
            self.fila.put(("fim_atualizar", None))
        threading.Thread(target=trabalho, daemon=True).start()

    # ------------------------------------------------------------ bordas da pista
    def mapear_pista(self):
        ok = messagebox.askokcancel(
            "Mapear bordas da pista",
            "Para o traçado e replay mostrarem a pista com as bordas certas:\n\n"
            "1. Com o programa gravando, entre na pista (o contra o relógio é o melhor).\n"
            "2. Dê uma volta completa devagar, colado na borda ESQUERDA da pista.\n"
            "3. Dê outra volta completa colado na borda DIREITA.\n"
            "4. Saia da sessão para a gravação fechar.\n"
            "5. Clique de novo aqui e escolha a gravação (.f1rec.gz) dessa sessão,\n"
            "    que fica na pasta 'dados' do evento.\n\n"
            "Não precisa ser volta válida. Faça uma vez por pista.\n\nEscolher a gravação agora?")
        if not ok:
            return
        caminho = filedialog.askopenfilename(
            title="Escolha a gravação com as voltas nas bordas", initialdir=self.var_pasta.get() or PASTA,
            filetypes=[("Gravação do F1 26", "*.f1rec.gz"), ("Todos os arquivos", "*.*")])
        if not caminho:
            return
        self.escrever(f"Mapeando as bordas da pista com {os.path.basename(caminho)}...")

        def trabalho():
            try:
                import pistas
                self.fila.put(("aviso", ("Bordas da pista", pistas.mapear(caminho), False)))
            except ValueError as e:
                self.fila.put(("aviso", ("Não deu para mapear", str(e), True)))
            except Exception as e:  # noqa: BLE001
                self.fila.put(("aviso", ("Erro ao mapear", f"{type(e).__name__}: {e}", True)))

        threading.Thread(target=trabalho, daemon=True).start()

    # ------------------------------------------------------------ gravação
    def alternar(self):
        if self.gravador:
            self.parar()
        else:
            self.iniciar()

    def iniciar(self):
        if self.gravador:
            return
        if not self.var_pasta.get():
            self.abrir_configuracoes()
            return
        try:
            porta = int(self.var_porta.get())
        except ValueError:
            messagebox.showerror("Porta inválida", "A porta precisa ser um número (o padrão é 20777).")
            return
        self.salvar_cfg()
        os.makedirs(self.var_pasta.get(), exist_ok=True)
        self.gravador = Gravador(
            porta=porta, pasta_saida=self.var_pasta.get(), abrir=self.var_abrir.get(),
            ao_log=lambda m: self.fila.put(("log", m)),
            ao_relatorio=lambda c: self.fila.put(("rel", c)),
            ao_estado=lambda e: self.fila.put(("estado", e)),
            ao_info=lambda i: self.fila.put(("info", i)),
        )
        self.thread = threading.Thread(target=self._rodar, daemon=True)
        self.thread.start()
        self.botao.configure(text="Parar", icone=icone("parar"), fg=VERMELHO)

    def _rodar(self):
        self.gravador.rodar()
        self.fila.put(("fim", None))

    def parar(self):
        if self.gravador:
            self.mostrar_estado("Parando...")
            self.var_detalhe.set("Gerando o relatório, se houver sessão gravada.")
            self.botao.configure(state="disabled")
            self.gravador.parar()

    # ------------------------------------------------------------ fila de mensagens
    def escrever(self, msg):
        self.texto.configure(state="normal")
        self.texto.insert("end", msg + "\n")
        self.texto.see("end")
        self.texto.configure(state="disabled")

    def processar_fila(self):
        try:
            while True:
                tipo, val = self.fila.get_nowait()
                if tipo == "log":
                    self.escrever(val)
                elif tipo == "estado":
                    self.mostrar_estado(val)
                elif tipo == "info":
                    self.mostrar_info(val)
                elif tipo == "rel":
                    self.adicionar_relatorio(val)
                elif tipo == "novaversao":
                    self.bt_atualizar.configure(text="Atualizar  ●", fg=AZUL)
                elif tipo == "fim_atualizar":
                    self.bt_atualizar.configure(state="normal")
                elif tipo == "aviso":
                    titulo, texto, erro = val
                    self.escrever(texto)
                    (messagebox.showwarning if erro else messagebox.showinfo)(titulo, texto)
                elif tipo == "fim":
                    self.gravador = None
                    self.botao.configure(text="Iniciar", icone=icone("iniciar"), state="normal", fg=TEXTO)
                    self.mostrar_estado("Parado")
                    self.var_detalhe.set("Clique em Iniciar para começar a gravar.")
                    if self.fechando:
                        self.raiz.destroy()
                        return
        except queue.Empty:
            pass
        self.raiz.after(150, self.processar_fila)

    def ao_fechar(self):
        if self.gravador:
            self.fechando = True
            self.parar()
        else:
            self.raiz.destroy()


def main():
    try:
        raiz = tk.Tk()
        Painel(raiz)
        raiz.mainloop()
    except Exception:
        # sem console (pythonw): guarda o erro num arquivo e avisa
        import traceback
        with open(os.path.join(PASTA, "erro.txt"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        try:
            messagebox.showerror("Performance Analytics F1 26",
                                 "Deu um erro ao abrir. Os detalhes estão em erro.txt, na pasta do programa.")
        except Exception:
            pass


if __name__ == "__main__":
    main()
