"""
Painel BiInk - Amostra de dados do delivery (1º semestre de 2026)

Gráficos gerados:
    1 - Operação e Entregas      -> barras agrupadas  (problemas 1 e 2)
    2 - Produção e Desperdício   -> linhas            (problemas 3 e 4)
    3 - Gestão e Desempenho      -> Pareto            (problemas 5 e 6)
"""
import json
from pathlib import Path

import pandas as pd

# =====================================================================
# CONFIGURAÇÃO - ajuste aqui
# =====================================================================
PASTA_DADOS = Path(__file__).parent
PASTA_SAIDA = PASTA_DADOS / "saida"

ARQ_FATURAMENTO = "faturamento_delivery_1sem_2026_crise.csv"
ARQ_ENTREGA = "entrega_qualidade_1sem_2026_crise.csv"
ARQ_PREPARO = "preparo_desperdicio_1sem_2026_crise.csv"

# PREMISSAS DE CUSTO: os CSVs não trazem esses valores.
# Troque pelos números reais da BiInk. Eles afetam o custo do desperdício
# (gráfico 2) e o peso de "atrasos" e "desperdício" no Pareto (gráfico 3).
CUSTO_POR_KG_DESPERDICIO_RS = 12.00   # R$ por kg de alimento descartado
CUSTO_POR_PEDIDO_ATRASADO_RS = 8.00   # R$ por pedido atrasado (cupom, reembolso parcial, etc.)

MESES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
         7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


# =====================================================================
# 1) CARGA E UNIÃO DAS PLANILHAS
# =====================================================================
def carregar_dados() -> pd.DataFrame:
    fat = pd.read_csv(PASTA_DADOS / ARQ_FATURAMENTO, parse_dates=["data"])
    ent = pd.read_csv(PASTA_DADOS / ARQ_ENTREGA, parse_dates=["data"])
    pre = pd.read_csv(PASTA_DADOS / ARQ_PREPARO, parse_dates=["data"])
    df = fat.merge(ent, on="data", how="inner").merge(pre, on="data", how="inner")

    # Validações simples para não gerar gráfico em cima de dado quebrado
    if df.empty:
        raise ValueError("As planilhas não têm datas em comum.")
    if df.isna().any().any():
        raise ValueError("Há valores vazios nas planilhas.")
    if (df["pedidos_com_atraso"] > df["pedidos_entregues"]).any():
        raise ValueError("Há dias com mais atrasos do que pedidos entregues.")

    df["mes"] = df["data"].dt.month
    return df.sort_values("data").reset_index(drop=True)


# =====================================================================
# 2) CÁLCULOS DE CADA GRÁFICO
# =====================================================================
def grafico1_operacao(df: pd.DataFrame) -> dict:
    """Pedidos x prazo x adoção do módulo de motoboy, por mês."""
    g = df.groupby("mes").agg(
        recebidos=("pedidos_recebidos", "sum"),
        entregues=("pedidos_entregues", "sum"),
        atrasados=("pedidos_com_atraso", "sum"),
        adocao_motoboy=("adocao_modulo_motoboy_%", "mean"),
    )
    g["no_prazo"] = g["entregues"] - g["atrasados"]
    g["pct_atraso"] = g["atrasados"] / g["entregues"] * 100

    corr = df["adocao_modulo_motoboy_%"].corr(df["pedidos_com_atraso"] / df["pedidos_entregues"])
    return {
        "meses": [MESES[m] for m in g.index],
        "recebidos": g["recebidos"].tolist(),
        "no_prazo": g["no_prazo"].tolist(),
        "atrasados": g["atrasados"].tolist(),
        "adocao_motoboy": g["adocao_motoboy"].round(1).tolist(),
        "pct_atraso_total": round(df["pedidos_com_atraso"].sum() / df["pedidos_entregues"].sum() * 100, 1),
        "correlacao": round(float(corr), 2),
    }


def grafico2_desperdicio(df: pd.DataFrame) -> dict:
    """Evolução mensal do desperdício, do custo estimado e do volume de pedidos."""
    g = df.groupby("mes").agg(
        kg=("alimentos_descartados_kg", "sum"),
        pedidos=("pedidos_recebidos", "sum"),
    )
    g["custo"] = g["kg"] * CUSTO_POR_KG_DESPERDICIO_RS
    g["kg_por_100"] = g["kg"] / g["pedidos"] * 100
    return {
        "meses": [MESES[m] for m in g.index],
        "kg": g["kg"].round(1).tolist(),
        "custo": g["custo"].round(2).tolist(),
        "pedidos": g["pedidos"].tolist(),
        "kg_por_100": g["kg_por_100"].round(1).tolist(),
        "kg_total": round(float(g["kg"].sum()), 1),
        "uso_previsao": round(float(df["uso_previsao_demanda_%"].mean()), 1),
    }


def grafico3_pareto(df: pd.DataFrame) -> dict:
    """Pareto do impacto financeiro estimado de cada problema."""
    fatores = {
        # dado real da planilha de faturamento
        "Cancelamentos e reembolsos": float(df["perdas_reembolsos_rs"].sum()),
        # usa as premissas de custo da configuração
        "Atrasos nas entregas": float(df["pedidos_com_atraso"].sum() * CUSTO_POR_PEDIDO_ATRASADO_RS),
        "Desperdício de alimentos": float(df["alimentos_descartados_kg"].sum() * CUSTO_POR_KG_DESPERDICIO_RS),
    }
    serie = pd.Series(fatores).sort_values(ascending=False)
    acumulado = serie.cumsum() / serie.sum() * 100
    return {
        "fatores": serie.index.tolist(),
        "valores": serie.round(2).tolist(),
        "acumulado": acumulado.round(1).tolist(),
        "total": round(float(serie.sum()), 2),
        "faturamento": round(float(df["faturamento_bruto_rs"].sum()), 2),
        "precisao_status": round(float(df["precisao_status_ciclo_%"].mean()), 1),
        "uso_previsao": round(float(df["uso_previsao_demanda_%"].mean()), 1),
    }


# =====================================================================
# 3) PNGs (matplotlib) - bons para colar em apresentação
# =====================================================================
COR = {"tinta": "#14213D", "prazo": "#1B998B", "atraso": "#E4572E",
       "neutro": "#9AA5B1", "alerta": "#F2A541"}


def gerar_pngs(g1: dict, g2: dict, g3: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

    # ---- Gráfico 1: barras agrupadas ----
    x = np.arange(len(g1["meses"]))
    w = 0.26
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.bar(x - w, g1["recebidos"], w, label="Pedidos recebidos", color=COR["neutro"])
    ax.bar(x, g1["no_prazo"], w, label="Entregues no prazo", color=COR["prazo"])
    ax.bar(x + w, g1["atrasados"], w, label="Pedidos atrasados", color=COR["atraso"])
    ax.set_xticks(x, g1["meses"])
    ax.set_ylabel("Pedidos no mês")
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(x, g1["adocao_motoboy"], color=COR["tinta"], marker="o", lw=2,
             label="Adoção do módulo de motoboy (%)")
    ax2.set_ylim(0, 60)
    ax2.set_ylabel("Adoção do módulo (%)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.08))
    ax.set_title("Operação e entregas: pedidos x prazo (1º semestre 2026)", loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(PASTA_SAIDA / "grafico1_operacao_entregas.png", dpi=160)
    plt.close(fig)

    # ---- Gráfico 2: linhas ----
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(g2["meses"], g2["kg"], marker="o", lw=2.4, color=COR["atraso"], label="Alimentos descartados (kg)")
    ax.plot(g2["meses"], g2["pedidos"], marker="s", lw=2.4, color=COR["neutro"],
            label="Pedidos recebidos (produção)")
    ax.set_ylabel("kg  /  pedidos")
    ax.set_ylim(0, max(g2["pedidos"]) * 1.15)
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(g2["meses"], g2["custo"], marker="^", lw=2.4, ls="--", color=COR["alerta"],
             label="Custo do desperdício (R$, estimado)")
    ax2.set_ylabel("R$ (estimado)")
    ax2.set_ylim(0, max(g2["custo"]) * 1.25)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.08))
    ax.set_title("Produção e desperdício: evolução mensal", loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(PASTA_SAIDA / "grafico2_producao_desperdicio.png", dpi=160)
    plt.close(fig)

    # ---- Gráfico 3: Pareto ----
    fig, ax = plt.subplots(figsize=(10, 5.2))
    cores = [COR["atraso"] if i == 0 else COR["neutro"] for i in range(len(g3["fatores"]))]
    ax.bar(g3["fatores"], g3["valores"], color=cores)
    ax.set_ylabel("Impacto estimado (R$)")
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(g3["fatores"], g3["acumulado"], color=COR["tinta"], marker="o", lw=2)
    ax2.axhline(80, color=COR["tinta"], ls=":", lw=1)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("% acumulado")
    for i, v in enumerate(g3["valores"]):
        ax.text(i, v, f"R$ {v:,.0f}".replace(",", "."), ha="center", va="bottom", fontsize=10)
    ax.set_title("Gestão e desempenho: o que mais pesa (Pareto)", loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(PASTA_SAIDA / "grafico3_pareto.png", dpi=160)
    plt.close(fig)


# =====================================================================
# 4) TELA HTML (Chart.js via CDN)
# =====================================================================
def brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BiInk | Painel do delivery</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --tinta:#14213D; --papel:#F3F5F7; --cartao:#FFFFFF; --linha:#D9DEE4;
    --prazo:#1B998B; --atraso:#E4572E; --neutro:#9AA5B1; --alerta:#F2A541; --texto:#26303F; --suave:#5C6877;
  }
  @media (prefers-color-scheme: dark) {
    :root { --papel:#0E1624; --cartao:#16213A; --linha:#2A3754; --texto:#E6EBF2; --suave:#9AA7BA; --tinta:#E6EBF2; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--papel); color:var(--texto);
         font-family:"Segoe UI", system-ui, -apple-system, Roboto, sans-serif; line-height:1.5; }
  header { background:#14213D; color:#fff; padding:28px 24px 24px; }
  header h1 { margin:0 0 4px; font-size:1.7rem; letter-spacing:-.01em; }
  header p { margin:0; color:#B8C2D3; max-width:70ch; }
  main { max-width:1080px; margin:0 auto; padding:24px 16px 56px; display:grid; gap:24px; }
  section { background:var(--cartao); border:1px solid var(--linha); border-radius:10px; padding:22px; }
  section h2 { margin:0 0 4px; font-size:1.2rem; }
  .problemas { margin:0 0 14px; color:var(--suave); font-size:.92rem; }
  .grafico { position:relative; height:360px; }
  .leitura { margin:16px 0 0; padding:12px 14px; border-left:4px solid var(--atraso);
             background:color-mix(in srgb, var(--atraso) 8%, transparent); max-width:80ch; }
  .nota { margin:10px 0 0; color:var(--suave); font-size:.86rem; max-width:90ch; }
  footer { max-width:1080px; margin:0 auto; padding:0 16px 40px; color:var(--suave); font-size:.85rem; }
  @media (max-width:640px) { .grafico { height:300px; } }
</style>
</head>
<body>
<header>
  <h1>BiInk | Painel do delivery</h1>
  <p>Janeiro a junho de 2026, calculado a partir das planilhas de faturamento, entrega e preparo.</p>
</header>
<main>
  <section>
    <h2>Operação e entregas</h2>
    <p class="problemas">Problema 1: atraso nas entregas. Problema 2: falta de motoboys.</p>
    <div class="grafico"><canvas id="g1" role="img" aria-label="Barras agrupadas de pedidos recebidos, no prazo e atrasados por mês"></canvas></div>
    <p class="leitura">__LEITURA1__</p>
    <p class="nota">As planilhas não trazem o número de motoboys. A linha mostra a adoção do módulo de motoboy no sistema, usada como indicador no lugar da quantidade de entregadores.</p>
  </section>
  <section>
    <h2>Produção e desperdício</h2>
    <p class="problemas">Problema 3: desperdício de alimentos. Problema 4: falta de controle dos recursos.</p>
    <div class="grafico"><canvas id="g2" role="img" aria-label="Linhas mensais de kg descartados, custo estimado e pedidos recebidos"></canvas></div>
    <p class="leitura">__LEITURA2__</p>
    <p class="nota">Não há planilha de produção nem de custo. Os pedidos recebidos representam a produção, e o custo é o peso descartado multiplicado por __CUSTO_KG__ por kg (premissa editável no script).</p>
  </section>
  <section>
    <h2>Gestão e desempenho</h2>
    <p class="problemas">Problema 5: falta de informação para decidir. Problema 6: dificuldade no controle dos resultados.</p>
    <div class="grafico"><canvas id="g3" role="img" aria-label="Pareto do impacto financeiro estimado por problema"></canvas></div>
    <p class="leitura">__LEITURA3__</p>
    <p class="nota">Cancelamentos e reembolsos vêm direto da planilha. Atrasos (__CUSTO_ATRASO__ por pedido) e desperdício usam as premissas de custo do script, então os valores são estimativas.</p>
  </section>
</main>
<footer>Gerado por painel_biink.py</footer>
<script>
const D = __DADOS__;
const css = getComputedStyle(document.documentElement);
const cor = n => css.getPropertyValue(n).trim();
Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
Chart.defaults.color = cor('--suave');
Chart.defaults.borderColor = cor('--linha');
const base = { responsive:true, maintainAspectRatio:false, interaction:{mode:'index', intersect:false},
               plugins:{ legend:{position:'bottom'} } };
const fmt = v => v.toLocaleString('pt-BR');

new Chart(document.getElementById('g1'), {
  data: { labels: D.g1.meses, datasets: [
    { type:'bar', label:'Pedidos recebidos', data:D.g1.recebidos, backgroundColor:cor('--neutro') },
    { type:'bar', label:'Entregues no prazo', data:D.g1.no_prazo, backgroundColor:cor('--prazo') },
    { type:'bar', label:'Pedidos atrasados', data:D.g1.atrasados, backgroundColor:cor('--atraso') },
    { type:'line', label:'Adoção do módulo de motoboy (%)', data:D.g1.adocao_motoboy, yAxisID:'y1',
      borderColor:cor('--tinta'), backgroundColor:cor('--tinta'), tension:.25, pointRadius:4 }
  ]},
  options: { ...base, scales:{
    y:{ beginAtZero:true, title:{display:true, text:'Pedidos no mês'} },
    y1:{ position:'right', min:0, max:60, grid:{drawOnChartArea:false}, title:{display:true, text:'Adoção (%)'} } } }
});

new Chart(document.getElementById('g2'), {
  type:'line',
  data: { labels: D.g2.meses, datasets: [
    { label:'Alimentos descartados (kg)', data:D.g2.kg, borderColor:cor('--atraso'), backgroundColor:cor('--atraso'), tension:.25, pointRadius:4 },
    { label:'Pedidos recebidos (produção)', data:D.g2.pedidos, borderColor:cor('--neutro'), backgroundColor:cor('--neutro'), tension:.25, pointRadius:4 },
    { label:'Custo do desperdício (R$, estimado)', data:D.g2.custo, yAxisID:'y1', borderColor:cor('--alerta'),
      backgroundColor:cor('--alerta'), borderDash:[6,4], tension:.25, pointRadius:4 }
  ]},
  options: { ...base, scales:{
    y:{ beginAtZero:true, title:{display:true, text:'kg / pedidos'} },
    y1:{ position:'right', beginAtZero:true, grid:{drawOnChartArea:false}, title:{display:true, text:'R$ (estimado)'} } } }
});

new Chart(document.getElementById('g3'), {
  data: { labels: D.g3.fatores, datasets: [
    { type:'bar', label:'Impacto estimado (R$)', data:D.g3.valores,
      backgroundColor: D.g3.valores.map((_, i) => i === 0 ? cor('--atraso') : cor('--neutro')) },
    { type:'line', label:'% acumulado', data:D.g3.acumulado, yAxisID:'y1',
      borderColor:cor('--tinta'), backgroundColor:cor('--tinta'), pointRadius:5, tension:0 }
  ]},
  options: { ...base, scales:{
    y:{ beginAtZero:true, title:{display:true, text:'Impacto estimado (R$)'} },
    y1:{ position:'right', min:0, max:100, grid:{drawOnChartArea:false}, title:{display:true, text:'% acumulado'} } },
    plugins:{ legend:{position:'bottom'},
      tooltip:{ callbacks:{ label:c => c.dataset.yAxisID === 'y1' ? c.parsed.y + '%' : 'R$ ' + fmt(c.parsed.y) } } } }
});
</script>
</body>
</html>
"""


def gerar_html(g1: dict, g2: dict, g3: dict) -> None:
    corr = g1["correlacao"]
    if abs(corr) < 0.3:
        frase_corr = (f"Nos dados diários, a adoção do módulo de motoboy quase não se relaciona com a taxa de atraso "
                      f"(correlação {corr:.2f}), então esta amostra não mostra que a falta de entregadores explique os atrasos.")
    else:
        frase_corr = f"A correlação entre adoção do módulo e taxa de atraso é {corr:.2f}."
    leitura1 = (f"Em média, {g1['pct_atraso_total']:.0f}% dos pedidos entregues chegam atrasados, mês após mês. {frase_corr}")

    kg = g2["kg"]
    var = (kg[-1] / kg[0] - 1) * 100
    pico = g2["meses"][kg.index(max(kg))]
    leitura2 = (f"Foram {g2['kg_total']:.0f} kg descartados no semestre, com pico em {pico}. "
                f"De janeiro a junho a variação foi de {var:+.0f}%. "
                f"O uso da previsão de demanda ficou em {g2['uso_previsao']:.0f}% em todo o período.")

    topo = g3["fatores"][0]
    perc_topo = g3["valores"][0] / g3["total"] * 100
    leitura3 = (f"{topo} lidera, com {perc_topo:.0f}% do impacto estimado ({brl(g3['valores'][0])} de {brl(g3['total'])}). "
                f"A precisão do status do pedido ficou em {g3['precisao_status']:.0f}% e a previsão de demanda não foi usada, "
                f"o que mostra a falta de informação para decidir.")

    dados = {"g1": g1, "g2": g2, "g3": g3}
    html = (HTML.replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
                .replace("__LEITURA1__", leitura1).replace("__LEITURA2__", leitura2)
                .replace("__LEITURA3__", leitura3)
                .replace("__CUSTO_KG__", f"R$ {CUSTO_POR_KG_DESPERDICIO_RS:.2f}".replace(".", ","))
                .replace("__CUSTO_ATRASO__", f"R$ {CUSTO_POR_PEDIDO_ATRASADO_RS:.2f}".replace(".", ",")))
    (PASTA_SAIDA / "painel_biink.html").write_text(html, encoding="utf-8")


# =====================================================================
# 5) EXECUÇÃO
# =====================================================================
def main() -> None:
    PASTA_SAIDA.mkdir(exist_ok=True)
    df = carregar_dados()
    g1, g2, g3 = grafico1_operacao(df), grafico2_desperdicio(df), grafico3_pareto(df)
    gerar_html(g1, g2, g3)
    gerar_pngs(g1, g2, g3)
    print(f"{len(df)} dias lidos ({df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y}).")
    print(f"Arquivos gerados em: {PASTA_SAIDA}")


if __name__ == "__main__":
    main()
