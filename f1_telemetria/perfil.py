"""Perfil de pilotagem: como VOCÊ pilota, medido sessão a sessão, e ajustes de setup para esse estilo.

Cada relatório mede a sessão (freada, aceleração, volante, comportamento do carro por tipo de curva,
travamentos e patinação) e soma ao arquivo perfil_piloto.json, que fica só no seu PC.
O perfil é a média das sessões, pesando mais as recentes.
"""
import json
import os
import statistics
import time

import curvas
import dicas

ARQUIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perfil_piloto.json")
MAX_SESSOES = 40
PESO_IDADE = 0.85          # cada sessão mais antiga vale 85% da seguinte
TIPOS = ("lenta", "media", "rapida")
FASES = ("entrada", "meio", "saida")
LENTA, RAPIDA = 120, 200   # km/h na velocidade mínima da curva

# limites do jogo (mínimo, máximo) e passo de cada ajuste sugerido
LIMITES = {"front_wing": (0, 50, 2), "rear_wing": (0, 50, 2), "on_throttle": (10, 100, 10), "off_throttle": (10, 100, 10),
           "front_anti_roll_bar": (1, 21, 2), "rear_anti_roll_bar": (1, 21, 2), "front_suspension": (1, 41, 3),
           "rear_suspension": (1, 41, 3), "brake_bias": (50, 70, 1), "brake_pressure": (80, 100, 2),
           "rear_left_tyre_pressure": (20.5, 26.5, 0.5), "front_left_tyre_pressure": (22.5, 29.5, 0.5)}
NOMES = {"front_wing": "Asa dianteira", "rear_wing": "Asa traseira", "on_throttle": "Diferencial ao acelerar",
         "off_throttle": "Diferencial ao desacelerar", "front_anti_roll_bar": "Barra anti-rolagem dianteira",
         "rear_anti_roll_bar": "Barra anti-rolagem traseira", "front_suspension": "Suspensão dianteira",
         "rear_suspension": "Suspensão traseira", "brake_bias": "Distribuição de freio", "brake_pressure": "Pressão de freio",
         "rear_left_tyre_pressure": "Pressão dos pneus traseiros",
         "front_left_tyre_pressure": "Pressão dos pneus dianteiros"}
# o que cada ajuste faz no F1 26 (direção do efeito), para explicar a sugestão
POR_QUE = {
    ("brake_bias", 1): "mais freio na frente = carro mais estável na freada (dá para mudar durante a corrida)",
    ("brake_bias", -1): "mais freio atrás = menos travada da dianteira e carro gira mais na freada",
    ("off_throttle", 1): "diferencial mais travado sem acelerar = mais estabilidade na entrada",
    ("off_throttle", -1): "diferencial mais solto sem acelerar = carro gira mais na entrada",
    ("on_throttle", 1): "diferencial mais travado ao acelerar = mais tração na saída",
    ("on_throttle", -1): "diferencial mais solto ao acelerar = carro gira mais na saída",
    ("rear_anti_roll_bar", -1): "barra traseira mais macia = mais tração e estabilidade no meio e na saída",
    ("rear_anti_roll_bar", 1): "barra traseira mais dura = carro gira mais no meio da curva",
    ("front_anti_roll_bar", -1): "barra dianteira mais macia = frente gira mais no meio da curva",
    ("front_wing", 1): "mais asa dianteira = mais entrada e rotação (o carro do F1 26 tende a sair de frente)",
    ("rear_wing", 1): "mais asa traseira = traseira mais estável sem precisar de wheel flick; na reta pesa pouco porque a asa abre no modo reta. Quando ficar confiante, tire 5 por vez",
    ("rear_wing", -1): "menos asa traseira = mais velocidade e rotação nas curvas rápidas; tire 5 por vez e pare quando a traseira começar a escapar",
    ("rear_suspension", 1): "traseira mais dura = mais rotação na entrada da curva",
    ("rear_suspension", -1): "traseira mais macia = menos rotação, carro mais calmo na entrada",
    ("front_suspension", -1): "frente mais macia = mais rotação na entrada da curva",
    ("brake_pressure", -1): "menos pressão = menos travada (os pros usam entre 97% e 100%)",
    ("rear_left_tyre_pressure", -1): "pneu traseiro mais vazio = mais área de contato e tração (esquenta mais)",
    ("front_left_tyre_pressure", -1): "pneu dianteiro mais vazio = mais aderência na frente (esquenta mais)",
}
PNEUS = {"rear_left_tyre_pressure": ("rear_left_tyre_pressure", "rear_right_tyre_pressure"),
         "front_left_tyre_pressure": ("front_left_tyre_pressure", "front_right_tyre_pressure")}


def _media(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 3) if xs else None


def metricas_sessao(D, apices):
    """Mede o estilo nas suas voltas válidas desta sessão."""
    M = D["meta"]
    J, passo = M["jogador"], M["passo"]
    voltas = [t for t in D["tracos"] if t["carro"] == J and t["valida"] and not t["pit"]
              and not (M["tipo"] == "corrida" and t["volta"] == 1)]
    if len(voltas) < 2:
        return None
    n = min(len(t["v"]) for t in voltas)
    ref = min(voltas, key=lambda t: t["ms"])
    trs = curvas.trechos(apices, ref["v"], n)
    if not trs:
        return None
    # tipo de cada curva pela velocidade mínima (mediana das voltas)
    tipo = {}
    for c in trs:
        vm = statistics.median(min(t["v"][c["ini"]:c["fim"] + 1]) for t in voltas)
        tipo[c["k"]] = "lenta" if vm < LENTA else "rapida" if vm > RAPIDA else "media"

    pico, trail, soltura, ate_total, rampa, correc_acel, correc_vol, flick = [], [], [], [], [], [], [], []
    for t in voltas:
        for c in trs:
            ini, fim, ap = c["ini"], c["fim"], c["i"]
            if ap >= n or fim >= n:
                continue
            jan = max(ini, ap - round(400 / passo))
            fa = next((k for k in range(jan, ap + 1) if t["freio"][k] > dicas.FREIO_LIGADO), None)
            if fa is not None:
                zona = range(fa, ap + 1)
                pico.append(max(t["freio"][k] for k in zona))
                # freando e virando ao mesmo tempo = trail braking
                trail.append(100 * sum(1 for k in zona if t["freio"][k] > 5 and abs(t["volante"][k]) > 15) / len(zona))
                kp = max(zona, key=lambda k: t["freio"][k])
                kz = next((k for k in range(kp, fim + 1) if t["freio"][k] < 5), None)
                if kz is not None:
                    soltura.append((kz - kp) * passo)
            imin = min(range(ini, fim + 1), key=lambda k: t["v"][k])
            k95 = next((k for k in range(imin, fim + 1) if t["acel"][k] >= dicas.ACEL_TOTAL), None)
            if k95 is not None:
                ate_total.append((k95 - imin) * passo)
                k10 = next((k for k in range(imin, k95 + 1) if t["acel"][k] >= 10), None)
                if k10 is not None and k95 > k10:
                    rampa.append(85 / ((k95 - k10) * passo) * 100)    # % de pedal a cada 100 m
            # tirou o pé de novo depois de já estar acelerando = correção no acelerador
            sub, mx_ = 0, 0
            for k in range(imin, fim + 1):
                a = t["acel"][k]
                if a >= 50:
                    mx_ = max(mx_, a)
                if mx_ >= 50 and a < mx_ - 25:
                    sub += 1
                    mx_ = a
            correc_acel.append(sub)
            # correções de volante: mudanças de sentido do volante dentro da curva
            dv = [t["volante"][k + 1] - t["volante"][k] for k in range(ini, min(fim, n - 1))]
            dv = [d for d in dv if abs(d) >= 3]
            correc_vol.append(sum(1 for a, b in zip(dv, dv[1:]) if (a > 0) != (b > 0)))
            # wheel flick: na entrada das curvas lentas/médias, um golpe de volante bem maior que o ângulo
            # que sobra no ápice (provoca subesterço de propósito para segurar a traseira)
            if tipo[c["k"]] != "rapida":
                vol = [abs(t["volante"][k]) for k in range(ini, ap + 1)]
                if vol:
                    kp = max(range(len(vol)), key=lambda k: vol[k])
                    pico_v, no_ap = vol[kp], vol[-1]
                    flick.append(pico_v >= 25 and pico_v >= 1.6 * max(no_ap, 5) and (len(vol) - 1 - kp) * passo >= 20)

    # comportamento do carro (ângulos de deriva) e rodas (pacote 13)
    fases = {(tp, f): [] for tp in TIPOS for f in FASES}
    trav_d = trav_t = pat = 0
    pat_tipo = {tp: 0 for tp in TIPOS}
    voltas_mx = 0

    def curva_de(i):
        for c in trs:
            if c["ini"] <= i <= c["fim"]:
                return c
        return None

    for t in voltas:
        mx = t.get("mx")
        # gravações antigas não têm o pacote 13 de verdade (vem tudo zerado): sem dado de rodas
        if not mx or not any(abs(x) > 1e-4 for x in mx["af"][::7]):
            continue
        voltas_mx += 1
        ja = set()
        for d, af, ar, tf, tt, p in zip(mx["d"], mx["af"], mx["ar"], mx["trava"], mx["trava_t"], mx["patina"]):
            i = min(n - 1, round(d / passo))
            c = curva_de(i)
            if c is None:
                continue
            tp = tipo[c["k"]]
            if tf < dicas.TRAVA and (c["k"], "d") not in ja:
                trav_d += 1
                ja.add((c["k"], "d"))
            if tt < dicas.TRAVA and (c["k"], "t") not in ja:
                trav_t += 1
                ja.add((c["k"], "t"))
            if p > dicas.PATINA and (c["k"], "p") not in ja:
                pat += 1
                pat_tipo[tp] += 1
                ja.add((c["k"], "p"))
            if t["v"][i] > 300:
                continue
            ap = c["i"]
            acel, freio = t["acel"][i], t["freio"][i]
            if abs(i - ap) * passo <= 40 and acel < 60 and freio < 5:
                fase = "meio"
            elif i < ap and (freio > 5 or acel < 10):
                fase = "entrada"
            elif i > ap and acel >= 30:
                fase = "saida"
            else:
                continue
            fases[(tp, fase)].append(af - ar)
    por10 = lambda x: round(x * 10 / voltas_mx, 2) if voltas_mx else None
    if not voltas_mx:
        fases = {k: [] for k in fases}
    return {
        "voltas": len(voltas), "voltas_rodas": voltas_mx,
        "curvas": {tp: sorted(k for k, v in tipo.items() if v == tp) for tp in TIPOS},
        "freio": {"pico": _media(pico), "trail": _media(trail), "soltura_m": _media(soltura)},
        "acel": {"ate_total_m": _media(ate_total), "rampa": _media(rampa), "correcoes": _media(correc_acel)},
        "volante": {"correcoes": _media(correc_vol), "flick": round(100 * sum(flick) / len(flick), 1) if flick else None},
        "equilibrio": {tp: {f: (_media(fases[(tp, f)]) if len(fases[(tp, f)]) >= 8 else None) for f in FASES} for tp in TIPOS},
        "rodas": {"trava_d": por10(trav_d), "trava_t": por10(trav_t), "patina": por10(pat),
                  "patina_tipo": {tp: por10(v) for tp, v in pat_tipo.items()}},
    }


def _junta(lista, pesos):
    """Média ponderada de dicionários com a mesma forma (ignora None)."""
    dic = [x for x in lista if isinstance(x, dict)]
    if dic:
        chaves = list(dict.fromkeys(k for x in dic for k in x))      # sessões antigas podem não ter as medidas novas
        return {k: _junta([(x or {}).get(k) if isinstance(x, dict) else None for x in lista], pesos) for k in chaves}
    lis = [x for x in lista if isinstance(x, list)]
    if lis:
        return lis[-1]
    par = [(x, p) for x, p in zip(lista, pesos) if isinstance(x, (int, float))]
    if not par:
        return None
    return round(sum(x * p for x, p in par) / sum(p for _, p in par), 3)


def atualizar(D, metr):
    """Guarda a sessão no perfil (a mesma gravação substitui a anterior) e devolve o perfil médio."""
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        dados = {"sessoes": []}
    M = D["meta"]
    chave = os.path.basename(M.get("arquivo") or "")
    sess = [s for s in dados.get("sessoes", []) if s.get("id") != chave]
    sess.append({"id": chave, "ts": M.get("inicio_ts") or time.time(), "quando": M.get("data") or time.strftime("%d/%m/%Y %H:%M"), "pista": M.get("pista"),
                 "tipo": M.get("tipo"), "metricas": metr, "setup": D.get("setup")})
    sess.sort(key=lambda s: s.get("ts") or 0)
    sess = sess[-MAX_SESSOES:]
    dados["sessoes"] = sess
    try:
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
    except OSError:
        pass
    return perfil_medio(sess)


def perfil_medio(sess):
    ms = [s["metricas"] for s in sess if s.get("metricas")]
    if not ms:
        return None
    pesos = [PESO_IDADE ** (len(ms) - 1 - i) * min(1.0, (m.get("voltas") or 1) / 5) for i, m in enumerate(ms)]
    p = _junta(ms, pesos)
    p["sessoes"] = len(ms)
    return p


# ---------------------------------------------------------------- leitura do perfil em palavras
def rotulos(p):
    """Frases curtas sobre o estilo (para o relatório)."""
    if not p:
        return {}
    out = {}
    f, a, v = p.get("freio") or {}, p.get("acel") or {}, p.get("volante") or {}
    if f.get("trail") is not None:
        out["freio"] = ("Solta o freio já virando para a curva (trail braking forte)" if f["trail"] >= 35 else
                        "Freia quase todo em linha reta" if f["trail"] < 15 else "Mistura: parte da freada já virando")
    if a.get("ate_total_m") is not None:
        out["acel"] = ("Acelera cedo e rápido na saída (agressivo)" if a["ate_total_m"] < 90 and (a.get("rampa") or 0) > 120 else
                       "Acelera de forma progressiva e tardia" if a["ate_total_m"] > 160 else "Retomada equilibrada")
    if v.get("correcoes") is not None:
        out["volante"] = ("Muitas correções de volante dentro da curva" if v["correcoes"] >= 1.5 else
                          "Volante suave, poucas correções" if v["correcoes"] < 0.6 else "Algumas correções de volante")
        if v.get("flick") is not None and v["flick"] >= 30:
            out["volante"] += "; usa wheel flick na entrada"
    return out


def _estado(eq, fase, tipo):
    x = ((eq or {}).get(tipo) or {}).get(fase)
    if x is None:
        return None, 0
    if fase == "meio" and x > dicas.SUB_MEIO:
        return "sub", x - dicas.SUB_MEIO
    if -x > dicas.SOBRE:
        return "sobre", -x - dicas.SOBRE
    return "ok", 0


def equilibrio_rotulado(p):
    eq = (p or {}).get("equilibrio") or {}
    return {tp: {f: _estado(eq, f, tp)[0] for f in FASES} for tp in TIPOS}


# ---------------------------------------------------------------- ajustes de setup para o estilo
def sugestoes(p, setup, faixas=None):
    """Até 4 ajustes a partir do setup atual. faixas: {campo: (min, max)} do que os profissionais usam."""
    if not p or not setup:
        return []
    eq = p.get("equilibrio") or {}
    rodas = p.get("rodas") or {}
    rot = rotulos(p)
    problemas = []   # (gravidade, título, explicação, [(campo, sentido)])
    for tp in ("lenta", "media"):
        e, g = _estado(eq, "entrada", tp)
        if e == "sobre":
            extra = " Como você solta o freio já virando, a traseira fica leve na entrada." if (p.get("freio") or {}).get("trail", 0) >= 35 else ""
            problemas.append((g * 100, f"Traseira solta na entrada das curvas {'lentas' if tp == 'lenta' else 'médias'}", "O carro gira demais na freada." + extra,
                              [("brake_bias", 1), ("off_throttle", 1)]))
        e, g = _estado(eq, "saida", tp)
        if e == "sobre":
            extra = " Você acelera cedo e forte, o que pede mais tração." if "agressivo" in rot.get("acel", "") else ""
            problemas.append((g * 100, f"Traseira solta na saída das curvas {'lentas' if tp == 'lenta' else 'médias'}", "A traseira escorrega ao acelerar." + extra,
                              [("rear_anti_roll_bar", -1), ("on_throttle", 1), ("rear_left_tyre_pressure", -1)]))
        x = ((eq.get(tp) or {}).get("entrada"))
        if x is not None and x > dicas.SUB_MEIO:
            problemas.append(((x - dicas.SUB_MEIO) * 60, f"Demora a virar na entrada das curvas {'lentas' if tp == 'lenta' else 'médias'}",
                              "A frente não responde no começo da curva.", [("rear_suspension", 1), ("front_suspension", -1), ("front_wing", 1)]))
        e, g = _estado(eq, "meio", tp)
        if e == "sub":
            problemas.append((g * 60, f"Sai de frente no meio das curvas {'lentas' if tp == 'lenta' else 'médias'}", "A frente escorrega mais que a traseira.",
                              [("front_wing", 1), ("front_anti_roll_bar", -1), ("rear_anti_roll_bar", 1)]))
    e, g = _estado(eq, "meio", "rapida")
    if e == "sub":
        problemas.append((g * 60, "Sai de frente nas curvas rápidas", "Falta aderência na frente em alta velocidade.", [("front_wing", 1)]))
    elif e == "sobre":
        problemas.append((g * 100, "Traseira instável nas curvas rápidas", "A traseira escorrega em alta velocidade.", [("rear_wing", 1), ("rear_anti_roll_bar", -1)]))
    if (rodas.get("trava_d") or 0) >= 3:
        problemas.append((rodas["trava_d"] / 3, "Trava a dianteira na freada", f"Cerca de {rodas['trava_d']:.0f} travadas da frente a cada 10 voltas.",
                          [("brake_bias", -1), ("brake_pressure", -1)]))
    if (rodas.get("trava_t") or 0) >= 3:
        problemas.append((rodas["trava_t"] / 3, "Trava a traseira na freada", f"Cerca de {rodas['trava_t']:.0f} travadas de trás a cada 10 voltas.",
                          [("brake_bias", 1), ("off_throttle", 1)]))
    if (rodas.get("patina") or 0) >= 5 and not any("saída" in x[1] for x in problemas):
        problemas.append((rodas["patina"] / 5, "Patina na saída das curvas", f"Cerca de {rodas['patina']:.0f} patinadas a cada 10 voltas.",
                          [("rear_anti_roll_bar", -1), ("on_throttle", 1), ("rear_left_tyre_pressure", -1)]))
    # asa traseira: os setups esports (asa traseira bem baixa) pedem wheel flick na entrada.
    # Sem flick e com o carro nervoso, mais asa traseira estabiliza; quando o carro está calmo, tirar aos poucos
    vol = p.get("volante") or {}
    sem_flick = (vol.get("flick") or 0) < 20
    nervoso = any(_estado(eq, f, tp)[0] == "sobre" for tp in ("lenta", "media") for f in ("entrada", "meio")) \
        or (vol.get("correcoes") or 0) >= 1.5 or (((rodas.get("patina_tipo") or {}).get("lenta")) or 0) >= 15
    calmo = all(_estado(eq, f, tp)[0] in ("ok", None) for tp in TIPOS for f in FASES) \
        and (vol.get("correcoes") or 9) < 1.0 and (rodas.get("patina") or 0) < 8
    if nervoso and sem_flick:
        problemas.append((1.5, "Traseira nervosa nas curvas lentas e médias",
                          "Os setups esports usam pouca asa traseira e contam com o wheel flick na entrada, que você quase não usa.",
                          [("rear_wing", 1, 5, "livre")]))
    elif calmo:
        problemas.append((0.5, "Carro calmo: dá para ganhar velocidade",
                          "Traseira estável e poucas correções: tire asa traseira aos poucos até o carro começar a escapar.",
                          [("rear_wing", -1, 5)]))
    problemas.sort(key=lambda x: -x[0])
    out, usados = [], set()
    for g, titulo, expl, alavancas in problemas:
        for alav in alavancas:
            campo, sentido = alav[0], alav[1]
            if campo in usados or campo not in LIMITES or not isinstance(setup.get(campo), (int, float)):
                continue
            lo, hi, passo = LIMITES[campo]
            if len(alav) > 2:
                passo = alav[2]
            fx = (faixas or {}).get(campo)
            livre = len(alav) > 3 and alav[3] == "livre"     # o vídeo manda passar do que os pros usam (eles fazem flick)
            if fx and livre:
                fx = None
            if fx:
                lo, hi = max(lo, fx[0]), min(hi, fx[1])
            atual = setup[campo]
            novo = round(min(hi, max(lo, atual + sentido * passo)), 2)
            if (sentido > 0 and atual >= hi) or (sentido < 0 and atual <= lo) or novo == atual:
                continue
            out.append({"problema": titulo, "explicacao": expl, "campo": campo, "nome": NOMES[campo], "de": atual, "para": novo,
                        "na_faixa": bool(fx), "por_que": POR_QUE.get((campo, sentido), "")})
            usados.add(campo)
            break
        else:
            out.append({"problema": titulo, "explicacao": expl, "campo": None,
                        "nota": "Os ajustes que ajudariam já estão no limite" + (" do que os profissionais usam" if faixas else "") + ": compense na pilotagem."})
        if len(out) >= 4:
            break
    return out


# faixas gerais do meta do F1 26 (o que os setups esports usam em todas as pistas, no seco).
# Não é o setup de nenhuma pista: só o intervalo de valores, para as sugestões não saírem do meta.
META_GERAL = {"on_throttle": (90, 100), "off_throttle": (50, 100), "brake_bias": (54, 58), "brake_pressure": (97, 100),
              "front_anti_roll_bar": (1, 8), "rear_anti_roll_bar": (3, 21), "front_suspension": (34, 41), "rear_suspension": (30, 41),
              "front_left_tyre_pressure": (22.5, 29.5), "rear_left_tyre_pressure": (20.5, 26.5)}


def faixas_ref(ref):
    """Mínimo e máximo de cada ajuste entre os setups de referência da pista (seco); sem referência, o meta geral."""
    setups = [x for x in ((ref or {}).get("setups") or []) if x.get("clima", "seco") == "seco" and "Safe" not in x.get("nome", "")]
    if not setups:
        return dict(META_GERAL)
    fx = {}
    for campo in LIMITES:
        vs = [s[campo] for s in setups if isinstance(s.get(campo), (int, float))]
        if vs:
            fx[campo] = (min(vs), max(vs))
    # o vídeo de referência mostra pros usando 97–100% de pressão de freio
    if "brake_pressure" in fx:
        fx["brake_pressure"] = (min(97, fx["brake_pressure"][0]), fx["brake_pressure"][1])
    return fx or None


def montar(D, apices):
    """Tudo o que o relatório mostra na aba 'Seu estilo'."""
    metr = metricas_sessao(D, apices)
    if not metr:
        return None
    perfil = atualizar(D, metr)
    fx = faixas_ref(D.get("setup_ref"))
    return {"sessao": metr, "perfil": perfil, "rotulos": rotulos(perfil), "rotulos_sessao": rotulos(metr),
            "equilibrio": equilibrio_rotulado(perfil), "equilibrio_sessao": equilibrio_rotulado(metr),
            "sugestoes": sugestoes(perfil, D.get("setup"), fx), "com_faixas": bool(fx),
            "faixa_pista": bool(D.get("setup_ref"))}
