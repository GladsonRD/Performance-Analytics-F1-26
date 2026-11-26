"""
Bordas das pistas para o traçado e replay.

O jogo não transmite onde fica o asfalto, só a posição dos carros. Então cada pista ganha um
arquivo em pistas/<id da pista>.json com a linha central e as duas bordas, de um destes jeitos:

  - "mapeada": você faz uma volta colado na borda esquerda e outra colado na direita (de
    preferência no contra o relógio) e manda o painel mapear essa gravação. É o mais preciso.
  - pistas_base/: mapas já feitos ("mapeada") que vêm com o programa; valem quando você não
    mapeou a pista, mesmo que já tenha um mapa acumulado dela.
  - "acumulada": cada relatório gerado junta os traçados de todos os pilotos da sessão; a borda é
    até onde os carros já passaram, com folga. Melhora sozinha com o tempo.

Tudo é alinhado pela distância da volta que o próprio jogo manda (lap_distance), então voltas por
dentro e por fora da curva caem no mesmo ponto da pista.
"""

import json
import math
import os
import statistics
import time

import analise

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pistas")
PASTA_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pistas_base")   # mapas que vêm com o programa
G = 5.0              # metros entre pontos guardados
MEIO_CARRO = 1.0     # do centro do carro até a lateral (a borda fica além disso)
FOLGA = 0.8          # folga extra na borda acumulada
MEIA_MIN = 5.0       # meia largura mínima


def _arquivo(pid):
    return os.path.join(PASTA, f"{pid}.json")


def _ler(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def carregar(pid):
    """Mapa da pista: o seu (pistas/) se for mapeado; senão o mapeado que vem com o programa
    (pistas_base/); senão o acumulado que você tiver."""
    local = _ler(_arquivo(pid))
    if local and local.get("fonte") == "mapeada":
        return local
    base = _ler(os.path.join(PASTA_BASE, f"{pid}.json"))
    if base and base.get("fonte") == "mapeada" and base.get("cx") and (
            not local or abs(base.get("comprimento", 0) - local.get("comprimento", 0)) <= 30):
        return base
    return local


def salvar(pid, geo):
    os.makedirs(PASTA, exist_ok=True)
    tmp = _arquivo(pid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geo, f)
    os.replace(tmp, _arquivo(pid))


def _grade(comp):
    return [k * G for k in range(int(comp // G))]


def _normais(cx, cz):
    n = len(cx)
    nx, nz = [], []
    for i in range(n):
        a, b = (i - 2) % n, (i + 2) % n
        tx, tz = cx[b] - cx[a], cz[b] - cz[a]
        tn = math.hypot(tx, tz) or 1.0
        nx.append(-tz / tn)
        nz.append(tx / tn)
    return nx, nz


def _suave(a, k):
    n = len(a)
    return [sum(a[(i + j) % n] for j in range(-k, k + 1)) / (2 * k + 1) for i in range(n)]


def _bordas(geo):
    """Pontos das duas bordas a partir da linha central e das meias larguras."""
    cx, cz = geo["cx"], geo["cz"]
    nx, nz = _normais(cx, cz)
    e, d = geo["esq"], geo["dir"]
    return ([x + nx[i] * e[i] for i, x in enumerate(cx)], [z + nz[i] * e[i] for i, z in enumerate(cz)],
            [x - nx[i] * d[i] for i, x in enumerate(cx)], [z - nz[i] * d[i] for i, z in enumerate(cz)])


# ------------------------------------------------------------------ volta de mapeamento
def _voltas_da_gravacao(caminho):
    p1 = analise.passada1(caminho)
    sess = p1["sess"]
    comp = sess["comprimento"]
    J = p1["jogador"]
    _, ps, _ = analise.passada2(caminho, {J: None})
    grade = _grade(comp)
    por_volta = {}
    for p in ps[J]:
        por_volta.setdefault(p[1], []).append(p)
    voltas = {}
    for nv, pts in por_volta.items():
        pts = sorted((p for p in pts if 0 <= p[2] <= comp), key=lambda p: p[0])
        lim, ult = [], -1.0
        for p in pts:                        # só o último trecho contínuo que anda para frente
            if p[2] < ult - 50:
                lim = []
            if not lim or p[2] > lim[-1][2]:
                lim.append(p)
            ult = p[2]
        if len(lim) < 50 or lim[0][2] > 40 or lim[-1][2] < comp - 40:
            continue
        d = [p[2] for p in lim]
        voltas[nv] = (analise._reamostrar(d, [p[3] for p in lim], grade), analise._reamostrar(d, [p[4] for p in lim], grade))
    return sess, comp, voltas


def mapear(caminho):
    """Lê uma gravação com uma volta colada em cada borda e grava as bordas da pista.
    Devolve um texto para mostrar ao usuário."""
    sess, comp, voltas = _voltas_da_gravacao(caminho)
    pid = sess["pista"]
    nome = analise.PISTAS.get(pid, f"Pista {pid}")
    if len(voltas) < 2:
        raise ValueError(f"Encontrei só {len(voltas)} volta(s) completa(s) em {nome}. Preciso de duas: "
                         "uma colada na borda esquerda e outra na direita.")
    n = len(next(iter(voltas.values()))[0])
    cx = [statistics.mean(v[0][i] for v in voltas.values()) for i in range(n)]
    cz = [statistics.mean(v[1][i] for v in voltas.values()) for i in range(n)]
    cx, cz = _suave(cx, 2), _suave(cz, 2)
    nx, nz = _normais(cx, cz)

    def lado(v):
        return statistics.mean((v[0][i] - cx[i]) * nx[i] + (v[1][i] - cz[i]) * nz[i] for i in range(n))

    lados = sorted(((lado(v), nv) for nv, v in voltas.items()))
    (o_dir, v_dir), (o_esq, v_esq) = lados[0], lados[-1]
    if o_esq - o_dir < 6:
        raise ValueError(f"As voltas de {nome} ficaram muito próximas uma da outra ({o_esq - o_dir:.1f} m em média). "
                         "Faça uma volta bem colada na borda esquerda e outra bem colada na direita.")
    E, D_ = voltas[v_esq], voltas[v_dir]
    # linha central nova = meio entre as duas voltas; bordas = cada volta + meio carro para fora
    mx = [(E[0][i] + D_[0][i]) / 2 for i in range(n)]
    mz = [(E[1][i] + D_[1][i]) / 2 for i in range(n)]
    mx, mz = _suave(mx, 1), _suave(mz, 1)
    nx, nz = _normais(mx, mz)
    esq = [max(MEIA_MIN, (E[0][i] - mx[i]) * nx[i] + (E[1][i] - mz[i]) * nz[i] + MEIO_CARRO) for i in range(n)]
    dir_ = [max(MEIA_MIN, -((D_[0][i] - mx[i]) * nx[i] + (D_[1][i] - mz[i]) * nz[i]) + MEIO_CARRO) for i in range(n)]
    geo = {"pista_id": pid, "nome": nome, "comprimento": comp, "passo": G, "fonte": "mapeada",
           "quando": time.strftime("%Y-%m-%d %H:%M"), "voltas": [v_esq, v_dir],
           "cx": [round(v, 2) for v in mx], "cz": [round(v, 2) for v in mz],
           "esq": [round(v, 2) for v in _suave(esq, 2)], "dir": [round(v, 2) for v in _suave(dir_, 2)]}
    salvar(pid, geo)
    larg = statistics.mean(a + b for a, b in zip(geo["esq"], geo["dir"]))
    return (f"Bordas de {nome} salvas: volta {v_esq} na borda esquerda e volta {v_dir} na direita "
            f"(largura média {larg:.1f} m). Os próximos relatórios dessa pista já usam essas bordas.")


# ------------------------------------------------------------------ biblioteca acumulada
# pista normal <-> invertida (mesmo asfalto, sentido contrário)
INVERTIDAS = {7: 39, 39: 7, 17: 40, 40: 17, 26: 41, 41: 26}


def _interp_circ(vals, L, d):
    """Valor de uma lista de pontos a cada G metros numa volta fechada de comprimento L, na distância d."""
    n = len(vals)
    d = d % L
    i = int(d // G)
    f = (d - i * G) / G
    a, b = vals[i % n], vals[(i + 1) % n]
    return a + (b - a) * f


def _inverter(base, comp, tracos, passo):
    """Monta a pista invertida a partir do mapa da pista no sentido normal.
    Inverte o sentido (a borda esquerda vira a direita) e acha onde fica a linha de chegada
    comparando com as voltas gravadas na pista invertida."""
    n0 = len(base["cx"])
    L = n0 * G
    # sentido contrário: o ponto k da invertida é o ponto -k da normal
    rx = [base["cx"][(-k) % n0] for k in range(n0)]
    rz = [base["cz"][(-k) % n0] for k in range(n0)]
    resq = [base["dir"][(-k) % n0] for k in range(n0)]
    rdir = [base["esq"][(-k) % n0] for k in range(n0)]
    # deslocamento da linha de chegada: para pontos das voltas gravadas, o ponto mais perto na linha invertida
    desl = []
    for t in tracos:
        if not (t.get("x") and t.get("z")) or t.get("pit"):
            continue
        m = min(len(t["x"]), len(t["z"]))
        for j in range(0, m, max(1, int(50 / passo))):
            x, z = t["x"][j], t["z"][j]
            if x is None or z is None:
                continue
            k = min(range(n0), key=lambda i: (rx[i] - x) ** 2 + (rz[i] - z) ** 2)
            if (rx[k] - x) ** 2 + (rz[k] - z) ** 2 > 30 ** 2:
                continue
            desl.append(((k * G - j * passo) % L) / L * 2 * math.pi)
        if len(desl) > 400:
            break
    if len(desl) < 20:
        return None
    # média circular, depois confere se a maioria concorda
    ang = math.atan2(sum(math.sin(a) for a in desl), sum(math.cos(a) for a in desl))
    s = (ang / (2 * math.pi) * L) % L
    perto = sum(1 for a in desl if abs(((a / (2 * math.pi) * L - s + L / 2) % L) - L / 2) < 40)
    if perto < 0.7 * len(desl):
        return None
    grade = _grade(comp)
    return {"pista_id": None, "comprimento": comp, "passo": G, "fonte": "mapeada", "invertida_de": base.get("pista_id"),
            "quando": time.strftime("%Y-%m-%d %H:%M"),
            "cx": [round(_interp_circ(rx, L, d + s), 2) for d in grade], "cz": [round(_interp_circ(rz, L, d + s), 2) for d in grade],
            "esq": [round(_interp_circ(resq, L, d + s), 2) for d in grade], "dir": [round(_interp_circ(rdir, L, d + s), 2) for d in grade]}


def acumular(pid, comp, tracos, passo):
    """Junta os traçados de uma sessão na biblioteca da pista e devolve a geometria."""
    geo = carregar(pid)
    if geo and abs(geo.get("comprimento", 0) - comp) > 30:
        geo = None                                    # outra versão da pista: recomeça
    if geo and geo.get("fonte") == "mapeada":
        return geo
    # pista invertida (ou normal) sem mapa, mas com o outro sentido mapeado: monta a partir dele
    par = carregar(INVERTIDAS[pid]) if pid in INVERTIDAS else None
    if par and par.get("fonte") == "mapeada" and abs(par.get("comprimento", 0) - comp) < 80:
        try:
            inv = _inverter(par, comp, tracos, passo)
        except Exception:  # noqa: BLE001
            inv = None
        if inv:
            inv["pista_id"] = pid
            inv["nome"] = analise.PISTAS.get(pid, f"Pista {pid}")
            salvar(pid, inv)
            return inv
    grade = _grade(comp)
    bons = [t for t in tracos if t.get("x") and t.get("z") and t.get("valida") and not t.get("pit")]
    if not bons:
        return geo

    def na_grade(t):
        d = [i * passo for i in range(min(len(t["x"]), len(t["z"])))]
        return analise._reamostrar(d, t["x"], grade), analise._reamostrar(d, t["z"], grade)

    linhas = [na_grade(t) for t in bons]
    n = len(grade)
    # descarta voltas com posição estranha (longe da mediana)
    mx = [statistics.median(l[0][i] for l in linhas) for i in range(n)]
    mz = [statistics.median(l[1][i] for l in linhas) for i in range(n)]
    linhas = [l for l in linhas if statistics.mean(math.hypot(l[0][i] - mx[i], l[1][i] - mz[i]) for i in range(0, n, 3)) < 6] or linhas
    if not geo:
        cx = _suave([statistics.mean(l[0][i] for l in linhas) for i in range(n)], 2)
        cz = _suave([statistics.mean(l[1][i] for l in linhas) for i in range(n)], 2)
        geo = {"pista_id": pid, "nome": analise.PISTAS.get(pid, f"Pista {pid}"), "comprimento": comp, "passo": G,
               "fonte": "acumulada", "sessoes": 0, "cx": [round(v, 2) for v in cx], "cz": [round(v, 2) for v in cz],
               "omax": [None] * n, "omin": [None] * n}
    cx, cz = geo["cx"], geo["cz"]
    n = min(n, len(cx))
    nx, nz = _normais(cx, cz)
    omax, omin = geo["omax"], geo["omin"]
    for l in linhas:
        for i in range(n):
            o = (l[0][i] - cx[i]) * nx[i] + (l[1][i] - cz[i]) * nz[i]
            if abs(o) > 22:
                continue
            if omax[i] is None or o > omax[i]:
                omax[i] = round(o, 2)
            if omin[i] is None or o < omin[i]:
                omin[i] = round(o, 2)
    geo["sessoes"] = geo.get("sessoes", 0) + 1
    geo["esq"] = [round(v, 2) for v in _suave([max(MEIA_MIN, (o if o is not None else 0) + MEIO_CARRO + FOLGA) for o in omax], 3)]
    geo["dir"] = [round(v, 2) for v in _suave([max(MEIA_MIN, -(o if o is not None else 0) + MEIO_CARRO + FOLGA) for o in omin], 3)]
    salvar(pid, geo)
    return geo


# ------------------------------------------------------------------ piso: zebras, grama e brita
# O pacote 6 diz o piso sob cada pneu (0 asfalto, 1 zebra, 4 brita, 7 grama...). Com a posição e o rumo
# do carro, cada pneu vira um ponto no mapa: juntando todos os carros e voltas, aparecem as zebras de
# verdade e onde tem grama ou brita. Fica em pistas/<id>_piso.json (alinhado com a linha central).
EIXO_D, EIXO_T, MEIA_BITOLA = 1.7, -1.7, 0.8      # posição dos pneus em relação ao centro do carro (m)
PNEUS = ((EIXO_T, -MEIA_BITOLA), (EIXO_T, MEIA_BITOLA), (EIXO_D, -MEIA_BITOLA), (EIXO_D, MEIA_BITOLA))   # TE, TD, DE, DD
ZEBRA, BRITA, GRAMA = 1, 4, 7
GRAMAS = {6, 7, 8}          # grama, grama "cortada" etc.
BRITAS = {4, 5, 9}          # brita, areia


def _arq_piso(pid, base=False):
    return os.path.join(PASTA_BASE if base else PASTA, f"{pid}_piso.json")


def _ref(geo):
    return [len(geo["cx"]), round(geo["cx"][0], 1), round(geo["cz"][0], 1)]


def _piso_vazio(geo):
    n = len(geo["cx"])
    z = lambda v: [v] * n
    return {"ref": _ref(geo), "ids": [], "zl": z(0), "zr": z(0), "zlo": z(None), "zro": z(None),
            "gl": z(0), "gr": z(0), "bl": z(0), "br": z(0), "al": z(None), "ar": z(None)}


def carregar_piso(pid, geo):
    """Piso acumulado da pista (o seu; senão o que vem com o programa), se bater com a linha central."""
    for base in (False, True):
        p = _ler(_arq_piso(pid, base))
        if p and p.get("ref") == _ref(geo):
            return p
    return None


def acumular_piso(pid, geo, posicoes, rid):
    """Soma ao piso da pista os pneus de todos os carros desta gravação (uma vez por gravação)."""
    if not geo or not geo.get("cx"):
        return None
    piso = carregar_piso(pid, geo) or _piso_vazio(geo)
    if rid and rid in piso["ids"]:
        return piso
    cx, cz = geo["cx"], geo["cz"]
    n = len(cx)
    nx, nz = _normais(cx, cz)
    perto = lambda i, wx, wz: min(((i + k) % n for k in range(-4, 5)), key=lambda m: (cx[m] - wx) ** 2 + (cz[m] - wz) ** 2)
    for ps in posicoes.values():
        for j in range(1, len(ps) - 1, 2):
            p = ps[j]
            sup = p[7] if len(p) > 7 else None
            if not sup:
                continue
            fora = any(s != 0 for s in sup)
            if not fora and j % 12 != 1:          # só asfalto: amostra menos (serve para a largura)
                continue
            hx, hz = math.sin(p[5]), math.cos(p[5])          # rumo do carro (yaw do pacote 0)
            lx, lz = -hz, hx
            i = int(round(p[2] / G)) % n
            for (fa, la), s in zip(PNEUS, sup):
                wx, wz = p[3] + hx * fa + lx * la, p[4] + hz * fa + lz * la
                k = perto(i, wx, wz)
                o = (wx - cx[k]) * nx[k] + (wz - cz[k]) * nz[k]
                if abs(o) > 40:
                    continue
                L = "l" if o > 0 else "r"
                ao = abs(o)
                if s == 0:
                    a = piso["a" + L]
                    if a[k] is None or ao > a[k]:
                        a[k] = round(ao, 2)
                elif s == ZEBRA:
                    piso["z" + L][k] += 1
                    zo = piso["z" + L + "o"]
                    if zo[k] is None or ao > zo[k]:
                        zo[k] = round(ao, 2)
                elif s in GRAMAS:
                    piso["g" + L][k] += 1
                elif s in BRITAS:
                    piso["b" + L][k] += 1
    if rid:
        piso["ids"] = (piso["ids"] + [rid])[-200:]
    try:
        os.makedirs(PASTA, exist_ok=True)
        tmp = _arq_piso(pid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(piso, f)
        os.replace(tmp, _arq_piso(pid))
    except OSError:
        pass
    return piso


def _trechos(marca, n, min_pts, junta):
    """Liga marcas próximas (buracos de até `junta` pontos) e tira trechos curtos demais."""
    out = list(marca)
    i = 0
    while i < n:                                  # fecha buracos pequenos
        if out[i]:
            j = i + 1
            while j < n and not out[j] and j - i <= junta + 1:
                j += 1
            if j < n and out[j] and j - i <= junta + 1:
                for k in range(i, j):
                    out[k] = True
            i = j if j > i else i + 1
        else:
            i += 1
    i = 0
    while i < n:                                  # tira os curtos
        if out[i]:
            j = i
            while j < n and out[j]:
                j += 1
            if j - i < min_pts:
                for k in range(i, j):
                    out[k] = False
            i = j
        else:
            i += 1
    return out


def piso_relatorio(piso, geo):
    """Por ponto da linha central (a cada G m) e por lado: largura da zebra além da borda (0 = sem zebra)
    e o que tem na área de escape (0 = não se sabe/asfalto, 1 = grama, 2 = brita)."""
    if not piso:
        return None
    n = len(geo["cx"])
    out = {}
    for L, borda in (("l", geo["esq"]), ("r", geo["dir"])):
        z = piso["z" + L]
        tem = _trechos([z[i] >= 2 for i in range(n)], n, 3, 5)      # liga buracos de até 25 m na mesma zebra
        tem = [tem[i] or (tem[(i - 1) % n] and z[i] >= 1) or (tem[(i + 1) % n] and z[i] >= 1) for i in range(n)]   # pontas
        larg = []
        for i in range(n):
            if not tem[i]:
                larg.append(0)
                continue
            zo = piso["z" + L + "o"][i]
            larg.append(round(min(2.2, max(1.0, (zo - borda[i] + 0.4) if zo is not None else 1.2)), 2))
        out["z" + L] = larg
        g, b = piso["g" + L], piso["b" + L]
        gt = _trechos([g[i] >= 1 for i in range(n)], n, 1, 3)
        bt = _trechos([b[i] >= 1 for i in range(n)], n, 1, 3)
        out["o" + L] = [2 if bt[i] and b[i] >= g[i] else 1 if gt[i] else 2 if bt[i] else 0 for i in range(n)]
    return out


# ------------------------------------------------------------------ pit lane
def carregar_box(pid, geo):
    """Pit lane: o do OpenStreetMap (vem com o programa, da entrada à saída) tem preferência; senão o das gravações."""
    b = _ler(os.path.join(PASTA_BASE, f"{pid}_box.json"))
    if b and b.get("ref") == _ref(geo) and b.get("fonte") == "OpenStreetMap" and b.get("linha"):
        return b
    for base in (False, True):
        b = _ler(os.path.join(PASTA_BASE if base else PASTA, f"{pid}_box.json"))
        if b and b.get("ref") == _ref(geo) and b.get("linha"):
            return b
    return None


def acumular_box(pid, geo, posicoes):
    """Guarda o caminho do pit lane (posições com status de box). Fica com a passagem mais completa:
    da entrada à saída, a cada ~3 m."""
    if not geo or not geo.get("cx"):
        return None
    atual = carregar_box(pid, geo)
    melhor = None
    for ps in posicoes.values():
        trecho = []
        for p in ps:
            box = p[8] if len(p) > 8 else 0
            if box:
                if not trecho or (p[3] - trecho[-1][0]) ** 2 + (p[4] - trecho[-1][1]) ** 2 >= 9:
                    trecho.append((round(p[3], 1), round(p[4], 1)))
            elif trecho:
                if len(trecho) > 20 and (melhor is None or len(trecho) > len(melhor)):
                    melhor = trecho
                trecho = []
        if len(trecho) > 20 and (melhor is None or len(trecho) > len(melhor)):
            melhor = trecho
    if not melhor or (atual and len(atual["linha"]) >= len(melhor)):
        return atual
    novo = {"ref": _ref(geo), "linha": [list(p) for p in melhor]}
    try:
        os.makedirs(PASTA, exist_ok=True)
        with open(os.path.join(PASTA, f"{pid}_box.json"), "w", encoding="utf-8") as f:
            json.dump(novo, f)
    except OSError:
        pass
    return novo


def carregar_muros(pid, geo):
    """Muros da pista (do OpenStreetMap, já encaixados no traçado do jogo), se batem com a linha central."""
    for base in (False, True):
        m = _ler(os.path.join(PASTA_BASE if base else PASTA, f"{pid}_muros.json"))
        if m and m.get("ref") == _ref(geo) and m.get("muros"):
            return m
    return None


def para_relatorio(geo, passo, n, piso=None, muros=None, box=None):
    """Linha central e bordas na grade do relatório (um ponto a cada `passo` metros)."""
    if not geo or not geo.get("esq"):
        return None
    if piso and geo.get("fonte") == "acumulada":
        # largura pelos pneus no asfalto (mais preciso que o centro do carro + folga)
        geo = dict(geo)
        for L, k in (("l", "esq"), ("r", "dir")):
            a = piso["a" + L]
            if sum(1 for v in a if v is not None) > len(a) * 0.6:
                ult = None
                cheio = []
                for i, v in enumerate(a):
                    ult = v if v is not None else ult
                    cheio.append(max(MEIA_MIN, (ult if ult is not None else geo[k][i]) + 0.3))
                geo[k] = _suave(cheio, 3)
    ex, ez, dx, dz = _bordas(geo)
    d = [i * geo["passo"] for i in range(len(geo["cx"]))]
    alvo = [i * passo for i in range(n)]
    f = lambda ys: [round(v, 1) for v in analise._reamostrar(d, ys, alvo)]
    out = {"fonte": geo["fonte"], "sessoes": geo.get("sessoes"), "quando": geo.get("quando"),
           "cx": f(geo["cx"]), "cz": f(geo["cz"]), "ex": f(ex), "ez": f(ez), "dx": f(dx), "dz": f(dz)}
    pr = piso_relatorio(piso, geo)
    if pr:
        # zebra: largura no ponto mais próximo (sem interpolar, para não borrar as pontas); escape idem
        m = len(geo["cx"])
        perto = lambda ys: [ys[min(m - 1, int(round(t / geo["passo"])))] for t in alvo]
        out.update({k: perto(v) for k, v in pr.items()})
        out["piso_ids"] = len(piso.get("ids") or [])
    if box:
        out["box"] = box["linha"]
    if muros:
        out["muros"] = muros["muros"]
        out["muros_credito"] = muros.get("credito")
        if muros.get("solo"):
            out["solo"] = muros["solo"]   # terreno em volta: areia, grama...
    return out
