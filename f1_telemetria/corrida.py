"""Análises só da corrida: degradação dos pneus por stint, paradas no box e ar limpo x tráfego.

Tudo sai dos tempos de volta de cada piloto (histórico do jogo), dos stints, das passagens pelo
box e da diferença para o líder ao fim de cada volta.
"""
import statistics

K_COMB = 0.03          # s por kg de combustível (peso: carro mais leve anda mais rápido)
QUEIMA_PADRAO = 1.5    # kg/volta quando não dá para medir
AR_SUJO = 1.0          # s: abaixo disso para o carro da frente = andando no ar sujo
AR_LIMPO = 2.0         # s: acima disso = ar limpo
MIN_VOLTAS_FIT = 4


def _theil_sen(xs, ys):
    """Inclinação robusta (mediana das inclinações entre pares): uma volta com erro não estraga a reta."""
    incl = [(ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[j] != xs[i]]
    if not incl:
        return 0.0, statistics.median(ys)
    b = statistics.median(incl)
    a = statistics.median(y - b * x for x, y in zip(xs, ys))
    return b, a


def _stints(D, c):
    for x in D.get("classificacao", []):
        if x["idx"] == c and x.get("stints"):
            return x["stints"]
    return D["stints"].get(c) or []


def _voltas_box(D, c):
    pit = set(D.get("pit_voltas", {}).get(c, []))
    if not pit:
        st = _stints(D, c)
        for x in st[:-1]:
            pit |= {x["fim"] + 1, x["fim"] + 2}
    return pit


def _voltas_sc(D):
    v = set()
    for s in D.get("sc") or []:
        v |= set(range(s["de"], s["ate"] + 2))
    return v


def _queima(D, c):
    """kg de combustível por volta do carro (mediana das voltas medidas)."""
    jog = D["meta"]["jogador"]
    if c == jog:
        g = [v["comb_gasto"] for v in D.get("jogador_voltas", []) if v.get("comb_gasto") and 0.3 < v["comb_gasto"] < 5]
    else:
        cc = D.get("comb_carro", {}).get(c) or {}
        ks = sorted(cc)
        g = [cc[a] - cc[b] for a, b in zip(ks, ks[1:]) if b == a + 1 and 0.3 < cc[a] - cc[b] < 5]
    if len(g) >= 2:
        return statistics.median(g), True
    if c != jog:
        q, ok = _queima(D, jog)
        if ok:
            return q, False
    return QUEIMA_PADRAO, False


def intervalos(D):
    """Diferença (s) para o carro da frente e o de trás ao cruzar a linha no fim de cada volta."""
    gaps, pos = D.get("gaps", {}), D.get("posicoes", {})
    por_volta = {}
    for c, pv in pos.items():
        for v, p in pv.items():
            por_volta.setdefault(v, {})[p] = c
    res = {}
    for c, pv in pos.items():
        lin = {}
        for v, p in pv.items():
            g = gaps.get(c, {}).get(v)
            if g is None:
                continue
            fr, tr = por_volta[v].get(p - 1), por_volta[v].get(p + 1)
            gf = gaps.get(fr, {}).get(v) if fr is not None else None
            gt = gaps.get(tr, {}).get(v) if tr is not None else None
            lin[v] = {"frente": round((g - gf) / 1000, 3) if gf is not None else None, "carro_frente": fr,
                      "tras": round((gt - g) / 1000, 3) if gt is not None else None, "carro_tras": tr}
        res[c] = lin
    return res


def analisar_corrida(D):
    jog = D["meta"]["jogador"]
    sc = _voltas_sc(D)
    inter = intervalos(D)
    degr, trafego, paradas = {}, {}, {}
    for c, vs in D["voltas"].items():
        st = _stints(D, c)
        box = _voltas_box(D, c)
        queima, medida = _queima(D, c)
        n_total = max((v["n"] for v in vs), default=0)
        stints_out, resid = [], {}
        ini = 0
        for k, x in enumerate(st):
            fim = n_total if x["fim"] == 255 else min(x["fim"] + 1, n_total)   # a volta de entrada ainda é do pneu velho
            if fim <= ini:
                continue
            todas = [v for v in vs if ini < v["n"] <= fim]
            limpas = [v for v in todas if v["n"] > 1 and v["n"] not in box and v["n"] not in sc]
            # tira voltas com erro grande (rodada, batida): mais de 3 s acima da mediana do stint
            if limpas:
                med = statistics.median(v["ms"] for v in limpas)
                limpas = [v for v in limpas if v["ms"] < med + 3000]
            item = {"stint": k + 1, "pneu": x["pneu"], "de": ini + 1, "ate": fim, "n_limpas": len(limpas),
                    "voltas": [{"n": v["n"], "ms": v["ms"], "idade": v["n"] - ini, "limpa": v in limpas} for v in todas]}
            if limpas:
                item["media_ms"] = round(statistics.mean(v["ms"] for v in limpas))
                item["melhor_ms"] = min(v["ms"] for v in limpas)
                if len(limpas) >= 3:
                    item["consistencia_s"] = round(statistics.pstdev(v["ms"] for v in limpas) / 1000, 3)
            if len(limpas) >= MIN_VOLTAS_FIT:
                xs = [v["n"] - ini for v in limpas]
                ys = [v["ms"] / 1000 for v in limpas]
                b, a = _theil_sen(xs, ys)
                corr = b + K_COMB * queima   # o carro fica mais leve a cada volta: sem isso a degradação parece menor
                item.update(bruta_s=round(b, 3), degr_s=round(corr, 3), base_s=round(a, 3))
                for v in limpas:
                    resid[v["n"]] = round(v["ms"] / 1000 - (a + b * (v["n"] - ini)), 3)
            stints_out.append(item)
            ini = fim
        degr[c] = {"stints": stints_out, "queima_kg": round(queima, 2), "queima_medida": medida}

        # ar limpo x tráfego: volta n começa no fim da volta n-1
        lin = []
        iv = inter.get(c, {})
        for v in vs:
            n = v["n"]
            a_, b_ = iv.get(n - 1, {}).get("frente"), iv.get(n, {}).get("frente")
            fr = [g for g in (a_, b_) if g is not None and g > 0]
            frente = round(statistics.mean(fr), 3) if fr else None
            cl = None
            if n > 1 and n not in box and n not in sc and frente is not None:
                cl = "sujo" if frente < AR_SUJO else "limpo" if frente > AR_LIMPO else "perto"
            lin.append({"n": n, "frente": frente, "tras": iv.get(n, {}).get("tras"), "carro_frente": iv.get(n, {}).get("carro_frente"),
                        "ar": cl, "resid": resid.get(n)})
        sujo = [x["resid"] for x in lin if x["ar"] == "sujo" and x["resid"] is not None]
        limpo = [x["resid"] for x in lin if x["ar"] in ("limpo", "perto") and x["resid"] is not None]
        t = {"voltas": lin, "n_sujo": sum(1 for x in lin if x["ar"] == "sujo"),
             "n_limpo": sum(1 for x in lin if x["ar"] == "limpo"), "n_perto": sum(1 for x in lin if x["ar"] == "perto")}
        if len(sujo) >= 2 and len(limpo) >= 2:
            t["custo_s"] = round(statistics.mean(sujo) - statistics.mean(limpo), 3)
        trafego[c] = t

        # paradas: tempo no pit lane e tempo total perdido (volta de entrada + saída contra o ritmo normal)
        pp = []
        normal = None
        lv = [v["ms"] for v in vs if v["n"] > 1 and v["n"] not in box and v["n"] not in sc]
        if len(lv) >= 3:
            normal = statistics.median(lv)
        tel = sorted(D.get("paradas", {}).get(c) or [], key=lambda p: p["volta"])
        trocas = {x["fim"] + 1: (x["pneu"], st[k + 1]["pneu"]) for k, x in enumerate(st[:-1])}
        lista = []
        usadas = set()
        for t_ in tel:
            # o pit lane pode começar na volta de entrada ou já contar a volta seguinte (linha dentro do box)
            v_in = next((v for v in (t_["volta"], t_["volta"] - 1) if v in trocas and v not in usadas), None)
            if v_in is not None:
                usadas.add(v_in)
            lista.append((v_in if v_in is not None else t_["volta"], t_))
        for v_in in trocas:
            if v_in not in usadas:
                lista.append((v_in, None))
        for k, (v_in, t_) in enumerate(sorted(lista, key=lambda z: z[0])):
            v_out = v_in + 1
            ent = next((v for v in vs if v["n"] == v_in), None)
            sai = next((v for v in vs if v["n"] == v_out), None)
            p = {"n": k + 1, "volta": v_in}
            if v_in in trocas:
                p["de"], p["para"] = trocas[v_in]
            if t_:
                p["pit_lane_s"] = round(t_["pit_lane_ms"] / 1000, 2)
                if t_["parado_ms"]:
                    p["parado_s"] = round(t_["parado_ms"] / 1000, 2)
                elif v_in not in trocas:
                    p["drive_through"] = True
            if normal and ent and sai:
                p["perda_s"] = round((ent["ms"] + sai["ms"] - 2 * normal) / 1000, 2)
            pc = D["posicoes"].get(c, {})
            antes, depois = pc.get(v_in - 1), pc.get(v_out)
            if antes and depois:
                p["pos_antes"], p["pos_depois"] = antes, depois
            if v_in in trocas:
                p["duelos"] = _duelos(D, c, v_in)
            pp.append(p)
        if pp:
            paradas[c] = pp
    return {"degradacao": degr, "trafego": trafego, "paradas": paradas,
            "k_comb": K_COMB, "ar_sujo": AR_SUJO, "ar_limpo": AR_LIMPO}


def _duelos(D, c, v_in):
    """Undercut/overcut: rivais que estavam a até 5 s e pararam até 4 voltas antes ou depois.
    Compara a diferença antes das duas paradas com a diferença depois das duas."""
    gaps = D.get("gaps", {})
    out = []
    for r, vs in D["voltas"].items():
        if r == c:
            continue
        st = _stints(D, r)
        for x in st[:-1]:
            r_in = x["fim"] + 1
            if abs(r_in - v_in) > 4:
                continue
            antes = min(v_in, r_in) - 1
            depois = max(v_in, r_in) + 1
            ga, gd = gaps.get(c, {}), gaps.get(r, {})
            if antes not in ga or antes not in gd or depois not in ga or depois not in gd:
                continue
            dif_antes = (ga[antes] - gd[antes]) / 1000     # + = c atrás de r
            dif_depois = (ga[depois] - gd[depois]) / 1000
            if abs(dif_antes) > 5:
                continue
            tipo = "mesma volta" if r_in == v_in else ("undercut" if v_in < r_in else "overcut")
            out.append({"rival": r, "volta_rival": r_in, "tipo": tipo, "antes_s": round(dif_antes, 2),
                        "depois_s": round(dif_depois, 2), "ganho_s": round(dif_antes - dif_depois, 2),
                        "trocou": (dif_antes > 0) != (dif_depois > 0)})
    return out
