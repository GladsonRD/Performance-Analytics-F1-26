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


def para_relatorio(geo, passo, n):
    """Linha central e bordas na grade do relatório (um ponto a cada `passo` metros)."""
    if not geo or not geo.get("esq"):
        return None
    ex, ez, dx, dz = _bordas(geo)
    d = [i * geo["passo"] for i in range(len(geo["cx"]))]
    alvo = [i * passo for i in range(n)]
    f = lambda ys: [round(v, 1) for v in analise._reamostrar(d, ys, alvo)]
    return {"fonte": geo["fonte"], "sessoes": geo.get("sessoes"), "quando": geo.get("quando"),
            "cx": f(geo["cx"]), "cz": f(geo["cz"]), "ex": f(ex), "ez": f(ez), "dx": f(dx), "dz": f(dz)}
