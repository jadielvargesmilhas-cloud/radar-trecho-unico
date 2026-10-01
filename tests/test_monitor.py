import json
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import monitor  # noqa: E402

HOJE = date(2026, 10, 1)


class Resp:
    def __init__(self, status, dados):
        self.status_code, self._d = status, dados

    def json(self):
        return self._d


class Sessao:
    def __init__(self, resposta=None):
        self.gets, self.posts, self.resposta = [], [], resposta

    def get(self, url, params=None, timeout=None):
        self.gets.append(params)
        return self.resposta

    def post(self, url, data=None, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "json": json})
        return Resp(200, {})


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    (tmp_path / "config.json").write_text(json.dumps(c), encoding="utf-8")
    monkeypatch.setattr(monitor, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(monitor, "HISTORICO", tmp_path / "data" / "historico.json")
    monkeypatch.setenv("SERPAPI_KEY", "k")
    monkeypatch.setenv("NTFY_TOPIC", "t")
    return c


def rodar(ff, serp=None, sessao=None, hoje=HOJE):
    return monitor.executar(buscar_ff=ff, buscar_serp=serp or (lambda *a: (_ for _ in ()).throw(RuntimeError("x"))),
                            sessao=sessao or Sessao(), hoje=hoje, dormir=lambda s: None)


def tabela(precos):
    """precos[(origem, dia, classe)] -> valor"""
    def ff(cfg, o, dia, classe, pausa):
        return {"preco_total": precos[(o["id"], dia, classe)], "fonte": "fast-flights", "companhia": "X"}
    return ff


def base():
    p = {}
    for i, o in enumerate(["MAD", "LIS", "BCN", "PAR"]):
        for j, d in enumerate(["2027-07-03", "2027-07-04", "2027-07-05", "2027-07-06"]):
            p[(o, d, "economy")] = 4000 + i * 300 + j * 50
            p[(o, d, "business")] = 20000 + i * 900 - j * 100
    return p


def test_fast_flights_consulta_real_trecho_unico(cfg, monkeypatch):
    import fast_flights
    from fast_flights.model import Airport, CarbonEmission, Flights, SimpleDatetime, SingleFlight
    vistas = []

    def falso(q):
        vistas.append(q)
        sf = SingleFlight(Airport("a", "CDG"), Airport("b", "SSA"), SimpleDatetime((2027, 7, 4), (21, 5)),
                          SimpleDatetime((2027, 7, 5), (6, 0)), 600, "A330")
        preco = 5100 if q.flight_data[0].from_airport.airport == "CDG" else 4800
        return [Flights("x", preco, ["TAP"], [sf, sf], CarbonEmission(1, 1))]

    monkeypatch.setattr(fast_flights, "get_flights", falso)
    paris = cfg["origens"][3]
    l = monitor.buscar_fast_flights(cfg, paris, "2027-07-04", "business")
    assert [q.flight_data[0].from_airport.airport for q in vistas] == ["CDG", "ORY"]   # os 2 aeroportos
    q = vistas[0]
    assert q.get_trip_type() == "one-way" and len(q.flight_data) == 1              # trecho único
    assert q.flight_data[0].to_airport.airport == "SSA"                           # Europa → Salvador
    assert q.get_seat_type() == "business" and len(q.passengers) == 2 and q.currency == "BRL"
    assert q.flight_data[0].date == "2027-07-04"
    assert l["preco_total"] == 4800 and l["aeroporto"] == "ORY" and l["saida"] == "21:05" and l["escalas"] == 1


def test_serpapi_parametros_trecho_unico(cfg):
    resp = {"best_flights": [{"price": 23900, "total_duration": 640,
                              "flights": [{"airline": "Iberia", "departure_airport": {"id": "MAD", "time": "2027-07-05 23:55"}}]}],
            "price_insights": {"price_level": "high", "typical_price_range": [18000, 22000]}}
    s = Sessao(Resp(200, resp))
    l = monitor.buscar_serpapi(cfg, cfg["origens"][0], "2027-07-05", "business", "k", sessao=s)
    p = s.gets[0]
    assert p["type"] == "2" and "return_date" not in p
    assert p["departure_id"] == "MAD" and p["arrival_id"] == "SSA" and p["travel_class"] == "3"
    assert p["adults"] == "2" and p["currency"] == "BRL"
    assert l["preco_total"] == 23900 and l["saida"] == "23:55" and l["escalas"] == 0 and l["nivel"] == "high"


def test_32_combinacoes_e_ranking(cfg):
    h = rodar(tabela(base()))
    assert len(h["combos"]) == 32 and h["execucoes"][-1]["ok"] == 32
    r = monitor.ranking_do_dia(h, cfg)
    assert r["economy"]["2027-07-03"][0] == (4000, "Madrid")
    assert r["business"]["2027-07-06"][0] == (19700, "Madrid")
    assert h["combos"]["LIS-SSA|2027-07-04|economy"]["leituras"][-1]["por_pessoa"] == 2175


def test_resumo_unico_com_quedas(cfg):
    s = Sessao()
    p = base()
    rodar(tabela(p), sessao=s)
    assert s.posts == []
    p[("PAR", "2027-07-05", "economy")] = 3500        # Paris vira a mais barata do dia 05 (recorde)
    p[("BCN", "2027-07-03", "business")] = 21500      # queda em executiva
    h = rodar(tabela(p), sessao=s)
    assert len(s.posts) == 1                           # UMA mensagem, não uma por combinação
    msg = s.posts[0]["json"]
    assert "2 quedas" in msg["title"] and msg["priority"] == 4
    assert "Paris 05/07 Econômica" in msg["message"] and "05/07: Paris R$ 3.500" in msg["message"]
    assert {a["tipo"] for a in h["alertas"]} == {"recorde"}


def test_rodizio_da_serpapi_quando_fonte_gratis_cai(cfg):
    def ff_bloqueado(*a):
        raise RuntimeError("bloqueado")

    atendidas = []

    def serp(cfg_, o, dia, classe, chave):
        atendidas.append((o["id"], dia, classe))
        return {"preco_total": 5000, "fonte": "SerpApi"}

    for _ in range(4):
        rodar(ff_bloqueado, serp)
    assert len(atendidas) == 32                        # 8 por dia × 4 dias
    assert len(set(atendidas)) == 32                   # nenhuma repetida: cobriu todas as 32


def test_limite_mensal(cfg):
    monitor.salvar_json(monitor.HISTORICO, {"combos": {}, "alertas": [], "execucoes": [],
                                            "uso_serpapi": {"2026-10": 240}})
    chamadas = []
    rodar(lambda *a: (_ for _ in ()).throw(RuntimeError("b")),
          lambda *a: chamadas.append(1) or {"preco_total": 1})
    assert chamadas == []


def test_falha_total_avisa(cfg):
    s = Sessao()
    h = rodar(lambda *a: (_ for _ in ()).throw(RuntimeError("b")), sessao=s)
    assert h["execucoes"][-1]["ok"] == 0 and "falhou" in s.posts[-1]["json"]["title"]


def test_datas_passadas_saem_do_monitoramento(cfg):
    vistas = set()

    def ff(cfg_, o, dia, classe, pausa):
        vistas.add(dia)
        return {"preco_total": 1000}

    rodar(ff, hoje=date(2027, 7, 4))
    assert vistas == {"2027-07-05", "2027-07-06"}


def test_aviso_de_teste(cfg):
    s = Sessao()
    assert monitor.aviso_de_teste(sessao=s) == ["ntfy"] and "conectado" in s.posts[0]["json"]["title"]


# ------------------------------------------------------------ descoberta de outras cidades
def mundo(extra=None):
    """Preços base das 4 principais + candidatas (Porto e Vigo baratas, Londres quase, resto caro)."""
    p = base()
    for j, d in enumerate(["2027-07-03", "2027-07-04", "2027-07-05", "2027-07-06"]):
        for cid, eco, exe in [("OPO", 3900, 21000), ("VGO", 4100 if j != 1 else 3950, 19500),
                              ("LON", 4150, 19000), ("FRA", 6000, 25000), ("AMS", 6100, 18500)]:
            p[(cid, d, "economy")] = eco
            p[(cid, d, "business")] = exe
    p.update(extra or {})

    def ff(cfg, o, dia, classe, pausa):
        k = (o["id"], dia, classe)
        if k not in p:
            raise RuntimeError("sem voo")
        return {"preco_total": p[k], "fonte": "fast-flights", "escalas": 1, "duracao_min": 700}
    return ff, p


def test_descoberta_promove_mais_baratas_e_quase(cfg):
    s = Sessao()
    ff, _ = mundo()
    h = rodar(ff, sessao=s)                                   # 1ª execução: varredura roda sozinha
    alts = {c: [a["cidade"] for a in v] for c, v in h["alternativas"].items()}
    # econômica: melhor principal = Madrid 4000..4150; Porto 3900 e Vigo 3950 (dia 04) são mais baratas.
    # Londres 4150 nunca fica abaixo de Madrid -> NÃO entra (só entra quem é mais barato)
    assert alts["economy"] == ["Porto", "Vigo"]
    # executiva: melhor principal 19700..20000; Amsterdã 18500, Londres 19000, Vigo 19500
    assert alts["business"] == ["Amsterdã", "Londres", "Vigo"]
    # a leitura da varredura já semeia o histórico diário das promovidas
    assert h["combos"]["OPO-SSA|2027-07-03|economy"]["leituras"][-1]["preco_total"] == 3900
    assert h["combos"]["OPO-SSA|2027-07-03|economy"]["tipo"] == "alternativa"
    # ranking do dia passa a considerar as alternativas
    r = monitor.ranking_do_dia(h, cfg)
    assert r["economy"]["2027-07-03"][0] == (3900, "Porto")
    # notificação de descoberta enviada, com prioridade alta
    msg = [p for p in s.posts if "alternativa" in p["json"]["title"]][0]["json"]
    assert msg["priority"] == 4 and "Porto" in msg["message"] and "a menos que Madrid" in msg["message"]
    D = h["descoberta"]
    assert D["referencia"]["economy"]["2027-07-06"] == {"preco": 4150, "cidade": "Madrid"}   # referência congelada da varredura
    assert D["resultados"]["economy"]["OPO"]["vantagem"]["2027-07-06"] == 250
    assert "Palma de Maiorca" in D["sem_resultado"]["economy"]                           # sem voo no mundo simulado
    assert "Frankfurt" not in msg["message"] and "Londres, Econômica" not in msg["message"]   # na econômica Londres é só "quase"
    assert "Londres, Executiva" in msg["message"]
    assert "Porto, Econômica: 06/07 por R$ 3.900, R$ 250 a menos que Madrid (mais barata em 4 das 4 datas)" in msg["message"]
    assert msg["message"].count("Amsterdã") == 1 and "5 alternativas" in msg["title"]


def test_link_google_preenchido_e_codificado(cfg):
    from base64 import b64decode
    from urllib.parse import parse_qs, urlparse
    from fast_flights.pb.flights_pb2 import Info
    for aero, dia, classe, adultos in [("MAD", "2027-07-04", "business", 2), ("ORY", "2027-07-06", "economy", 2),
                                       ("LHR", "2027-07-03", "economy", 3)]:
        url = monitor.link_google(aero, "SSA", dia, classe, adultos, "BRL")
        assert url.startswith("https://www.google.com/travel/flights?tfs=")
        assert " " not in url and "+" not in url.split("tfs=", 1)[1].split("&")[0]   # '+' codificado como %2B
        qs = parse_qs(urlparse(url).query)                                          # como o navegador lê
        i = Info.FromString(b64decode(qs["tfs"][0]))
        assert (i.data[0].from_airport.airport, i.data[0].to_airport.airport, i.data[0].date) == (aero, "SSA", dia)
        assert len(i.passengers) == adultos and i.trip == 2                         # 2 = só ida
        assert i.seat == {"economy": 1, "business": 3}[classe]
        assert qs["curr"] == ["BRL"] and qs["hl"] == ["pt-BR"]


def test_so_mais_baratas_e_nenhuma_se_nada_bater(cfg):
    ff, p = mundo()
    for k in list(p):
        if k[0] not in ("MAD", "LIS", "BCN", "PAR"):
            p[k] = 99999                                   # nenhuma cidade candidata é mais barata
    s = Sessao()
    h = rodar(ff, sessao=s)
    assert h["alternativas"] == {"economy": [], "business": []}
    assert not [m for m in s.posts if "alternativa" in m["json"]["title"]]     # nenhum aviso de descoberta


def test_alternativas_viram_monitoramento_diario(cfg):
    ff, p = mundo()
    rodar(ff)                                                 # varredura (quarta-feira, 1ª vez)
    buscas = []

    def ff2(cfg_, o, dia, classe, pausa):
        buscas.append(o["id"])
        return ff(cfg_, o, dia, classe, pausa)

    p[("OPO", "2027-07-03", "economy")] = 3700
    h = rodar(ff2, hoje=date(2026, 10, 2))                   # sexta: sem varredura, só diário
    assert "FRA" not in buscas                                # candidata não promovida não é buscada no dia a dia
    assert buscas.count("OPO") == 4 and buscas.count("AMS") == 4   # Porto (eco) e Amsterdã (exec) em 4 datas
    assert "LON" in buscas and buscas.count("LON") == 4       # Londres só na executiva, onde é mais barata
    assert len(buscas) == 32 + (2 + 3) * 4                    # 32 principais + (2 eco + 3 exec) alternativas × 4 datas
    alerta = [a for a in h["alertas"] if a["cidade"] == "Porto"][-1]
    assert alerta["para"] == 3700 and alerta["tipo"] == "recorde"


def test_varredura_so_no_dia_marcado_ou_forcada(cfg, monkeypatch):
    ff, _ = mundo()
    rodar(ff)
    assert not monitor.descoberta_devida(cfg, monitor.carregar_json(monitor.HISTORICO, {}), date(2026, 10, 2))  # sexta
    assert monitor.descoberta_devida(cfg, monitor.carregar_json(monitor.HISTORICO, {}), date(2026, 10, 4))      # domingo
    monkeypatch.setenv("DESCOBRIR", "sim")
    assert monitor.descoberta_devida(cfg, monitor.carregar_json(monitor.HISTORICO, {}), date(2026, 10, 2))


def test_reserva_serpapi_nao_gasta_com_alternativas(cfg):
    ff, _ = mundo()
    rodar(ff)                                                 # promove alternativas
    usados = []

    def serp(cfg_, o, dia, classe, chave):
        usados.append(o["id"])
        return {"preco_total": 5000, "fonte": "SerpApi"}

    def quebra(*a):
        raise RuntimeError("bloqueado")

    rodar(quebra, serp, hoje=date(2026, 10, 2))
    assert usados and set(usados) <= {"MAD", "LIS", "BCN", "PAR"}


def test_nova_varredura_troca_alternativas(cfg, monkeypatch):
    ff, p = mundo()
    rodar(ff)
    for d in ["2027-07-03", "2027-07-04", "2027-07-05", "2027-07-06"]:
        p[("OPO", d, "economy")] = 9000                       # Porto encareceu
        p[("FRA", d, "economy")] = 3500                       # Frankfurt despencou
    monkeypatch.setenv("DESCOBRIR", "sim")
    h = rodar(ff, hoje=date(2026, 10, 4))
    eco = [a["cidade"] for a in h["alternativas"]["economy"]]
    assert eco[0] == "Frankfurt" and "Porto" not in eco
