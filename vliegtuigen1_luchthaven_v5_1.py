# vliegtuigen1_nieuw.py
# Streamlit dashboard voor de eindpresentatie Visual Analytics

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import folium
import branca.colormap as cm
from streamlit_folium import st_folium

try:
    from streamlit_option_menu import option_menu
except ImportError:
    option_menu = None

APP_NAME = "vliegtuigen1_luchthaven_v5_1"
LUC_DATA_FILE = "luchthaven_data_4.xlsx"

st.set_page_config(
    page_title="Presentatie Visual Analytics",
    page_icon="✈️",
    layout="wide"
)

# -----------------------------------------------------------------------------
# Vaste stijl en kleuren
# -----------------------------------------------------------------------------

KLEUREN = {
    "primary": "#5BB7E5",        # lichtblauw voor geselecteerde knoppen en filters
    "primary_dark": "#1F6F9C",
    "primary_soft": "#DDF2FC",
    "secondary": "#8ECDEB",
    "accent": "#F4A261",
    "background": "#FFFFFF",
    "card": "#FFFFFF",
    "dark": "#1F2937",
    "gray": "#6B7280",
    "border": "#D8E2EA",
    "danger": "#E76F51",
    "te_laat": "#E76F51",
    "op_tijd": "#2A9D8F",
    "te_vroeg": "#457B9D",
}

STATUS_KLEUREN = {
    "Te laat": KLEUREN["te_laat"],
    "Op tijd": KLEUREN["op_tijd"],
    "Te vroeg": KLEUREN["te_vroeg"],
    "Onbekend": KLEUREN["gray"],
}

PLOTLY_TEMPLATE = "plotly_white"

st.markdown(
    f"""
    <style>
        .stApp {{
            background: #FFFFFF;
        }}
        .block-container {{padding-top: 2rem; padding-bottom: 3rem;}}
        h1, h2, h3 {{color: {KLEUREN['dark']}; font-weight: 750;}}
        [data-testid="stSidebar"] {{
            background: #FFFFFF;
            border-right: 1px solid {KLEUREN['border']};
        }}
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span {{
            color: {KLEUREN['dark']} !important;
        }}
        [data-testid="stMetric"] {{
            background-color: {KLEUREN['card']};
            border: 1px solid {KLEUREN['border']};
            padding: 16px;
            border-radius: 16px;
            box-shadow: 0 4px 14px rgba(42, 92, 127, 0.08);
            min-height: 118px;
        }}
        [data-testid="stMetricValue"] {{
            font-size: 1.55rem !important;
            line-height: 1.25 !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }}
        [data-testid="stMetricLabel"] {{
            font-size: 0.95rem !important;
            color: {KLEUREN['gray']} !important;
        }}
        div[data-testid="stMetric"]:has(div[data-testid="stMetricLabel"]:contains("Drukste luchthaven")) div[data-testid="stMetricValue"] {{
            font-size: 1.05rem !important;
        }}
        .stMultiSelect label, .stSelectbox label {{font-weight: 650;}}
        div[data-baseweb="tag"] {{
            background-color: {KLEUREN['primary_soft']} !important;
            color: {KLEUREN['primary_dark']} !important;
            border: 1px solid {KLEUREN['primary']} !important;
        }}
        div[data-baseweb="select"] > div {{
            border-color: {KLEUREN['primary']} !important;
        }}
        .stSlider [data-baseweb="slider"] div[role="slider"] {{
            background-color: {KLEUREN['primary']} !important;
        }}
        .drukste-card {{
            background-color: {KLEUREN['card']};
            border: 1px solid {KLEUREN['border']};
            padding: 16px;
            border-radius: 16px;
            box-shadow: 0 4px 14px rgba(42, 92, 127, 0.08);
            min-height: 118px;
        }}
        .drukste-label {{
            color: {KLEUREN['gray']};
            font-size: 0.95rem;
            margin-bottom: 10px;
        }}
        .drukste-value {{
            color: {KLEUREN['dark']};
            font-size: 1.03rem;
            font-weight: 400;
            line-height: 1.22;
            overflow-wrap: anywhere;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Data laden
# -----------------------------------------------------------------------------

@st.cache_data
def load_luchthaven_data(path: str = LUC_DATA_FILE) -> pd.DataFrame:
    """Laadt en schoont de luchthaven-dataset."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset niet gevonden: {path}")

    df = pd.read_excel(path)

    # Oude indexkolommen verwijderen als ze toch aanwezig zijn
    drop_cols = [c for c in ["Unnamed: 0", "Unnamed: 0.1"] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    # Datatypes goed zetten
    df["STD"] = pd.to_datetime(df["STD"], errors="coerce")
    df["Latitude"] = pd.to_numeric(df["Latitude"].astype(str).str.replace(",", "."), errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"].astype(str).str.replace(",", "."), errors="coerce")
    df["verschil_minuten"] = pd.to_numeric(df["verschil_minuten"], errors="coerce")
    df["Jaartal"] = pd.to_numeric(df["Jaartal"], errors="coerce")

    # Controle op volledige namen. Als de kolommen ontbreken, maak ze alsnog aan.
    if "luchthaven_naam" not in df.columns:
        df["luchthaven_naam"] = df.get("City", df.get("ICAO", "Onbekend"))
    if "maatschappij_naam" not in df.columns:
        df["maatschappij_naam"] = df.get("maatschappij", "Onbekend")

    # Labels met code + volledige naam. Handig voor filters en grafieken.
    df["luchthaven_label"] = (
        df["luchthaven_naam"].fillna(df["City"]).astype(str)
        + " ("
        + df["ICAO"].fillna("").astype(str)
        + ")"
    )
    df["maatschappij_label"] = (
        df["maatschappij_naam"].fillna(df["maatschappij"]).astype(str)
        + " ("
        + df["maatschappij"].fillna("").astype(str)
        + ")"
    )

    # Status opnieuw bepalen op basis van verschil_minuten.
    # Negatief = te vroeg, 0 t/m 5 minuten = op tijd, meer dan 5 = te laat.
    df["status_berekend"] = np.select(
        [
            df["verschil_minuten"] < 0,
            df["verschil_minuten"].between(0, 5, inclusive="both"),
            df["verschil_minuten"] > 5,
        ],
        ["Te vroeg", "Op tijd", "Te laat"],
        default="Onbekend",
    )

    df = df.dropna(subset=["STD", "verschil_minuten", "Latitude", "Longitude"])
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
        verplichte_kolommen = [
            "[3d Latitude]",
            "[3d Longitude]",
            "[3d Altitude Ft]",
            "TRUE AIRSPEED (derived)",
            "Time (secs)",
        ]
        for kolom in verplichte_kolommen:
            if kolom in df.columns:
                df[kolom] = pd.to_numeric(df[kolom], errors="coerce")

        df = df.dropna(subset=["[3d Latitude]", "[3d Longitude]"])
        df["vlucht"] = vluchtnaam
        vluchten[vluchtnaam] = df

    return vluchten

# -----------------------------------------------------------------------------
# Menu en filters
# -----------------------------------------------------------------------------

def show_sidebar_menu():
    with st.sidebar:
        st.markdown("## Menu")
        opties = ["Intro", "Vluchten", "Vertragingen"]
        if option_menu:
            return option_menu(
                menu_title=None,
                options=opties,
                icons=["play", "airplane", "clock-history"],
                menu_icon="list",
                default_index=0,
                styles={
                    "container": {"background-color": "transparent", "padding": "0!important"},
                    "icon": {"color": KLEUREN["primary_dark"], "font-size": "18px"},
                    "nav-link": {
                        "color": KLEUREN["dark"],
                        "font-size": "15px",
                        "margin": "4px 0px",
                        "border-radius": "10px",
                        "padding": "10px 12px",
                    },
                    "nav-link-selected": {
                        "background-color": KLEUREN["primary_soft"],
                        "color": KLEUREN["primary_dark"],
                        "font-weight": "700",
                    },
                },
            )
        return st.radio("Menu", opties)


def apply_vertraging_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.markdown("## Filters")

    jaren = sorted([int(j) for j in df["Jaartal"].dropna().unique()])
    gekozen_jaren = st.sidebar.multiselect("Jaar", jaren, default=jaren)

    luchthavens = sorted(df["luchthaven_label"].dropna().unique())
    default_luchthavens = luchthavens[:20] if len(luchthavens) > 20 else luchthavens
    gekozen_luchthavens = st.sidebar.multiselect(
        "Luchthaven",
        luchthavens,
        default=default_luchthavens,
        help="Volledige luchthavennaam met ICAO-code tussen haakjes.",
    )

    maatschappijen = sorted(df["maatschappij_label"].dropna().unique())
    default_maatschappijen = maatschappijen[:15] if len(maatschappijen) > 15 else maatschappijen
    gekozen_maatschappijen = st.sidebar.multiselect(
        "Luchtvaartmaatschappij",
        maatschappijen,
        default=default_maatschappijen,
        help="Volledige maatschappijnamen met code tussen haakjes.",
    )

    filtered = df[
        df["Jaartal"].isin(gekozen_jaren)
        & df["luchthaven_label"].isin(gekozen_luchthavens)
        & df["maatschappij_label"].isin(gekozen_maatschappijen)
    ].copy()
    return filtered


def style_fig(fig):
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        title_font=dict(size=22, color=KLEUREN["dark"]),
        font=dict(size=13, color="#263238"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=70, b=40),
        hoverlabel=dict(bgcolor="white", font_size=13),
        legend_title_text="",
    )
    return fig

# -----------------------------------------------------------------------------
# Pagina Intro
# -----------------------------------------------------------------------------

def page_intro():
    st.title("Presentatie Visual Analytics")

# -----------------------------------------------------------------------------
# Pagina Vluchten: behouden zoals eerdere app
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
        colors=["#F2C94C", "#59A14F", "#4E79A7", "#1F4E79", "#6F4E7C"],
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
        color_discrete_sequence=[KLEUREN["primary"], KLEUREN["accent"], "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1"],
    )
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style_fig(fig), use_container_width=True)

    st.subheader("Spreiding per vlucht")
    fig_box = px.box(
        pd.concat(vluchten_data.values(), ignore_index=True).dropna(subset=[y_col]),
        x="vlucht",
        y=y_col,
        color="vlucht",
        title=f"Spreiding van {y_label.lower()} per vlucht",
        labels={y_col: y_label, "vlucht": "Vlucht"},
        color_discrete_sequence=[KLEUREN["primary"], KLEUREN["accent"], "#59A14F", "#E15759", "#76B7B2", "#EDC948", "#B07AA1"],
    )
    st.plotly_chart(style_fig(fig_box), use_container_width=True)

# -----------------------------------------------------------------------------
# Pagina Vertragingen
# -----------------------------------------------------------------------------

def kpi_cards(df: pd.DataFrame):
    totaal = len(df)
    gemiddelde_vertraging = df["verschil_minuten"].mean()
    pct_te_laat = (df["status_berekend"] == "Te laat").mean() * 100

    drukste_luchthaven = "-"
    if not df.empty:
        drukste_luchthaven = df["luchthaven_naam"].value_counts().idxmax()

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.35])
    c1.metric("Totaal aantal vluchten", f"{totaal:,.0f}".replace(",", "."))
    c2.metric("Gemiddelde vertraging", f"{gemiddelde_vertraging:.1f} min")
    c3.metric("Percentage te laat", f"{pct_te_laat:.1f}%")
    with c4:
        st.markdown(
            f"""
            <div class="drukste-card">
                <div class="drukste-label">Drukste luchthaven</div>
                <div class="drukste-value">{drukste_luchthaven}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def page_vertragingen():
    st.title("Vertragingen")

    try:
        df = load_luchthaven_data()
    except FileNotFoundError as e:
        st.error(str(e))
        return

    df = apply_vertraging_filters(df)

    if df.empty:
        st.warning("Geen data over na het toepassen van de filters.")
        return

    kpi_cards(df)
    st.markdown("---")

    # 1. Meest voorkomende luchthavens
    st.subheader("1. Top 20 meest voorkomende luchthavens")
    top_airports = (
        df.groupby(["luchthaven_label", "luchthaven_naam", "ICAO", "Country"])
        .size()
        .reset_index(name="aantal_vluchten")
        .sort_values("aantal_vluchten", ascending=False)
        .head(20)
    )
    fig = px.bar(
        top_airports,
        x="luchthaven_label",
        y="aantal_vluchten",
        hover_data=["Country"],
        title="Top 20 meest voorkomende luchthavens",
        labels={"luchthaven_label": "Luchthaven", "aantal_vluchten": "Aantal vluchten"},
        color_discrete_sequence=[KLEUREN["primary"]],
    )
    fig.update_layout(xaxis_tickangle=-35)
    st.plotly_chart(style_fig(fig), use_container_width=True)

    # 2. Status per luchthaven: top 10 op basis van gekozen status
    st.subheader("2. Percentage te laat / op tijd / te vroeg per luchthaven")

    sorteer_optie = st.selectbox(
        "Welke top 10 wil je tonen?",
        [
            "Hoogste percentage te laat",
            "Hoogste percentage op tijd",
            "Hoogste percentage te vroeg",
        ],
        index=0,
    )
    status_focus = {
        "Hoogste percentage te laat": "Te laat",
        "Hoogste percentage op tijd": "Op tijd",
        "Hoogste percentage te vroeg": "Te vroeg",
    }[sorteer_optie]

    status_counts = (
        df.groupby(["luchthaven_label", "status_berekend"])
        .size()
        .reset_index(name="aantal")
    )
    total_per_airport = status_counts.groupby("luchthaven_label")["aantal"].transform("sum")
    status_counts["percentage"] = status_counts["aantal"] / total_per_airport * 100

    top10_luchthavens = (
        status_counts[status_counts["status_berekend"] == status_focus]
        .sort_values("percentage", ascending=False)
        .head(10)["luchthaven_label"]
        .tolist()
    )

    status_data = status_counts[status_counts["luchthaven_label"].isin(top10_luchthavens)].copy()
    status_data["luchthaven_label"] = pd.Categorical(
        status_data["luchthaven_label"],
        categories=top10_luchthavens,
        ordered=True,
    )
    status_data = status_data.sort_values("luchthaven_label")

    fig = px.bar(
        status_data,
        x="luchthaven_label",
        y="percentage",
        color="status_berekend",
        title=f"Top 10 luchthavens op basis van {status_focus.lower()}",
        labels={"percentage": "Percentage (%)", "luchthaven_label": "Luchthaven", "status_berekend": "Status"},
        color_discrete_map=STATUS_KLEUREN,
        category_orders={"status_berekend": ["Te laat", "Op tijd", "Te vroeg", "Onbekend"]},
    )
    fig.update_layout(barmode="stack", xaxis_tickangle=-35)
    st.plotly_chart(style_fig(fig), use_container_width=True)

    # 5. Boxplot maatschappij
    st.subheader("3. Boxplot: spreiding van vertraging per maatschappij")
    top_n_airlines = st.slider("Aantal maatschappijen in boxplot", 5, 20, 12)
    airline_counts = df.groupby("maatschappij_label").size().sort_values(ascending=False).head(top_n_airlines).index
    box_data = df[df["maatschappij_label"].isin(airline_counts)].copy()

    fig = px.box(
        box_data,
        x="maatschappij_label",
        y="verschil_minuten",
        color="maatschappij_label",
        title="Spreiding van vertraging per luchtvaartmaatschappij",
        labels={"maatschappij_label": "Luchtvaartmaatschappij", "verschil_minuten": "Vertraging (minuten)"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    if len(box_data) > 0:
        fig.update_yaxes(range=[box_data["verschil_minuten"].quantile(0.02), box_data["verschil_minuten"].quantile(0.98)])
    fig.update_layout(xaxis_tickangle=-35, showlegend=False)
    st.plotly_chart(style_fig(fig), use_container_width=True)

    # 6. Trend gemiddelde vertraging per maand
    st.subheader("4. Trend: gemiddelde vertraging per maand")
    maand_data = (
        df.assign(maand=df["STD"].dt.to_period("M").dt.to_timestamp())
        .groupby("maand")
        .agg(gemiddelde_vertraging=("verschil_minuten", "mean"), aantal_vluchten=("FLT", "count"))
        .reset_index()
        .sort_values("maand")
    )
    fig = px.line(
        maand_data,
        x="maand",
        y="gemiddelde_vertraging",
        markers=True,
        hover_data={"aantal_vluchten": True, "maand": "|%b %Y", "gemiddelde_vertraging": ":.2f"},
        title="Gemiddelde vertraging per maand",
        labels={"maand": "Maand", "gemiddelde_vertraging": "Gemiddelde vertraging (minuten)"},
        color_discrete_sequence=[KLEUREN["accent"]],
    )
    fig.add_hline(y=0, line_dash="dash", line_color=KLEUREN["gray"])
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style_fig(fig), use_container_width=True)

# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------

selected = show_sidebar_menu()

if selected == "Intro":
    page_intro()
elif selected == "Vluchten":
    page_vluchten()
elif selected == "Vertragingen":
    page_vertragingen()
