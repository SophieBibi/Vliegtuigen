# vliegtuigen1.py
# Streamlit dashboard voor de VA-eindpresentatie over vluchten en luchthavens

import os
import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import folium
import branca.colormap as cm
from folium.plugins import HeatMap
from streamlit_folium import st_folium

try:
    from streamlit_option_menu import option_menu
except ImportError:
    option_menu = None

APP_NAME = "vliegtuigen1"
LUC_DATA_FILE = "DatasetLuchthaven_murged2.csv"

st.set_page_config(
    page_title="Eindpresentatie Visual Analytics",
    page_icon="✈️",
    layout="wide"
)

# -----------------------------------------------------------------------------
# Algemene helperfuncties
# -----------------------------------------------------------------------------

@st.cache_data
def load_luchthaven_data(path: str = LUC_DATA_FILE) -> pd.DataFrame:
    """Laadt en schoont de luchthaven-dataset."""
    df = pd.read_csv(path)

    # Datum en numerieke kolommen goed zetten
    df["STD"] = pd.to_datetime(df["STD"], errors="coerce")
    df["Latitude"] = pd.to_numeric(df["Latitude"].astype(str).str.replace(",", "."), errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"].astype(str).str.replace(",", "."), errors="coerce")
    df["verschil_minuten"] = pd.to_numeric(df["verschil_minuten"], errors="coerce")
    df["Jaartal"] = pd.to_numeric(df["Jaartal"], errors="coerce")

    # Status opnieuw logisch bepalen: negatief = te vroeg, rond 0 = op tijd, positief = te laat
    df["status_berekend"] = np.select(
        [df["verschil_minuten"] < 0, df["verschil_minuten"].between(0, 5, inclusive="both"), df["verschil_minuten"] > 5],
        ["Te vroeg", "Op tijd", "Te laat"],
        default="Onbekend"
    )

    # Lege waarden verwijderen voor belangrijke analyses
    df = df.dropna(subset=["STD", "City", "luchthaven", "verschil_minuten", "Latitude", "Longitude"])
    return df


@st.cache_data
def load_vluchten_data() -> dict:
    """Laadt de 7 losse vluchtbestanden als ze in dezelfde map staan."""
    mogelijke_bestanden = {
        "vlucht 1": ["cleaned_30Flight 1.xlsx", "30Flight 1.xlsx"],
        "vlucht 2": ["cleaned_30Flight 2.xlsx", "30Flight 2.xlsx"],
        "vlucht 3": ["cleaned_30Flight 3.xlsx", "30Flight 3.xlsx"],
        "vlucht 4": ["cleaned_30Flight 4.xlsx", "30Flight 4.xlsx"],
        "vlucht 5": ["cleaned_30Flight 5.xlsx", "30Flight 5.xlsx"],
        "vlucht 6": ["cleaned_30Flight 6.xlsx", "30Flight 6.xlsx"],
        "vlucht 7": ["cleaned_30Flight 7.xlsx", "30Flight 7.xlsx"],
    }

    vluchten = {}
    for vluchtnaam, bestandsnamen in mogelijke_bestanden.items():
        gevonden_bestand = next((bestand for bestand in bestandsnamen if os.path.exists(bestand)), None)
        if gevonden_bestand is None:
            continue

        df = pd.read_excel(gevonden_bestand)
        verplichte_kolommen = ["[3d Latitude]", "[3d Longitude]", "[3d Altitude Ft]", "TRUE AIRSPEED (derived)", "Time (secs)"]
        for kolom in verplichte_kolommen:
            if kolom in df.columns:
                df[kolom] = pd.to_numeric(df[kolom], errors="coerce")

        df = df.dropna(subset=["[3d Latitude]", "[3d Longitude]"])
        df["vlucht"] = vluchtnaam
        vluchten[vluchtnaam] = df

    return vluchten


def show_sidebar_menu():
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/e/e0/Airplane_silhouette.svg", width=80)
        st.caption(f"App-bestand: `{APP_NAME}.py`")

        opties = ["Intro", "Vluchten", "Luchthavens", "Analyse & Advies"]
        if option_menu:
            return option_menu(
                menu_title="Menu",
                options=opties,
                icons=["play", "airplane", "bezier", "bar-chart"],
                menu_icon="list",
                default_index=0,
            )
        return st.radio("Menu", opties)


def apply_luchthaven_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Sidebarfilters voor het luchthaven-dashboard."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters luchthavenanalyse")

    jaren = sorted([int(j) for j in df["Jaartal"].dropna().unique()])
    gekozen_jaren = st.sidebar.multiselect("Jaar", jaren, default=jaren)

    landen = sorted(df["Country"].dropna().unique())
    gekozen_landen = st.sidebar.multiselect("Land", landen, default=landen[:])

    maatschappijen = sorted(df["maatschappij"].dropna().unique())
    gekozen_maatschappijen = st.sidebar.multiselect(
        "Maatschappij",
        maatschappijen,
        default=maatschappijen[:10] if len(maatschappijen) > 10 else maatschappijen,
    )

    filtered = df[
        df["Jaartal"].isin(gekozen_jaren)
        & df["Country"].isin(gekozen_landen)
        & df["maatschappij"].isin(gekozen_maatschappijen)
    ].copy()
    return filtered


def kpi_cards(df: pd.DataFrame):
    totaal = len(df)
    gemiddelde_vertraging = df["verschil_minuten"].mean()
    mediaan_vertraging = df["verschil_minuten"].median()
    pct_te_laat = (df["status_berekend"] == "Te laat").mean() * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totaal aantal vluchten", f"{totaal:,.0f}".replace(",", "."))
    c2.metric("Gemiddelde vertraging", f"{gemiddelde_vertraging:.1f} min")
    c3.metric("Mediaan vertraging", f"{mediaan_vertraging:.1f} min")
    c4.metric("Percentage te laat", f"{pct_te_laat:.1f}%")


# -----------------------------------------------------------------------------
# Visualisaties losse vluchten AMS - BCN
# -----------------------------------------------------------------------------

def draw_flight_map(df: pd.DataFrame, show_speed: bool):
    kleurkolom = "TRUE AIRSPEED (derived)" if show_speed else "[3d Altitude Ft]"
    legenda = "Snelheid in knots" if show_speed else "Hoogte in ft"

    kaartdata = df.dropna(subset=["[3d Latitude]", "[3d Longitude]", kleurkolom]).copy()
    if kaartdata.empty:
        st.warning("Geen geldige coördinaten gevonden voor deze vlucht.")
        return

    mid_lat = kaartdata["[3d Latitude]"].mean()
    mid_lon = kaartdata["[3d Longitude]"].mean()
    m = folium.Map(location=[mid_lat, mid_lon], zoom_start=5, tiles="CartoDB positron")

    colormap = cm.LinearColormap(
        colors=["yellow", "green", "turquoise", "blue", "purple"],
        vmin=float(kaartdata[kleurkolom].min()),
        vmax=float(kaartdata[kleurkolom].max()),
        caption=legenda,
    )

    coords = list(zip(kaartdata["[3d Latitude]"], kaartdata["[3d Longitude]"], kaartdata[kleurkolom]))
    tijden = kaartdata["Time (secs)"].fillna(0).tolist() if "Time (secs)" in kaartdata else [0] * len(coords)

    for i in range(1, len(coords)):
        start, eind = coords[i - 1], coords[i]
        folium.PolyLine(
            locations=[[start[0], start[1]], [eind[0], eind[1]]],
            color=colormap(start[2]),
            weight=3,
            opacity=0.9,
            tooltip=f"Tijd: {tijden[i]:.0f} sec | {legenda}: {start[2]:.1f}",
        ).add_to(m)

    folium.Marker([coords[0][0], coords[0][1]], popup="Vertrek", tooltip="Vertrek").add_to(m)
    folium.Marker([coords[-1][0], coords[-1][1]], popup="Aankomst", tooltip="Aankomst").add_to(m)
    colormap.add_to(m)
    st_folium(m, width=900, height=550)


def page_vluchten():
    st.title("7 vluchten: vliegprofiel, route, hoogte en snelheid")
    st.write("Deze pagina laat zien hoe individuele vluchten zich gedragen tijdens de reis. Hiermee kun je aantonen dat hoogte en snelheid veranderen per fase van de vlucht.")

    vluchten_data = load_vluchten_data()
    if not vluchten_data:
        st.error("Geen Excelbestanden gevonden. Zet de bestanden `30Flight 1.xlsx` t/m `30Flight 7.xlsx` of `cleaned_30Flight ...xlsx` in dezelfde map als deze app.")
        return

    vlucht_opties = list(vluchten_data.keys())
    geselecteerde_vlucht = st.selectbox("Selecteer een vlucht voor de kaart", vlucht_opties)
    show_speed_map = st.checkbox("Toon snelheid op de kaart in plaats van hoogte")
    draw_flight_map(vluchten_data[geselecteerde_vlucht], show_speed_map)

    st.subheader("Hoogte of snelheid door de tijd")
    keuze = st.selectbox("Welke vluchten wil je vergelijken?", ["ALL"] + vlucht_opties)
    show_speed_line = st.checkbox("Toon snelheid in plaats van hoogte", key="line_speed")

    if keuze == "ALL":
        df_plot = pd.concat(vluchten_data.values(), ignore_index=True)
    else:
        df_plot = vluchten_data[keuze].copy()

    df_plot["Time (hours)"] = df_plot["Time (secs)"] / 3600
    y_col = "TRUE AIRSPEED (derived)" if show_speed_line else "[3d Altitude Ft]"
    y_label = "Snelheid (knots)" if show_speed_line else "Hoogte (ft)"

    fig = px.line(
        df_plot.dropna(subset=["Time (hours)", y_col]),
        x="Time (hours)",
        y=y_col,
        color="vlucht",
        title=f"{y_label} door de tijd",
        labels={"Time (hours)": "Tijd (uren)", y_col: y_label, "vlucht": "Vlucht"},
    )
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Spreiding per vlucht")
    fig_box = px.box(
        pd.concat(vluchten_data.values(), ignore_index=True).dropna(subset=[y_col]),
        x="vlucht",
        y=y_col,
        color="vlucht",
        title=f"Spreiding van {y_label.lower()} per vlucht",
        labels={y_col: y_label, "vlucht": "Vlucht"},
    )
    st.plotly_chart(fig_box, use_container_width=True)


# -----------------------------------------------------------------------------
# Visualisaties luchthaven-dataset
# -----------------------------------------------------------------------------

def page_luchthavens():
    st.title("Luchthavenanalyse: vertraging, punctualiteit en drukte")

    df = load_luchthaven_data()
    df = apply_luchthaven_filters(df)

    if df.empty:
        st.warning("Geen data over na het toepassen van de filters.")
        return

    kpi_cards(df)

    st.markdown("---")
    st.subheader("1. Top 20 drukste luchthavens")
    top_airports = (
        df.groupby(["luchthaven", "City", "Country"])
        .size()
        .reset_index(name="aantal_vluchten")
        .sort_values("aantal_vluchten", ascending=False)
        .head(20)
    )
    fig = px.bar(
        top_airports,
        x="luchthaven",
        y="aantal_vluchten",
        hover_data=["City", "Country"],
        title="Top 20 meest voorkomende luchthavens",
        labels={"luchthaven": "Luchthaven", "aantal_vluchten": "Aantal vluchten"},
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: deze grafiek laat zien waar de meeste vliegactiviteit zit. Dit is belangrijk omdat drukte een mogelijke verklaring kan zijn voor vertraging.")

    st.subheader("2. Gemiddelde vertraging per luchthaven")
    top_delay = (
        df.groupby(["luchthaven", "City"])
        .agg(gemiddelde_vertraging=("verschil_minuten", "mean"), aantal_vluchten=("FLT", "count"))
        .query("aantal_vluchten >= 20")
        .sort_values("gemiddelde_vertraging", ascending=False)
        .head(15)
        .reset_index()
    )
    fig = px.bar(
        top_delay.sort_values("gemiddelde_vertraging"),
        x="gemiddelde_vertraging",
        y="luchthaven",
        orientation="h",
        hover_data=["City", "aantal_vluchten"],
        title="Luchthavens met hoogste gemiddelde vertraging",
        labels={"gemiddelde_vertraging": "Gemiddelde vertraging (minuten)", "luchthaven": "Luchthaven"},
        color="gemiddelde_vertraging",
        color_continuous_scale="Reds",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: hiermee vergelijk je luchthavens op punctualiteit. Een hoog gemiddelde kan wijzen op operationele knelpunten.")

    st.subheader("3. Percentage te laat / op tijd / te vroeg per luchthaven")
    min_vluchten = st.slider("Minimaal aantal vluchten per luchthaven", 10, 500, 50, step=10)
    airport_counts = df.groupby("luchthaven").size()
    selected_airports = airport_counts[airport_counts >= min_vluchten].index
    status_data = (
        df[df["luchthaven"].isin(selected_airports)]
        .groupby(["luchthaven", "status_berekend"])
        .size()
        .reset_index(name="aantal")
    )
    status_data["percentage"] = status_data.groupby("luchthaven")["aantal"].transform(lambda x: x / x.sum() * 100)
    fig = px.bar(
        status_data,
        x="luchthaven",
        y="percentage",
        color="status_berekend",
        title="Percentage vluchten per status per luchthaven",
        labels={"percentage": "Percentage (%)", "luchthaven": "Luchthaven", "status_berekend": "Status"},
        color_discrete_map={"Te laat": "red", "Op tijd": "green", "Te vroeg": "blue", "Onbekend": "gray"},
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: percentages zijn eerlijker dan absolute aantallen, omdat kleine en grote luchthavens zo beter vergelijkbaar worden.")

    st.subheader("4. Verdeling van vertragingen")
    max_abs_delay = st.slider("Toon vertraging tussen -x en +x minuten", 10, 180, 60, step=10)
    delay_filtered = df[df["verschil_minuten"].between(-max_abs_delay, max_abs_delay)]
    fig = px.histogram(
        delay_filtered,
        x="verschil_minuten",
        nbins=60,
        title="Verdeling van vertragingen",
        labels={"verschil_minuten": "Verschil t.o.v. planning (minuten)"},
    )
    fig.add_vline(x=0, line_dash="dash", annotation_text="Planning")
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: je ziet of de meeste vluchten rond de planning liggen en of er uitschieters zijn.")

    st.subheader("5. Boxplot: spreiding van vertraging per maatschappij")
    airline_counts = df.groupby("maatschappij").size().sort_values(ascending=False).head(12).index
    box_data = df[df["maatschappij"].isin(airline_counts)]
    fig = px.box(
        box_data,
        x="maatschappij",
        y="verschil_minuten",
        color="maatschappij",
        title="Spreiding van vertraging per maatschappij",
        labels={"maatschappij": "Maatschappij", "verschil_minuten": "Vertraging (minuten)"},
    )
    fig.update_yaxes(range=[df["verschil_minuten"].quantile(0.02), df["verschil_minuten"].quantile(0.98)])
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: een boxplot laat niet alleen het gemiddelde zien, maar ook stabiliteit, spreiding en uitschieters.")

    st.subheader("6. Trend: gemiddelde vertraging per maand")
    maand_data = (
        df.assign(maand=df["STD"].dt.to_period("M").dt.to_timestamp())
        .groupby("maand")
        .agg(gemiddelde_vertraging=("verschil_minuten", "mean"), aantal_vluchten=("FLT", "count"))
        .reset_index()
    )
    fig = px.line(
        maand_data,
        x="maand",
        y="gemiddelde_vertraging",
        markers=True,
        hover_data=["aantal_vluchten"],
        title="Gemiddelde vertraging per maand",
        labels={"maand": "Maand", "gemiddelde_vertraging": "Gemiddelde vertraging (minuten)"},
    )
    fig.add_hline(y=0, line_dash="dash")
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: hiermee zie je seizoenspatronen en verschillen tussen maanden/jaren.")

    st.subheader("7. Relatie tussen drukte en vertraging")
    scatter_data = (
        df.groupby(["luchthaven", "City", "Country"])
        .agg(aantal_vluchten=("FLT", "count"), gemiddelde_vertraging=("verschil_minuten", "mean"))
        .reset_index()
    )
    fig = px.scatter(
        scatter_data,
        x="aantal_vluchten",
        y="gemiddelde_vertraging",
        size="aantal_vluchten",
        hover_name="luchthaven",
        hover_data=["City", "Country"],
        title="Relatie tussen aantal vluchten en gemiddelde vertraging",
        labels={"aantal_vluchten": "Aantal vluchten", "gemiddelde_vertraging": "Gemiddelde vertraging (minuten)"},
        trendline="ols" if len(scatter_data) >= 3 else None,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: deze grafiek helpt om te onderzoeken of drukte samenhangt met vertraging.")

    st.subheader("8. Kaart van luchthavens")
    map_data = (
        df.groupby(["luchthaven", "City", "Country", "Latitude", "Longitude"])
        .agg(aantal_vluchten=("FLT", "count"), gemiddelde_vertraging=("verschil_minuten", "mean"))
        .reset_index()
    )
    fig = px.scatter_mapbox(
        map_data,
        lat="Latitude",
        lon="Longitude",
        size="aantal_vluchten",
        color="gemiddelde_vertraging",
        hover_name="luchthaven",
        hover_data=["City", "Country", "aantal_vluchten", "gemiddelde_vertraging"],
        zoom=3,
        height=600,
        title="Luchthavens: grootte = drukte, kleur = gemiddelde vertraging",
        color_continuous_scale="RdYlGn_r",
    )
    fig.update_layout(mapbox_style="carto-positron", margin={"r": 0, "t": 40, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: geografische patronen worden duidelijk. De kaart is ook sterk voor de interactieve demo van je Streamlit-app.")

    st.subheader("9. Heatmap: aantal vluchten per luchthaven per jaar")
    heatmap_data = df.pivot_table(index="luchthaven", columns="Jaartal", values="FLT", aggfunc="count", fill_value=0)
    heatmap_data = heatmap_data.loc[heatmap_data.sum(axis=1).sort_values(ascending=False).head(25).index]
    fig = px.imshow(
        heatmap_data,
        text_auto=True,
        aspect="auto",
        title="Aantal vluchten per luchthaven per jaar",
        labels={"x": "Jaar", "y": "Luchthaven", "color": "Aantal vluchten"},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.info("Aantonen: je vergelijkt jaren en luchthavens in één overzichtelijke visualisatie.")


# -----------------------------------------------------------------------------
# Analyse & advies
# -----------------------------------------------------------------------------

def page_analyse_advies():
    st.title("Storytelling: conclusie en advies")
    df = load_luchthaven_data()

    st.header("Vraagstelling")
    st.write("Welke luchthavens en maatschappijen presteren minder goed op punctualiteit, en lijkt drukte samen te hangen met vertraging?")

    st.header("Belangrijkste bevindingen uit de data")
    airport_summary = (
        df.groupby(["luchthaven", "City"])
        .agg(aantal_vluchten=("FLT", "count"), gemiddelde_vertraging=("verschil_minuten", "mean"), pct_te_laat=("status_berekend", lambda s: (s == "Te laat").mean() * 100))
        .query("aantal_vluchten >= 50")
        .sort_values("gemiddelde_vertraging", ascending=False)
        .reset_index()
    )

    airline_summary = (
        df.groupby("maatschappij")
        .agg(aantal_vluchten=("FLT", "count"), gemiddelde_vertraging=("verschil_minuten", "mean"), pct_te_laat=("status_berekend", lambda s: (s == "Te laat").mean() * 100))
        .query("aantal_vluchten >= 50")
        .sort_values("pct_te_laat", ascending=False)
        .reset_index()
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Luchthavens met hoogste gemiddelde vertraging")
        st.dataframe(airport_summary.head(10), use_container_width=True)
    with c2:
        st.subheader("Maatschappijen met hoogste percentage te laat")
        st.dataframe(airline_summary.head(10), use_container_width=True)

    st.header("Advies aan stakeholder")
    st.success(
        "Focus op de luchthavens en maatschappijen met zowel veel vluchten als hoge vertraging. "
        "Daar is de impact het grootst. Gebruik het dashboard om eerst patronen te vinden en daarna gerichte oorzaakanalyse te doen."
    )

    st.header("Waarom deze visualisaties goed zijn voor VA")
    st.write(
        "De app combineert KPI's, bar charts, histogrammen, boxplots, trendgrafieken, scatterplots, heatmaps en kaarten. "
        "Daardoor vertel je een compleet verhaal: eerst overzicht, daarna vergelijking, daarna verdieping en uiteindelijk advies."
    )


# -----------------------------------------------------------------------------
# Intro
# -----------------------------------------------------------------------------

def page_intro():
    st.title("Eindpresentatie Visual Analytics ✈️")
    st.subheader("Dashboard voor vluchten en luchthavens")
    st.write(
        "In deze Streamlit-app kruip je in de rol van data-analist. "
        "Je onderzoekt vluchtprofielen, luchthavenprestaties, vertragingen en drukte."
    )

    c1, c2, c3 = st.columns(3)
    c1.info("Begin: onderzoeksvraag en context")
    c2.info("Midden: interactieve analyse en visualisaties")
    c3.info("Eind: conclusie en advies")

    st.markdown("### Aanbevolen verhaal voor je presentatie")
    st.write(
        "Start met de vraag of drukte en luchthaven/maatschappij invloed hebben op punctualiteit. "
        "Laat daarna KPI's en grafieken zien. Eindig met een advies: richt verbeteracties op locaties met hoge vertraging én veel vluchten."
    )

    st.markdown("### Gebruikte technieken")
    st.write("Streamlit, Pandas, Plotly, Folium en interactieve filters.")


# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------

selected = show_sidebar_menu()

if selected == "Intro":
    page_intro()
elif selected == "Vluchten":
    page_vluchten()
elif selected == "Luchthavens":
    page_luchthavens()
elif selected == "Analyse & Advies":
    page_analyse_advies()
