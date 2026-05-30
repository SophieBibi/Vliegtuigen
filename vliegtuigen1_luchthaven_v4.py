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

APP_NAME = "vliegtuigen1_luchthaven_v4"
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
    "primary": "#1F4E79",
    "secondary": "#4F81BD",
    "accent": "#F28E2B",
    "light": "#EAF2F8",
    "dark": "#17324D",
    "gray": "#6B7280",
    "danger": "#E15759",
    "te_laat": "#E15759",
    "op_tijd": "#59A14F",
    "te_vroeg": "#4E79A7",
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
        .main {{background-color: #F7FAFC;}}
        h1, h2, h3 {{color: {KLEUREN['dark']};}}
        [data-testid="stMetric"] {{
            background-color: white;
            border: 1px solid #D9E2EC;
            padding: 18px;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(31, 78, 121, 0.08);
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #17324D 0%, #1F4E79 100%);
        }}
        [data-testid="stSidebar"] * {{color: white;}}
        .stMultiSelect label, .stSelectbox label, .stSlider label {{font-weight: 600;}}
        .block-container {{padding-top: 2rem;}}
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
        st.caption(f"App-bestand: `{APP_NAME}.py`")

        opties = ["Intro", "Vluchten", "Vertragingen"]
        if option_menu:
            return option_menu(
                menu_title=None,
                options=opties,
                icons=["play", "airplane", "clock-history"],
                menu_icon="list",
                default_index=0,
                styles={
                    "container": {"background-color": "transparent"},
                    "icon": {"color": "white", "font-size": "18px"},
                    "nav-link": {"color": "white", "font-size": "15px", "margin": "2px"},
                    "nav-link-selected": {"background-color": KLEUREN["accent"]},
                },
            )
        return st.radio("Menu", opties)


def apply_vertraging_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.markdown("## Filters")

    jaren = sorted([int(j) for j in df["Jaartal"].dropna().unique()])
    gekozen_jaren = st.sidebar.multiselect("Jaar", jaren, default=jaren)

    landen = sorted(df["Country"].dropna().unique())
    gekozen_landen = st.sidebar.multiselect("Land", landen, default=landen)

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
        & df["Country"].isin(gekozen_landen)
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

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totaal aantal vluchten", f"{totaal:,.0f}".replace(",", "."))
    c2.metric("Gemiddelde vertraging", f"{gemiddelde_vertraging:.1f} min")
    c3.metric("Percentage te laat", f"{pct_te_laat:.1f}%")
    c4.metric("Drukste luchthaven", drukste_luchthaven)


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

    # 3. Status per luchthaven
    st.subheader("2. Percentage te laat / op tijd / te vroeg per luchthaven")
    min_vluchten = st.slider("Minimaal aantal vluchten per luchthaven", 10, 500, 50, step=10)
    airport_counts = df.groupby("luchthaven_label").size()
    selected_airports = airport_counts[airport_counts >= min_vluchten].index

    status_data = (
        df[df["luchthaven_label"].isin(selected_airports)]
        .groupby(["luchthaven_label", "status_berekend"])
        .size()
        .reset_index(name="aantal")
    )
    status_data["percentage"] = status_data.groupby("luchthaven_label")["aantal"].transform(lambda x: x / x.sum() * 100)

    fig = px.bar(
        status_data,
        x="luchthaven_label",
        y="percentage",
        color="status_berekend",
        title="Percentage vluchten per status per luchthaven",
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

    # 8. Kaart van luchthavens
    st.subheader("5. Kaart van luchthavens")

    map_data = (
        df.groupby(["luchthaven_label", "luchthaven_naam", "ICAO", "Country", "Latitude", "Longitude"], dropna=False)
        .agg(
            aantal_vluchten=("FLT", "count"),
            gemiddelde_vertraging=("verschil_minuten", "mean")
        )
        .reset_index()
        .dropna(subset=["Latitude", "Longitude"])
    )

    if map_data.empty:
        st.warning("Geen kaartdata beschikbaar: Latitude/Longitude ontbreken na filtering.")
    else:
        # Terug naar de kaart-aanpak uit vliegtuigen1.py, omdat die bij jou werkte.
        # Alleen de schaal en het contrast zijn iets aangepast.
        fig = px.scatter_mapbox(
            map_data,
            lat="Latitude",
            lon="Longitude",
            size="aantal_vluchten",
            color="gemiddelde_vertraging",
            hover_name="luchthaven_label",
            hover_data={
                "Country": True,
                "aantal_vluchten": True,
                "gemiddelde_vertraging": ":.2f",
                "Latitude": False,
                "Longitude": False,
            },
            zoom=3,
            height=650,
            title="Luchthavens: grootte = aantal vluchten, kleur = gemiddelde vertraging",
            color_continuous_scale="RdYlGn_r",
            labels={
                "gemiddelde_vertraging": "Gem. vertraging (min)",
                "aantal_vluchten": "Aantal vluchten",
            },
            size_max=45,
            opacity=0.88,
        )

        fig.update_layout(
            mapbox_style="carto-positron",
            mapbox=dict(
                center=dict(lat=52, lon=8),
                zoom=3,
            ),
            margin={"r": 0, "t": 60, "l": 0, "b": 0},
            coloraxis_colorbar=dict(
                title="Gem. vertraging<br>(min)",
                thickness=22,
                len=0.82,
            ),
        )

        fig.update_traces(
            marker=dict(
                sizemode="area",
                sizemin=7,
                line=dict(width=1, color="white"),
            )
        )

        st.plotly_chart(fig, use_container_width=True)

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
