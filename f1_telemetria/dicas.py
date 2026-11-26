"""
Resumos da sessão:
  - "Seu resumo": dicas de pilotagem e de acerto comparando a sua melhor volta com a mais rápida da sessão.
  - "Resumo da sessão": rankings de todos os pilotos.

Tudo aqui é estimativa a partir da telemetria; os limiares ficam no topo para ajuste fino.
"""

import statistics

import curvas

# ---------------------------------------------------------------- limiares (ajustáveis)
FREIO_LIGADO = 10          # % de freio que conta como início da freada
CARGA_VOLANTE = 8          # volante (×100) acima disso = em curva (conta para a temperatura do pneu)
CARGA_FREIO = 20           # % de freio acima disso = freando (idem)
ADER_MIN = 98.0            # pneu só é "frio" se a aderência média cair abaixo disso (o jogo ainda mostra verde acima)
ACEL_TOTAL = 95            # % de acelerador que conta como "acelerador total"
DIF_FREADA_M = 10          # diferença mínima de ponto de freada para comentar (m)
DIF_ACEL_M = 15            # diferença mínima de retomada para comentar (m)
PERDA_MIN_S = 0.02         # perda mínima na curva para comentar (s)
TRAVA = -0.15              # deslizamento da roda abaixo disso = travando (pacote 13)
PATINA = 0.12              # deslizamento das traseiras acima disso = patinando
SUB_MEIO = 0.07            # deriva dianteira − traseira (rad) acima disso no meio da curva = subesterço
SOBRE = 0.015              # deriva traseira − dianteira (rad) acima disso = sobreesterço
BATERIA_SOBRANDO = 15      # % de bateria no fim da volta que indica energia sem uso

# Pressões máximas de acerto (PSI), como no F1 25/26
PRESSAO_MAX = {"diant": 29.5, "tras": 26.5}

# Aderência (%) por temperatura da superfície (°C), tabela enviada pelo usuário
TEMPS = [25, 35, 45, 55, 65, 75, 85, 95, 105, 115, 125, 135, 145, 155, 165, 175]
ADERENCIA = {
    "C1": [92.65, 93.20, 93.85, 94.85, 96.20, 97.50, 99.00, 100, 100, 99.85, 99.30, 98.65, 98.00, 97.40, 96.90, 96.50],
    "C2": [92.60, 93.20, 94.15, 95.33, 97.00, 98.50, 99.60, 100, 99.80, 99.40, 98.80, 98.15, 97.55, 96.95, 96.43, 96.15],
    "C3": [92.30, 93.10, 94.40, 95.70, 97.50, 99.25, 100, 100, 99.65, 99.10, 98.50, 97.88, 97.27, 96.63, 96.10, 95.80],
    "C4": [92.50, 93.50, 95.00, 97.00, 98.75, 99.85, 100, 99.84, 99.30, 98.70, 98.10, 97.50, 96.89, 96.25, 95.75, 95.45],
    "C5": [92.50, 93.70, 95.50, 97.50, 99.20, 100, 100, 99.60, 99.00, 98.35, 97.75, 97.10, 96.40, 95.85, 95.40, 95.10],
    "Inter": [97.20, 98.02, 98.90, 99.70, 100, 100, 99.60, 99.10, 98.50, 97.90, 97.20, 96.60, 96.00, 95.50, 95.05, 94.80],
    "Chuva": [97.80, 98.50, 99.40, 99.90, 100, 99.70, 99.30, 98.80, 98.20, 97.50, 96.80, 96.20, 95.60, 95.10, 94.70, 94.40],
}
# composto real do jogo -> tabela (C0 usa C1, C6 usa C5)
COMPOSTO = {16: "C5", 17: "C4", 18: "C3", 19: "C2", 20: "C1", 21: "C1", 22: "C5", 7: "Inter", 8: "Chuva"}
RODAS = ["traseiro esquerdo", "traseiro direito", "dianteiro esquerdo", "dianteiro direito"]
RODAS_C = ["TE", "TD", "DE", "DD"]


def aderencia(comp, temp):
    tab = ADERENCIA[comp]
    if temp <= TEMPS[0]:
        return tab[0]
    if temp >= TEMPS[-1]:
        return tab[-1]
    for i in range(len(TEMPS) - 1):
        if TEMPS[i] <= temp <= TEMPS[i + 1]:
            f = (temp - TEMPS[i]) / (TEMPS[i + 1] - TEMPS[i])
            return tab[i] + (tab[i + 1] - tab[i]) * f


def janela(comp, minimo=99.5):
    """Faixa de temperatura com aderência >= mínimo (de 1 em 1 °C) e a faixa de 100%."""
    ok = [t for t in range(25, 176) if aderencia(comp, t) >= minimo]
    cem = [t for t in TEMPS if ADERENCIA[comp][TEMPS.index(t)] >= 100]
    return (ok[0], ok[-1]), (cem[0], cem[-1])


def _fmt_s(s):
    return f"{s:+.3f} s".replace("-", "−")


def _nome_curva(k):
    return f"curva {k}"


# ---------------------------------------------------------------- seu resumo
def seu_resumo(D, apices_idx, A_esc=None, B_esc=None):
    M = D["meta"]
    J = M["jogador"]
    passo = M["passo"]
    nome = lambda c: D["pilotos"].get(c, {}).get("nome", f"Carro {c + 1}")
    meus = [t for t in D["tracos"] if t["carro"] == J]
    meus_validos = sorted([t for t in meus if t["valida"] and not t["pit"]], key=lambda t: t["ms"])
    if not meus_validos:
        return {"aviso": "Sem volta válida completa sua nesta sessão para analisar."}
    A = A_esc or meus_validos[0]
    rivais = sorted([t for t in D["tracos"] if t["carro"] != J and t["valida"]], key=lambda t: t["ms"])
    B = B_esc or (rivais[0] if rivais else (meus_validos[1] if len(meus_validos) > 1 else None))
    out = {"volta": A["volta"], "ms": A["ms"], "itens": []}
    itens = out["itens"]

    def add(tema, texto, nivel="atencao", curva=None, perda=None):
        itens.append({"tema": tema, "texto": texto, "nivel": nivel, "curva": curva, "perda": perda})

    n = min(len(A["v"]), len(B["v"])) if B else len(A["v"])
    trs = curvas.trechos(apices_idx, (B or A)["v"], n)

    def curva_de(i):
        for c in trs:
            if c["ini"] <= i <= c["fim"]:
                return c["k"]
        return None

    # ------------------------------------------- freadas, retomada, velocidade mínima vs a referência
    if B:
        out["ref"] = {"carro": B["carro"], "nome": nome(B["carro"]) if B["carro"] != J else "sua outra volta",
                      "volta": B["volta"], "ms": B["ms"]}
        ref_nome = nome(B["carro"]) if B["carro"] != J else "na sua 2ª melhor volta"
        achados = []
        for c in trs:
            ini, fim, ap = c["ini"], c["fim"], c["i"]
            dt = ((A["t"][fim] - B["t"][fim]) - (A["t"][ini] - B["t"][ini])) / 1000
            jan = max(ini, ap - round(500 / passo))
            fa = next((k for k in range(jan, ap + 1) if A["freio"][k] > FREIO_LIGADO), None)
            fb = next((k for k in range(jan, ap + 1) if B["freio"][k] > FREIO_LIGADO), None)
            ia = min(range(ini, fim + 1), key=lambda k: A["v"][k])
            ib = min(range(ini, fim + 1), key=lambda k: B["v"][k])
            minA, minB = A["v"][ia], B["v"][ib]
            pa = next((k for k in range(ia, fim + 1) if A["acel"][k] >= ACEL_TOTAL), None)
            pb = next((k for k in range(ib, fim + 1) if B["acel"][k] >= ACEL_TOTAL), None)
            if dt < PERDA_MIN_S:
                continue
            motivos = []
            if fa is not None and fb is not None:
                dm = (fa - fb) * passo
                if dm <= -DIF_FREADA_M and minA <= minB + 3:
                    motivos.append(f"freia {-dm} m antes que {ref_nome}")
                elif dm >= DIF_FREADA_M and minA < minB - 3:
                    motivos.append(f"freia {dm} m depois, mas passa mais lento no meio ({minA} contra {minB} km/h): "
                                   "a freada tardia está custando a velocidade de contorno")
            elif fa is not None and fb is None:
                motivos.append(f"freia e {ref_nome} não freia")
            if minA < minB - 5 and not any("mais lento" in m for m in motivos):
                motivos.append(f"leva {minB - minA} km/h a menos no meio da curva ({minA} contra {minB})")
            if pa is not None and pb is not None and (pa - pb) * passo >= DIF_ACEL_M:
                motivos.append(f"volta ao acelerador total {(pa - pb) * passo} m depois")
            if motivos:
                achados.append((dt, c["k"], motivos))
        achados.sort(reverse=True)
        for dt, k, motivos in achados[:6]:
            add("Pilotagem", f"Curva {k} ({_fmt_s(dt)}): você " + "; ".join(motivos) + ".", curva=k, perda=round(dt, 3))
        if not achados:
            add("Pilotagem", f"Nenhuma curva com perda clara para {ref_nome} nas freadas e retomadas.", "bom")

    # ------------------------------------------- travamentos e patinação (todas as suas voltas cronometradas)
    trav, pat = {}, {}
    amostras_mx = 0
    for t in meus:
        mx = t.get("mx")
        if not mx:
            continue
        amostras_mx += len(mx["d"])
        for d, tf, tt, p in zip(mx["d"], mx["trava"], mx["trava_t"], mx["patina"]):
            k = curva_de(min(n - 1, round(d / passo)))
            if k is None:
                continue
            if tf < TRAVA:
                trav.setdefault(k, set()).add((t["volta"], "dianteira"))
            if tt < TRAVA:
                trav.setdefault(k, set()).add((t["volta"], "traseira"))
            if p > PATINA:
                pat.setdefault(k, set()).add(t["volta"])
    voltas_mx = sum(1 for t in meus if t.get("mx"))
    if voltas_mx:
        poucos = amostras_mx / max(1, voltas_mx) < 1500
        nota = " (gravação com poucos pontos das rodas: podem ter escapado travamentos rápidos)" if poucos else ""
        if trav:
            lst = sorted(trav.items(), key=lambda x: -len(x[1]))
            partes = []
            for k, ev in lst[:5]:
                rodas = sorted({r for _, r in ev})
                partes.append(f"curva {k} ({len({v for v, _ in ev})} volta(s), roda {' e '.join(rodas)})")
            add("Travamentos", "Travamentos de roda na freada: " + "; ".join(partes) +
                ". Solte um pouco o freio no fim da freada ou mova o balanço de freio" +
                (" para trás" if any(r == "dianteira" for _, ev in lst for _, r in ev) else " para frente") + "." + nota)
        else:
            add("Travamentos", "Nenhum travamento de roda detectado nas suas voltas." + nota, "bom")
        if pat:
            lst = sorted(pat.items(), key=lambda x: -len(x[1]))
            add("Tração", "As traseiras patinam na saída de: " +
                ", ".join(f"curva {k} ({len(v)} volta(s))" for k, v in lst[:6]) +
                ". Acelere de forma mais progressiva nessas saídas; no acerto, barra traseira mais macia ou pneus traseiros um pouco mais vazios dão mais tração.")

    # ------------------------------------------- equilíbrio (sub/sobreesterço) por fase da curva
    fases = {}
    for t in meus_validos:
        mx = t.get("mx")
        if not mx:
            continue
        for d, af, ar in zip(mx["d"], mx["af"], mx["ar"]):
            i = min(n - 1, round(d / passo))
            k = curva_de(i)
            if k is None or t["v"][i] > 250:
                continue
            ap = trs[k - 1]["i"]
            acel, freio = t["acel"][i], t["freio"][i]
            if abs(i - ap) * passo <= 40 and acel < 60 and freio < 5:
                fase = "meio"
            elif i < ap and (freio > 5 or acel < 10):
                fase = "entrada"
            elif i > ap and acel >= 30:
                fase = "saida"
            else:
                continue
            fases.setdefault((k, fase), []).append(af - ar)
    sub, sob_ent, sob_sai = [], [], []
    for (k, fase), vals in fases.items():
        if len(vals) < 2:
            continue
        m = statistics.mean(vals)
        if fase == "meio" and m > SUB_MEIO:
            sub.append(k)
        elif fase == "entrada" and -m > SOBRE:
            sob_ent.append(k)
        elif fase == "saida" and -m > SOBRE:
            sob_sai.append(k)
    st = D.get("setup") or {}
    # limites do acerto no jogo: (mínimo, máximo)
    LIM = {"front_wing": (0, 50), "rear_wing": (0, 50), "front_anti_roll_bar": (1, 21), "rear_anti_roll_bar": (1, 21),
           "front_camber": (-3.5, -2.5), "on_throttle": (10, 100), "off_throttle": (10, 100), "brake_bias": (50, 70)}

    def opc(campo, sentido, texto):
        """Sugestão de acerto, só se ainda dá para mexer nesse sentido (+1 aumenta, −1 diminui)."""
        v = st.get(campo)
        if isinstance(v, (int, float)) and campo in LIM:
            lo, hi = LIM[campo]
            if (sentido > 0 and v >= hi - 1e-6) or (sentido < 0 and v <= lo + 1e-6):
                return None
            return f"{texto} (hoje: {v:g})"
        return texto

    def sugestoes(*xs):
        xs = [x for x in xs if x]
        if not xs:
            return " Os ajustes de acerto que ajudariam já estão no limite: compense na pilotagem."
        return " No acerto: " + (", ".join(xs[:-1]) + " ou " + xs[-1] if len(xs) > 1 else xs[0]) + "."

    def lista_curvas(ks):
        ks = sorted(ks)
        return ("na curva " if len(ks) == 1 else "nas curvas ") + ", ".join(map(str, ks))

    if fases:
        if sub:
            add("Equilíbrio", f"Subesterço no meio {lista_curvas(sub).replace('na ', 'da ', 1).replace('nas ', 'das ', 1)}: a frente escorrega mais que a traseira." +
                sugestoes(opc("front_wing", 1, "+1 ou +2 na asa dianteira"), opc("front_anti_roll_bar", -1, "barra estabilizadora dianteira mais macia"),
                          opc("front_camber", -1, "mais cambagem negativa na frente")))
        if sob_sai:
            add("Equilíbrio", f"Sobreesterço na saída {lista_curvas(sob_sai).replace('na ', 'da ', 1).replace('nas ', 'das ', 1)}: a traseira escorrega ao acelerar." +
                sugestoes(opc("rear_anti_roll_bar", -1, "barra traseira mais macia"), opc("on_throttle", 1, "diferencial ao acelerar (on-throttle) mais alto, para mais tração"),
                          opc("rear_wing", 1, "+1 na asa traseira")))
        if sob_ent:
            add("Equilíbrio", f"Sobreesterço na entrada {lista_curvas(sob_ent).replace('na ', 'da ', 1).replace('nas ', 'das ', 1)}: a traseira solta na freada." +
                sugestoes(opc("brake_bias", 1, "balanço de freio mais para a frente"), opc("off_throttle", 1, "diferencial sem acelerar (off-throttle) mais alto")))
        if not (sub or sob_sai or sob_ent):
            add("Equilíbrio", "Carro equilibrado: nenhuma curva com sub ou sobreesterço claro.", "bom")
        itens[-1]["nota"] = "Estimativa pelos ângulos de deriva das rodas (pacote 13), só do seu carro."

    # ------------------------------------------- bateria
    if A.get("bat"):
        fim_bat = A["bat"][-1]
        ini_bat = A["bat"][0]
        if fim_bat >= BATERIA_SOBRANDO and M["tipo"] != "corrida":
            add("Bateria", f"Você terminou a volta com {fim_bat}% de bateria (começou com {ini_bat}%). "
                "Na classificação essa energia sobra: dá para usar mais nas retas.")
        zero = next((i for i, b in enumerate(A["bat"]) if b <= 2 and A["acel"][i] >= ACEL_TOTAL), None)
        if zero is not None:
            fim_reta = next((i for i in range(zero, n) if A["freio"][i] > FREIO_LIGADO), n - 1)
            if (fim_reta - zero) * passo >= 150:
                k = curva_de(fim_reta)
                txt = f"A bateria zera a {zero * passo} m da volta e você faz {(fim_reta - zero) * passo} m de reta sem energia até a curva {k}."
                if B and B.get("bat") and B["bat"][zero] > 10:
                    txt += f" Nesse ponto {out['ref']['nome']} ainda tem {B['bat'][zero]}%."
                add("Bateria", txt + " Economize um pouco antes (modo médio em trechos curtos) para chegar ao fim das retas longas com energia.")
        if B and A.get("modo") and B.get("modo"):
            trechos_boost = []
            i = 0
            while i < n:
                if B["modo"][i] == 3 and A["modo"][i] < 3 and A["acel"][i] >= ACEL_TOTAL:
                    j = i
                    while j < n and B["modo"][j] == 3 and A["modo"][j] < 3:
                        j += 1
                    if (j - i) * passo >= 120:
                        trechos_boost.append((i, j))
                    i = j
                else:
                    i += 1
            for i, j in trechos_boost[:3]:
                k = curva_de(min(n - 1, j + round(100 / passo)))
                add("Bateria", f"Entre {i * passo} e {j * passo} m (antes da curva {k}) {out['ref']['nome']} usa boost e você não, por {(j - i) * passo} m.")
        # chegada na linha: velocidade, bateria e onde ligou o boost (trecho antes da linha)
        pa, pb = A.get("pre"), (B or {}).get("pre")
        if pa:
            ib_a = next((i for i, m in enumerate(pa["modo"]) if m == 3), None)
            txt = (f"Você cruzou a linha a {A['v'][0]} km/h com {A['bat'][0]}% de bateria"
                   + (f", com o boost ligado {'desde mais de ' if ib_a == 0 else ''}{-pa['d'][ib_a]} m antes" if ib_a is not None else ", sem boost antes da linha"))
            if pb:
                ib_b = next((i for i, m in enumerate(pb["modo"]) if m == 3), None)
                txt += (f"; {out['ref']['nome']} cruzou a {B['v'][0]} km/h com {B['bat'][0]}%"
                        + (f" (boost {'desde mais de ' if ib_b == 0 else ''}{-pb['d'][ib_b]} m antes)" if ib_b is not None else " (sem boost antes)"))
            nivel = "atencao" if (pb and A["v"][0] < B["v"][0] - 3) else "bom"
            if ib_a is not None:
                txt += f". Do momento em que ligou até a linha você gastou {pa['bat'][ib_a] - A['bat'][0]}% da bateria"
            add("Bateria", txt + ".", nivel)
        if not any(x["tema"] == "Bateria" for x in itens):
            add("Bateria", "Uso de bateria sem desperdício aparente nesta volta.", "bom")

    # ------------------------------------------- pneus: temperatura x janela ideal, por composto, em todas as voltas
    comp_volta = {v["n"]: COMPOSTO.get(v.get("pneu_real")) for v in D["jogador_voltas"]}
    pit_volta = {v["n"]: bool(v.get("pit")) for v in D["jogador_voltas"]}
    com_temp = [t for t in meus if t.get("temp_n") and t.get("temp") and comp_volta.get(t["volta"])]
    # janela de aderência pela temperatura do NÚCLEO (carcaça): é o número de cima na tela de pneus do jogo e
    # o que define a aderência. Ele muda devagar, então conta a volta inteira. A superfície (número do meio na
    # tela) pula a cada curva e reta; fica só como linha de apoio, medida nas curvas e freadas.
    def carga(t):
        vol, fr = t.get("volante"), t.get("freio")
        if not vol or not fr:
            return list(range(len(t["temp"][0])))
        idx = [i for i in range(min(len(vol), len(fr), len(t["temp"][0]))) if abs(vol[i]) > CARGA_VOLANTE or fr[i] > CARGA_FREIO]
        return idx or list(range(len(t["temp"][0])))
    pts = {}                                   # volta -> roda -> [(índice, temperatura do núcleo)]
    sup = {}                                   # volta -> roda -> média da superfície em curva/freada
    for t in com_temp:
        pts[t["volta"]] = [list(enumerate(t["temp_n"][r])) for r in range(4)]
        idx = carga(t)
        sup[t["volta"]] = [round(statistics.mean(t["temp"][r][i] for i in idx)) for r in range(4)]
    out["pneus_base"] = "nucleo"
    out["pneus_voltas"] = [{"n": t["volta"], "comp": comp_volta[t["volta"]], "pit": pit_volta.get(t["volta"], False),
                            "media": [round(statistics.mean(x for _, x in pts[t["volta"]][r])) for r in range(4)],
                            "min": [min(x for _, x in pts[t["volta"]][r]) for r in range(4)],
                            "max": [max(t["temp_n"][r]) for r in range(4)],
                            "sup": sup[t["volta"]]}
                           for t in sorted(com_temp, key=lambda t: t["volta"])]
    grupos = {}
    for t in com_temp:
        if pit_volta.get(t["volta"]) or (M["tipo"] == "corrida" and t["volta"] == 1):
            continue                      # volta de box e largada distorcem a temperatura
        grupos.setdefault(comp_volta[t["volta"]], []).append(t)
    ordem_c = []
    for t in sorted(com_temp, key=lambda t: t["volta"]):
        c_ = comp_volta[t["volta"]]
        if c_ in grupos and c_ not in ordem_c:
            ordem_c.append(c_)
    out["pneus_comp"] = []
    PRESSAO_MIN = {"diant": 22.5, "tras": 20.5}
    campos_p = ["rear_left_tyre_pressure", "rear_right_tyre_pressure", "front_left_tyre_pressure", "front_right_tyre_pressure"]
    for comp in ordem_c:
        laps = grupos[comp]
        (jmin, jmax), (cmin, cmax) = janela(comp)
        vis = next((v.get("pneu_visual") for v in D["jogador_voltas"] if v["n"] == laps[0]["volta"]), None)
        g = {"composto": comp, "visual": vis, "janela": [jmin, jmax], "ideal": [cmin, cmax], "voltas": [t["volta"] for t in laps], "rodas": []}
        quentes, frios, frescos = [], [], []
        for r in range(4):
            todas = [x for t in laps for _, x in pts[t["volta"]][r]]
            if not todas:
                continue
            tmax, vmax_, imax = max((x, t["volta"], i) for t in laps for i, x in enumerate(t["temp_n"][r]))
            tmin = min(todas)
            abaixo = sum(1 for x in todas if x < jmin) / len(todas) * 100
            dentro = sum(1 for x in todas if jmin <= x <= jmax) / len(todas) * 100
            acima = sum(1 for x in todas if x > jmax) / len(todas) * 100
            # onde fica mais frio (média por curva)
            por_curva = {}
            for t in laps:
                for i, x in pts[t["volta"]][r]:
                    k = curva_de(min(i, n - 1))
                    if k:
                        por_curva.setdefault(k, []).append(x)
            k_frio = min(por_curva, key=lambda k: statistics.mean(por_curva[k])) if por_curva else None
            ader = statistics.mean(aderencia(comp, x) for x in todas)
            g["rodas"].append({"roda": RODAS_C[r], "media": round(statistics.mean(todas)), "min": tmin, "max": tmax,
                               "volta_max": vmax_, "curva_max": curva_de(min(imax, n - 1)), "curva_fria": k_frio,
                               "abaixo": round(abaixo), "dentro": round(dentro), "acima": round(acima),
                               "abertura": laps[0]["temp_n"][r][0] if M["tipo"] != "corrida" else None,
                               "sup_media": round(statistics.mean(sup[t["volta"]][r] for t in laps)),
                               "aderencia_media": round(ader, 2), "frio": abaixo >= 30 and ader < ADER_MIN,
                               })
            if acima >= 20:
                quentes.append((acima, r, tmax, curva_de(min(imax, n - 1))))
            if abaixo >= 30 and ader < ADER_MIN:      # frio só quando a perda de aderência é relevante
                frios.append((abaixo, r, round(statistics.mean(todas)), k_frio))
            elif abaixo >= 30:
                frescos.append((r, round(ader, 1)))
        out["pneus_comp"].append(g)
        nome_c = f"{comp} ({len(laps)} volta{'s' if len(laps) > 1 else ''})"
        for acima, r, tmax, k in sorted(quentes, reverse=True):
            diant = r >= 2
            p = st.get(campos_p[r])
            pmax = PRESSAO_MAX["diant" if diant else "tras"]
            base = f"{nome_c}: pneu {RODAS[r]} superaquece, {round(acima)}% do tempo acima de {jmax} °C (máx. {tmax} °C na curva {k})."
            if p and p < pmax - 0.05:
                add("Pneus", base + f" Aumente a pressão (está em {p:g} PSI; máximo {pmax:g}).")
            elif p:
                add("Pneus", base + f" A pressão já está no máximo ({p:g} PSI): o ponto mais quente é a curva {k}; alivie o pneu ali.")
            else:
                add("Pneus", base)
        if frios:
            tras = [x for x in frios if x[1] < 2]
            ideal_txt = f"{cmin} °C" if cmin == cmax else f"{cmin}–{cmax} °C"
            kfr = statistics.mode([k for *_, k in frios if k]) if any(k for *_, k in frios) else None
            if len(frios) == 4:
                meds = [m for _, _, m, _ in frios]
                abx = [round(a_) for a_, *_ in frios]
                txt = (f"{nome_c}: os 4 pneus ficaram frios — média de {min(meds)} a {max(meds)} °C (ideal {ideal_txt}), "
                       f"{min(abx)}–{max(abx)}% do tempo abaixo de {jmin} °C")
            else:
                txt = f"{nome_c}: pneus frios — " + "; ".join(
                    f"{RODAS[r]} com média de {med} °C, {round(a_)}% do tempo abaixo de {jmin} °C" for a_, r, med, _ in sorted(frios, reverse=True))
            txt += (f"; o ponto mais frio é a curva {kfr}." if kfr else ".")
            if tras:
                txt += " Traseiros frios tiram tração na saída das curvas."
            baixar = [RODAS_C[r] for _, r, _, _ in frios if st.get(campos_p[r]) and st[campos_p[r]] > PRESSAO_MIN["diant" if r >= 2 else "tras"] + 0.05]
            if baixar:
                txt += f" Pela mesma regra do superaquecimento, diminua a pressão em {'/'.join(sorted(baixar, key=RODAS_C.index))}."
            txt += " Na pilotagem: freadas fortes e acelerações firmes aquecem os pneus."
            add("Pneus", txt)
        if not quentes and not frios:
            if frescos:
                pior = min(a_ for _, a_ in frescos)
                add("Pneus", f"{nome_c}: {'/'.join(RODAS_C[r] for r, _ in frescos)} um pouco abaixo da janela, mas com aderência média de "
                    f"{str(pior).replace('.', ',')}% ou mais: perda pequena, não precisa mexer.", "bom")
            else:
                add("Pneus", f"{nome_c}: temperatura dentro da janela ideal na maior parte do tempo.", "bom")
    # classificação: temperatura na abertura da sua melhor volta
    comp = comp_volta.get(A["volta"])
    if comp and A.get("temp_n") and M["tipo"] != "corrida":
        (jmin, jmax), (cmin, cmax) = janela(comp)
        ab = [A["temp_n"][r][0] for r in range(4)]
        frios_ab = [RODAS_C[r] for r in range(4) if ab[r] < cmin]
        quentes_ab = [RODAS_C[r] for r in range(4) if ab[r] > cmax + 10]
        txt = (f"Abertura da sua melhor volta: {', '.join(f'{RODAS_C[r]} {ab[r]} °C' for r in (2, 3, 0, 1))}. "
               f"Ideal para o {comp}: {cmin}–{cmax} °C (100% de aderência).")
        if frios_ab:
            add("Pneus", txt + f" {'/'.join(frios_ab)} abriram frios: aqueça mais na volta de saída (mais freadas fortes e acelerações).")
        elif quentes_ab:
            add("Pneus", txt + f" {'/'.join(quentes_ab)} abriram quentes demais: alivie a volta de saída.")
        else:
            add("Pneus", txt + " Você abriu a volta na temperatura certa.", "bom")
    return out


def _limpas(D, c):
    """Voltas de ritmo de corrida do carro: válidas, sem a 1ª, sem box e sem safety car; tira as com erro grande."""
    import corrida
    box, sc = corrida._voltas_box(D, c), corrida._voltas_sc(D)
    vs = [v for v in (D["voltas"].get(c) or []) if v.get("valida") and v.get("ms") and v["n"] > 1
          and v["n"] not in box and v["n"] not in sc]
    if len(vs) < 3:
        return []
    med = statistics.median(v["ms"] for v in vs)
    return [v for v in vs if v["ms"] < med + 3000]


def resumo_com_escolha(D, apices_idx):
    """"Seu resumo" com a referência escolhida e as dicas prontas contra cada piloto, para trocar no relatório.
    Corrida: compara RITMO (a volta de cada um mais perto da mediana das voltas limpas) e a referência padrão é
    quem tem o melhor ritmo. Outras sessões: melhor volta contra melhor volta, referência = a mais rápida."""
    M = D["meta"]
    J = M["jogador"]
    nome = lambda c: D["pilotos"].get(c, {}).get("nome", f"Carro {c + 1}")
    corrida_ = M["tipo"] == "corrida"
    por_carro = {}
    for t in D["tracos"]:
        por_carro.setdefault(t["carro"], []).append(t)
    opcoes, A = [], None
    if corrida_:
        def ritmo(c):
            lp = _limpas(D, c)
            if not lp:
                return None
            med = statistics.median(v["ms"] for v in lp)
            ns = {v["n"] for v in lp}
            cand = [t for t in por_carro.get(c, []) if t["volta"] in ns and t.get("ms")]
            if not cand:
                return None
            return med, len(lp), min(cand, key=lambda t: abs(t["ms"] - med))
        meu = ritmo(J)
        if meu:
            A = meu[2]
            for c in por_carro:
                if c == J:
                    continue
                r = ritmo(c)
                if r:
                    opcoes.append({"carro": c, "nome": nome(c), "ritmo_ms": round(r[0]), "n_limpas": r[1], "tr": r[2]})
            # quem tem poucas voltas limpas (abandonou, rodou...) vai para o fim da lista: ritmo pouco confiável
            lim = max([3] + [o["n_limpas"] for o in opcoes]) / 2
            opcoes.sort(key=lambda o: (o["n_limpas"] < lim, o["ritmo_ms"]))
    if not opcoes:
        A = None
        for c, ts in por_carro.items():
            vs = [t for t in ts if t["valida"] and t.get("ms")] if c != J else []
            if vs:
                b = min(vs, key=lambda t: t["ms"])
                opcoes.append({"carro": c, "nome": nome(c), "tr": b})
        opcoes.sort(key=lambda o: o["tr"]["ms"])
    base = seu_resumo(D, apices_idx, A, opcoes[0]["tr"] if opcoes else None)
    if base.get("aviso") or not opcoes:
        return base
    base["modo"] = "ritmo" if A else "melhor"
    if A:
        lp = _limpas(D, J)
        base["ritmo"] = {"ms": round(statistics.median(v["ms"] for v in lp)), "n_limpas": len(lp)}
    por = {}
    for o in opcoes:
        r = base if o is opcoes[0] else seu_resumo(D, apices_idx, A, o["tr"])
        por[str(o["carro"])] = {"itens": r["itens"], "ref": r.get("ref")}
    base["opcoes"] = [{k: v for k, v in o.items() if k != "tr"} | {"volta": o["tr"]["volta"], "ms": o["tr"]["ms"]} for o in opcoes]
    base["por_piloto"] = por
    return base


# ---------------------------------------------------------------- resumo da sessão
def resumo_sessao(D):
    M = D["meta"]
    comp = M["comprimento"]
    linhas = []
    for c, vs in D["voltas"].items():
        validas = [v for v in vs if v["valida"]]
        if not vs:
            continue
        melhor = min(validas, key=lambda v: v["ms"]) if validas else None
        setores = [min((v["s"][k] for v in vs if v["s_validos"][k] and v["s"][k] > 0), default=None) for k in range(3)]
        ideal = sum(setores) if all(setores) else None
        medias = [comp / (v["ms"] / 1000) * 3.6 for v in validas]
        linhas.append({
            "carro": c,
            "melhor": melhor["ms"] if melhor else None,
            "vel_media_melhor": round(comp / (melhor["ms"] / 1000) * 3.6, 1) if melhor else None,
            "vel_media": round(statistics.mean(medias), 1) if medias else None,
            "vmax": D["vmax_carro"].get(c) or None,
            "speed_trap": D["speed_trap"].get(c),
            "setores": setores,
            "ideal": ideal,
            "validas": len(validas),
            "voltas": len(vs),
            "avisos": D["avisos_carro"].get(c, 0),
            "consistencia": round(statistics.pstdev([v["ms"] for v in validas]) / 1000, 3) if len(validas) >= 2 else None,
        })
    return {"pilotos": linhas}
