"""Posição das curvas de cada pista (ápices) e divisão da volta em trechos por curva."""

import math

# Ápices oficiais (metros), conferidos com os mapas oficiais da F1 e gravações reais.
# Chave = id da pista no jogo.
CURVAS_OFICIAIS = {
    0: {"comp": 5276, "apices": [372, 492, 1122, 1242, 1458, 1890, 1992, 2130, 3324, 3420, 4158, 4398, 4668, 4782]},  # Melbourne
    31: {"comp": 6200, "apices": [300, 380, 540, 700, 1596, 1813, 2051, 2128, 2247, 2751, 3080, 3248, 3745, 5205, 5265,
                                  5340, 6132]},  # Las Vegas
}


def _suave(a, j):
    n = len(a)
    out = []
    for i in range(n):
        lo, hi = max(0, i - j), min(n - 1, i + j)
        out.append(sum(a[lo:hi + 1]) / (hi - lo + 1))
    return out


def apices_auto(x, z, v, passo):
    """Curvas pelo desenho da pista (quanto o carro vira), como no relatório."""
    n = min(len(x), len(v))
    w = max(2, round(12 / passo))
    th = []
    for i in range(n):
        a = math.atan2(z[min(n - 1, i + w)] - z[max(0, i - w)], x[min(n - 1, i + w)] - x[max(0, i - w)])
        if th:
            while a - th[-1] > math.pi:
                a -= 2 * math.pi
            while a - th[-1] < -math.pi:
                a += 2 * math.pi
        th.append(a)
    k = [(th[min(n - 1, i + w)] - th[max(0, i - w)]) / ((min(n - 1, i + w) - max(0, i - w)) * passo) for i in range(n)]
    ks = _suave(k, max(1, round(10 / passo)))
    lim = 1 / 500
    regs, i = [], 0
    while i < n:
        if abs(ks[i]) > lim:
            sg = 1 if ks[i] > 0 else -1
            a = i
            while i < n and ks[i] * sg > lim:
                i += 1
            regs.append((a, i - 1))
        else:
            i += 1
    out = []
    for a, b in regs:
        seg = [abs(ks[q]) for q in range(a, b + 1)]
        pk = [q for q in range(1, len(seg) - 1) if seg[q] >= seg[q - 1] and seg[q] >= seg[q + 1]] or [seg.index(max(seg))]
        grupos = [[pk[0]]]
        for q in pk[1:]:
            g = grupos[-1]
            vale = min(seg[g[-1]:q + 1])
            topo = min(max(seg[x_] for x_ in g), seg[q])
            if vale < 0.6 * topo and (q - g[-1]) * passo >= 40:
                grupos.append([q])
            else:
                g.append(q)
        cortes = [0]
        for g1, g2 in zip(grupos, grupos[1:]):
            m = max(g1)
            for q in range(max(g1), min(g2) + 1):
                if seg[q] < seg[m]:
                    m = q
            cortes.append(m)
        cortes.append(len(seg) - 1)
        for gi, g in enumerate(grupos):
            pico = max(g, key=lambda q: seg[q])
            ang = abs(th[a + cortes[gi + 1]] - th[a + cortes[gi]]) * 180 / math.pi
            raio = 1 / seg[pico]
            ip = a + pico
            jv = round(250 / passo)
            vmax = max(v[max(0, ip - jv):ip + 1])
            r40 = round(40 / passo)
            vmin = min(v[max(0, ip - r40):min(n, ip + r40 + 1)])
            queda = (vmax - vmin) / vmax if vmax else 0
            if ang >= 14 and (raio <= 220 or queda >= 0.04):
                out.append(ip)
    return out


def apices(pista_id, comprimento, passo, tracos):
    """Índices (na grade de distância) dos ápices. Oficiais quando conhecidos; senão, automáticos
    a partir da volta válida mais rápida que tem posição no mapa."""
    of = CURVAS_OFICIAIS.get(pista_id)
    if of:
        return [round(d * comprimento / of["comp"] / passo) for d in of["apices"]], True
    com_mapa = sorted([t for t in tracos if t.get("x") and t.get("valida")], key=lambda t: t["ms"]) or \
        [t for t in tracos if t.get("x")]
    if not com_mapa:
        return [], False
    t = com_mapa[0]
    return apices_auto(t["x"], t["z"], t["v"], passo), False


def trechos(lista_apices, v_ref, n):
    """Cada curva vai do fim da anterior até o ponto mais rápido antes da próxima (igual ao relatório)."""
    vs = _suave(v_ref[:n], 3)
    ap = [i for i in lista_apices if 0 < i < n - 1]
    out = []
    for k, i in enumerate(ap):
        fim = n - 1
        if k < len(ap) - 1:
            prox = ap[k + 1]
            fim = max(range(i, prox + 1), key=lambda j: vs[j])
        ini = out[-1]["fim"] if out else 0
        out.append({"k": k + 1, "i": i, "ini": ini, "fim": fim})
    return out
