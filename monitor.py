"""
Radar de Tarifas — TRECHO ÚNICO Europa → Salvador.

Para cada data × cidade de origem × classe (econômica/executiva), busca o menor
preço só de ida para N adultos e responde: "em cada dia, qual rota é a mais barata?"

Fonte principal : fast-flights (lê o Google Flights direto, grátis e sem limite)
Fonte reserva   : SerpApi (Google Flights), com orçamento diário/mensal para caber no plano grátis
Avisos          : ntfy (push no celular) e, opcional, Telegram — UMA mensagem-resumo por dia.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).parent
CONFIG = RAIZ / "config.json"
HISTORICO = RAIZ / "data" / "historico.json"
SERPAPI_URL = "https://serpapi.com/search.json"
CLASSE_PT = {"economy": "Econômica", "business": "Executiva", "premium-economy": "Premium", "first": "Primeira"}
CLASSE_SERP = {"economy": "1", "premium-economy": "2", "business": "3", "first": "4"}


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hoje_utc() -> date:
    return datetime.now(timezone.utc).date()


def brl(v) -> str:
    return "—" if v is None else "R$ " + f"{v:,.0f}".replace(",", ".")


def data_curta(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}/{d.month:02d}"


def carregar_json(caminho: Path, padrao):
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    return padrao


def salvar_json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    tmp.replace(caminho)


def link_google(aeroporto: str, destino: str, dia: str, classe: str, adultos: int, moeda: str) -> str:
    """Endereço do Google Flights já preenchido (só ida, origem, destino, data, passageiros, classe).
    É o mesmo endereço que a busca lê; o tfs é codificado para o '+' não virar espaço."""
    from urllib.parse import urlencode
    from fast_flights import FlightQuery, Passengers, create_query
    q = create_query(flights=[FlightQuery(date=dia, from_airport=aeroporto, to_airport=destino)],
                     trip="one-way", seat=classe, passengers=Passengers(adults=adultos), language="pt-BR", currency=moeda)
    return "https://www.google.com/travel/flights?" + urlencode(q.params())


def chave_combo(origem_id: str, destino: str, dia: str, classe: str) -> str:
    return f"{origem_id}-{destino}|{dia}|{classe}"


# ---------------------------------------------------------------- fontes
def buscar_fast_flights(cfg: dict, origem: dict, dia: str, classe: str, pausa: float = 0) -> dict:
    """Busca só de ida em cada aeroporto da cidade e fica com o menor."""
    from fast_flights import FlightQuery, Passengers, create_query, get_flights

    melhor, link, erros = None, None, []
    for i, aero in enumerate(origem["aeroportos"]):
        if i and pausa:
            time.sleep(pausa)
        q = create_query(
            flights=[FlightQuery(date=dia, from_airport=aero, to_airport=cfg["destino"])],
            trip="one-way", seat=classe, passengers=Passengers(adults=cfg["adultos"]),
            language="pt-BR", currency=cfg["moeda"],
        )
        try:
            validos = [f for f in get_flights(q) if isinstance(f.price, int) and f.price > 0]
        except Exception as e:  # noqa: BLE001
            erros.append(f"{aero}: {e}")
            continue
        if validos:
            f = min(validos, key=lambda x: x.price)
            if melhor is None or f.price < melhor[0].price:
                melhor, link = (f, aero, len(validos)), link_google(aero, cfg["destino"], dia, classe, cfg["adultos"], cfg["moeda"])
    if melhor is None:
        raise RuntimeError("fast-flights: " + ("; ".join(erros) or "nenhuma tarifa"))
    f, aero, n = melhor
    return {
        "preco_total": int(f.price), "fonte": "fast-flights", "link": link, "aeroporto": aero,
        "companhia": " + ".join(f.airlines) if f.airlines else None,
        "escalas": max(len(f.flights) - 1, 0),
        "duracao_min": sum(s.duration for s in f.flights) if f.flights else None,
        "saida": (f"{f.flights[0].departure.time[0]:02d}:{f.flights[0].departure.time[1]:02d}" if f.flights else None),
        "opcoes": n,
    }


def buscar_serpapi(cfg: dict, origem: dict, dia: str, classe: str, chave: str, sessao=requests) -> dict:
    params = {
        "engine": "google_flights", "type": "2",
        "departure_id": origem["serpapi"], "arrival_id": cfg["destino"], "outbound_date": dia,
        "adults": str(cfg["adultos"]), "travel_class": CLASSE_SERP[classe],
        "currency": cfg["moeda"], "hl": "pt", "gl": "br", "api_key": chave,
    }
    r = sessao.get(SERPAPI_URL, params=params, timeout=60)
    dados = r.json()
    if r.status_code != 200 or dados.get("error"):
        raise RuntimeError(f"SerpApi: {dados.get('error') or r.status_code}")
    opcoes = [o for o in (dados.get("best_flights") or []) + (dados.get("other_flights") or [])
              if isinstance(o.get("price"), (int, float))]
    if not opcoes:
        raise RuntimeError("SerpApi: nenhuma tarifa")
    m = min(opcoes, key=lambda o: o["price"])
    trechos = m.get("flights") or []
    cias = []
    for t in trechos:
        if t.get("airline") and t["airline"] not in cias:
            cias.append(t["airline"])
    ins = dados.get("price_insights") or {}
    saida = ((trechos[0].get("departure_airport") or {}).get("time") or "")[-5:] if trechos else None
    return {
        "preco_total": round(float(m["price"])), "fonte": "SerpApi",
        "link": link_google((trechos[0].get("departure_airport") or {}).get("id") or origem["serpapi"].split(",")[0],
                            cfg["destino"], dia, classe, cfg["adultos"], cfg["moeda"]),
        "aeroporto": (trechos[0].get("departure_airport") or {}).get("id") if trechos else None,
        "companhia": " + ".join(cias) or None, "escalas": max(len(trechos) - 1, 0),
        "duracao_min": m.get("total_duration"), "saida": saida or None, "opcoes": len(opcoes),
        "nivel": ins.get("price_level"), "faixa_tipica": ins.get("typical_price_range"),
    }


# ---------------------------------------------------------------- lógica
def comparar(leituras: list, novo: int, queda_minima: float) -> dict | None:
    if not leituras:
        return None
    ultimo = leituras[-1]["preco_total"]
    menor = min(l["preco_total"] for l in leituras)
    if novo < ultimo and ultimo - novo >= queda_minima:
        return {"de": ultimo, "para": novo, "economia": ultimo - novo, "tipo": "recorde" if novo < menor else "queda"}
    return None


def origens_da_classe(cfg: dict, hist: dict, classe: str) -> list:
    """As 4 principais + as alternativas promovidas pela varredura para esta classe."""
    alts = [dict(a, tipo="alternativa") for a in (hist.get("alternativas") or {}).get(classe, [])]
    return [dict(o, tipo="principal") for o in cfg["origens"]] + alts


DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def descoberta_devida(cfg: dict, hist: dict, hoje: date) -> bool:
    d = cfg.get("descoberta") or {}
    if not d.get("ativa") or not d.get("candidatas"):
        return False
    if os.getenv("DESCOBRIR", "").lower() == "sim" or not hist.get("descoberta"):
        return True
    return DIAS_SEMANA[hoje.weekday()] == str(d.get("dia_da_semana", "domingo")).lower()


def ranking_do_dia(hist: dict, cfg: dict) -> dict:
    """{classe: {dia: [(preco, cidade, chave), ...] ordenado}} usando a última leitura de cada combinação."""
    out = {}
    for classe in cfg["classes"]:
        out[classe] = {}
        for dia in cfg["datas"]:
            linha = []
            for o in origens_da_classe(cfg, hist, classe):
                c = hist["combos"].get(chave_combo(o["id"], cfg["destino"], dia, classe))
                if c and c["leituras"]:
                    linha.append((c["leituras"][-1]["preco_total"], o["cidade"]))
            out[classe][dia] = sorted(linha)
    return out


def notificar(titulo: str, texto: str, link: str | None, alta: bool = False, sessao=requests) -> list[str]:
    enviados = []
    topico = os.getenv("NTFY_TOPIC", "").strip()
    if topico:
        payload = {"topic": topico, "title": titulo, "message": texto, "tags": ["airplane"], "priority": 4 if alta else 3}
        if link:
            payload["click"] = link
        try:
            r = sessao.post("https://ntfy.sh/", json=payload, timeout=30)
            if getattr(r, "status_code", 200) >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            enviados.append("ntfy")
        except Exception as e:  # noqa: BLE001
            print(f"  ! ntfy falhou: {e}")
    tk, chat = os.getenv("TELEGRAM_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if tk and chat:
        try:
            sessao.post(f"https://api.telegram.org/bot{tk}/sendMessage",
                        json={"chat_id": chat, "text": f"{titulo}\n{texto}" + (f"\n{link}" if link else ""),
                              "disable_web_page_preview": True}, timeout=30)
            enviados.append("telegram")
        except Exception as e:  # noqa: BLE001
            print(f"  ! telegram falhou: {e}")
    return enviados


def executar(buscar_ff=buscar_fast_flights, buscar_serp=buscar_serpapi, sessao=requests,
             hoje: date | None = None, dormir=time.sleep) -> dict:
    cfg = carregar_json(CONFIG, None)
    hist = carregar_json(HISTORICO, {"combos": {}, "alertas": [], "execucoes": [], "uso_serpapi": {}})
    hoje = hoje or hoje_utc()
    chave_serp = os.getenv("SERPAPI_KEY", "").strip()
    painel = os.getenv("PAINEL_URL", "").strip() or None
    uso = hist.setdefault("uso_serpapi", {})
    mes, dia_hoje = hoje.strftime("%Y-%m"), hoje.isoformat()
    usados_hoje = 0
    pausa = cfg.get("pausa_entre_buscas_segundos", 4)
    exe = {"quando": agora_iso(), "ok": 0, "falhas": 0, "via_serpapi": 0, "detalhes": []}
    novidades = []

    datas_ativas = [d for d in cfg["datas"] if date.fromisoformat(d) > hoje]
    if not datas_ativas:
        exe["detalhes"].append("todas as datas já passaram")
    hist["config"] = {k: cfg[k] for k in ("destino", "adultos", "moeda", "datas", "classes")}
    hist["config"]["origens"] = [{"id": o["id"], "cidade": o["cidade"]} for o in cfg["origens"]]

    def registrar(k, o, dia, classe, leitura):
        leitura["quando"] = agora_iso()
        leitura["por_pessoa"] = round(leitura["preco_total"] / cfg["adultos"])
        combo = hist["combos"][k]
        mud = comparar(combo["leituras"], leitura["preco_total"], cfg.get("alertar_quando_cair_pelo_menos_reais", 1))
        combo["leituras"].append(leitura)
        combo["leituras"] = combo["leituras"][-400:]
        combo["menor"] = min(combo["leituras"], key=lambda l: l["preco_total"])
        exe["ok"] += 1
        print(f"  ✓ {o['cidade']} {data_curta(dia)} {CLASSE_PT[classe]}: {brl(leitura['preco_total'])} ({leitura.get('fonte', '?')})")
        if mud:
            a = {**mud, "combo": k, "cidade": o["cidade"], "data": dia, "classe": classe, "quando": leitura["quando"]}
            hist["alertas"].append(a)
            novidades.append(a)

    # 1ª passada: fonte gratuita em todas as combinações
    pendentes, primeira = [], True
    lidas_hoje = set()
    for classe in cfg["classes"]:
        for dia in datas_ativas:
            for o in origens_da_classe(cfg, hist, classe):
                k = chave_combo(o["id"], cfg["destino"], dia, classe)
                hist["combos"].setdefault(k, {"leituras": []}).update(
                    origem=o["id"], cidade=o["cidade"], data=dia, classe=classe, tipo=o["tipo"])
                if not primeira and pausa:
                    dormir(pausa)
                primeira = False
                try:
                    registrar(k, o, dia, classe, buscar_ff(cfg, o, dia, classe, pausa))
                    lidas_hoje.add(k)
                except Exception as e:  # noqa: BLE001
                    pendentes.append((k, o, dia, classe, [str(e)]))

    # 2ª passada: SerpApi só nas que falharam, começando pelas leituras mais antigas (rodízio)
    def idade(item):
        l = hist["combos"][item[0]]["leituras"]
        return l[-1]["quando"] if l else ""
    pendentes.sort(key=idade)
    for k, o, dia, classe, erros in pendentes:
        cabe = (o["tipo"] == "principal" and chave_serp and usados_hoje < cfg.get("serpapi_max_por_dia", 8)
                and uso.get(mes, 0) < cfg.get("serpapi_max_por_mes", 240))
        if cabe:
            uso[mes] = uso.get(mes, 0) + 1
            usados_hoje += 1
            try:
                registrar(k, o, dia, classe, buscar_serp(cfg, o, dia, classe, chave_serp))
                lidas_hoje.add(k)
                exe["via_serpapi"] += 1
                continue
            except Exception as e:  # noqa: BLE001
                erros.append(str(e))
        exe["falhas"] += 1
        rot = f"{o['cidade']} {data_curta(dia)} {CLASSE_PT[classe]}"
        exe["detalhes"].append(f"{rot}: " + " | ".join(erros)[:300])
        print(f"  ✗ {rot}: {' | '.join(erros)[:160]}")

    descobertas = []
    if datas_ativas and descoberta_devida(cfg, hist, hoje):
        descobertas = varrer(cfg, hist, datas_ativas, buscar_ff, dormir, pausa, lidas_hoje, registrar, exe)

    hist["atualizado_em"] = agora_iso()
    hist["alertas"] = hist["alertas"][-300:]
    hist["execucoes"] = (hist.get("execucoes", []) + [exe])[-60:]
    salvar_json(HISTORICO, hist)

    if novidades:
        rank = ranking_do_dia(hist, cfg)
        linhas = []
        for a in sorted(novidades, key=lambda x: (x["classe"], x["data"])):
            marca = "🏆" if a["tipo"] == "recorde" else "📉"
            linhas.append(f"{marca} {a['cidade']} {data_curta(a['data'])} {CLASSE_PT[a['classe']]}: "
                          f"{brl(a['de'])} → {brl(a['para'])}")
        linhas.append("")
        linhas.append("Mais barata de cada dia (econômica):" if "economy" in rank else "Mais barata de cada dia:")
        cl = "economy" if "economy" in rank else cfg["classes"][0]
        for dia, lista in rank[cl].items():
            if lista:
                linhas.append(f"  {data_curta(dia)}: {lista[0][1]} {brl(lista[0][0])}")
        recorde = any(a["tipo"] == "recorde" for a in novidades)
        titulo = f"{'🏆' if recorde else '📉'} {len(novidades)} queda{'s' if len(novidades) > 1 else ''} de preço para {cfg['destino']}"
        canais = notificar(titulo, "\n".join(linhas), painel, recorde, sessao)
        print(f"  ! resumo enviado via {canais or 'nenhum canal'}")

    if descobertas:
        grupos = {}
        for d_ in descobertas:                         # uma linha por cidade e classe, com o melhor dia
            g = grupos.setdefault((d_["cidade"], d_["classe"]), {**d_, "dias": 0})
            g["dias"] += 1
            if d_["vantagem"] > g["vantagem"]:
                g.update({k: d_[k] for k in ("data", "preco", "vantagem", "principal")})
        linhas = []
        for classe in cfg["classes"]:
            for g in sorted((g for g in grupos.values() if g["classe"] == classe), key=lambda x: -x["vantagem"]):
                extra = f" (mais barata em {g['dias']} das {len(datas_ativas)} datas)" if g["dias"] > 1 else ""
                linhas.append(f"🔎 {g['cidade']}, {CLASSE_PT[classe]}: {data_curta(g['data'])} por {brl(g['preco'])}, "
                              f"{brl(g['vantagem'])} a menos que {g['principal']}{extra}")
        linhas.append("")
        linhas.append("Essas cidades agora são monitoradas todo dia. Lembre de somar o custo de chegar até elas.")
        notificar(f"🔎 {len(grupos)} alternativa{'s' if len(grupos) > 1 else ''} mais barata{'s' if len(grupos) > 1 else ''} na Europa",
                  "\n".join(linhas), painel, True, sessao)

    if datas_ativas and exe["ok"] == 0:
        notificar("⚠️ Radar trecho único falhou hoje",
                  "Nenhuma combinação foi lida. Veja a aba Actions do GitHub.", painel, True, sessao)
    return hist


def varrer(cfg, hist, datas, buscar_ff, dormir, pausa, lidas_hoje, registrar, exe) -> list:
    """Busca todas as cidades candidatas; promove as melhores a alternativas diárias.
    Retorna as combinações candidatas que ficaram MAIS BARATAS que a melhor principal do dia."""
    d = cfg["descoberta"]
    principais = {o["id"] for o in cfg["origens"]}
    candidatas = [c for c in d["candidatas"] if c["id"] not in principais]
    resultados, falhas = {}, 0
    print(f"\n🔎 Varredura de {len(candidatas)} cidades candidatas")
    for classe in cfg["classes"]:
        resultados[classe] = {}
        for c in candidatas:
            precos = {}
            for dia in datas:
                k = chave_combo(c["id"], cfg["destino"], dia, classe)
                if k in lidas_hoje:                       # já foi lida hoje como alternativa: reaproveita
                    precos[dia] = hist["combos"][k]["leituras"][-1]
                    continue
                if pausa:
                    dormir(pausa)
                try:
                    l = buscar_ff(cfg, c, dia, classe, pausa)
                    l["quando"] = agora_iso()
                    l["por_pessoa"] = round(l["preco_total"] / cfg["adultos"])
                    precos[dia] = l
                except Exception:  # noqa: BLE001
                    falhas += 1
            if precos:
                resultados[classe][c["id"]] = {"cidade": c["cidade"], "aeroportos": c["aeroportos"], "precos": precos}

    # melhor principal por dia e classe (leitura de hoje)
    melhor_principal = {}
    for classe in cfg["classes"]:
        for dia in datas:
            op = []
            for o in cfg["origens"]:
                cb = hist["combos"].get(chave_combo(o["id"], cfg["destino"], dia, classe))
                if cb and cb["leituras"]:
                    op.append((cb["leituras"][-1]["preco_total"], o["cidade"]))
            if op:
                melhor_principal[(classe, dia)] = min(op)

    limite = d.get("promover_ate_por_classe", 5)
    promovidas, mais_baratas = {}, []
    for classe, cands in resultados.items():
        notas = []
        for cid, info in cands.items():
            melhor_v = None
            for dia, l in info["precos"].items():
                mp = melhor_principal.get((classe, dia))
                if not mp:
                    continue
                vant = mp[0] - l["preco_total"]
                info.setdefault("vantagem", {})[dia] = vant
                if vant > 0:
                    mais_baratas.append({"cidade": info["cidade"], "data": dia, "classe": classe,
                                         "preco": l["preco_total"], "vantagem": vant, "principal": mp[1]})
                rel = vant / mp[0]
                melhor_v = rel if melhor_v is None else max(melhor_v, rel)
            info["melhor_vantagem_rel"] = melhor_v
            if melhor_v is not None and melhor_v > 0:          # só entra se for MAIS BARATA em pelo menos uma data
                notas.append((melhor_v, cid))
        notas.sort(reverse=True)
        promovidas[classe] = [{"id": cid, "cidade": cands[cid]["cidade"], "aeroportos": cands[cid]["aeroportos"]}
                              for _, cid in notas[:limite]]
        for p_ in promovidas[classe]:                     # semeia o histórico diário com a leitura da varredura
            for dia, l in cands[p_["id"]]["precos"].items():
                k = chave_combo(p_["id"], cfg["destino"], dia, classe)
                if k in lidas_hoje:
                    continue
                hist["combos"].setdefault(k, {"leituras": []}).update(
                    origem=p_["id"], cidade=p_["cidade"], data=dia, classe=classe, tipo="alternativa")
                o = dict(p_, tipo="alternativa")
                registrar(k, o, dia, classe, dict(l))
                lidas_hoje.add(k)

    hist["alternativas"] = promovidas
    referencia = {c: {dia: {"preco": mp[0], "cidade": mp[1]} for (cl, dia), mp in melhor_principal.items() if cl == c}
                  for c in cfg["classes"]}
    sem_resultado = {c: [x["cidade"] for x in candidatas if x["id"] not in resultados.get(c, {})] for c in cfg["classes"]}
    hist["descoberta"] = {"quando": agora_iso(), "falhas": falhas, "resultados": resultados,
                          "referencia": referencia, "sem_resultado": sem_resultado,
                          "dia_da_semana": d.get("dia_da_semana", "domingo")}
    exe["descoberta"] = {"cidades": len(candidatas), "falhas": falhas,
                         "promovidas": {k: [p_["cidade"] for p_ in v] for k, v in promovidas.items()}}
    print(f"  promovidas: {exe['descoberta']['promovidas']}")
    mais_baratas.sort(key=lambda x: -x["vantagem"])
    return mais_baratas


def aviso_de_teste(sessao=requests) -> list[str]:
    return notificar("✅ Radar trecho único conectado",
                     "Se você está lendo isto, os avisos de queda de preço vão chegar neste celular.",
                     os.getenv("PAINEL_URL", "").strip() or None, False, sessao)


if __name__ == "__main__":
    if os.getenv("TESTE_AVISO", "").lower() == "sim":
        print("Aviso de teste enviado por:", aviso_de_teste() or "nenhum canal configurado")
    h = executar()
    e = h["execucoes"][-1]
    print(f"\nResumo: {e['ok']} lidas, {e['falhas']} falhas, {e['via_serpapi']} pela SerpApi.")
    sys.exit(0)
