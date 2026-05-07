import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import numpy as np
import folium
import branca.colormap as cm
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from folium.plugins import HeatMap

st.set_page_config(page_title='Case 3 Vluchten (groep 3)', page_icon='✈️')

# Sidebar met verbeterde menu-opties
with st.sidebar: 
    selected = option_menu(
        menu_title="Menu", 
        options=["Intro", "Vluchten", "Luchthavens"], 
        icons=["play", "airplane", "bezier"], 
        menu_icon="list"
    )

# Functie voor laden van vluchten data
@st.cache_data
def load_vluchten_data():
    vluchten_data = {
        f'vlucht {i}': pd.read_excel(f'cleaned_30Flight {i}.xlsx') 
        for i in range(1, 8)
    }
    return vluchten_data

# Functie voor het tekenen van de kaart
def draw_flight_map(df):
    mid_lat, mid_lon = df['[3d Latitude]'].mean(), df['[3d Longitude]'].mean()
    m = folium.Map(location=[mid_lat, mid_lon], zoom_start=5, tiles='CartoDB positron')
    colormap = cm.LinearColormap(
        colors=['yellow', 'green', 'turquoise', 'blue', 'purple'], 
        index=[0, 10000, 20000, 30000, 40000],
        vmin=df['[3d Altitude Ft]'].min(), 
        vmax=df['[3d Altitude Ft]'].max(),
        caption='Hoogte in ft.'
    )

    coordinates = list(zip(df['[3d Latitude]'], df['[3d Longitude]'], df['[3d Altitude Ft]']))
    for i in range(1, len(coordinates)):
        start, end = coordinates[i-1], coordinates[i]
        color = colormap(start[2])
        folium.PolyLine(
            locations=[[start[0], start[1]], [end[0], end[1]]],
            color=color, weight=2.5, opacity=1,
            tooltip=f"Time: {df['Time (secs)'].iloc[i]} sec, Altitude: {df['[3d Altitude Ft]'].iloc[i]} ft, Speed: {df['TRUE AIRSPEED (derived)'].iloc[i]}"
        ).add_to(m)

    folium.Marker(location=[df['[3d Latitude]'].iloc[0], df['[3d Longitude]'].iloc[0]],
                  popup="AMSTERDAM (AMS)", tooltip="AMSTERDAM (AMS)").add_to(m)
    folium.Marker(location=[df['[3d Latitude]'].iloc[-1], df['[3d Longitude]'].iloc[-1]],
                  popup="BARCELONA (BCN)", tooltip="BARCELONA (BCN)").add_to(m)
    colormap.add_to(m)
    return m

# INTRO pagina
if selected == 'Intro':
    st.title("Case 3 Vluchten - Groep 3")
    st.write("Welkom bij het vluchten dashboard. Hier krijg je inzicht in vluchtgegevens en luchthavendata.")
    st.write("### Gebruikte Bronnen:")
    st.write("- [Youtube filmpje](https://www.youtube.com/watch?v=hEPoto5xp3k)")
    st.write("- [Streamlit documentatie](https://docs.streamlit.io/)")

# VLUCHTEN pagina
elif selected == "Vluchten": 
    st.title("7 Vluchten (AMS - BCN)") 

    vluchten_data = load_vluchten_data()
    selected_vlucht = st.selectbox("Selecteer een vlucht", options=['ALL'] + [f'vlucht {i}' for i in range(1, 8)])

    if selected_vlucht == 'ALL':
        df1 = pd.concat([df.assign(vlucht=vlucht) for vlucht, df in vluchten_data.items()], ignore_index=True)
    else:
        df1 = vluchten_data[selected_vlucht]
        df1['vlucht'] = selected_vlucht

    # Streamlit kaart weergave met uitleg
    if selected_vlucht != 'ALL':
        st.write("Hieronder zie je de kaart voor de geselecteerde vlucht.")
        map_ = draw_flight_map(df1)
        st_folium(map_, width=700, height=600)
    
    # Grafiek Hoogte vs Tijd met verbeterde kleuren en layout
    df1['Time (hours)'] = df1['Time (secs)'] / 3600
    kleuren_map = {f'vlucht {i}': color for i, color in enumerate(px.colors.qualitative.Plotly, 1)}
    fig = px.line(
        df1, x='Time (hours)', y='[3d Altitude Ft]', title='Hoogte vs Tijd',
        labels={"Time (hours)": "Tijd (uren)", "[3d Altitude Ft]": "Hoogte (ft)"}, color='vlucht', color_discrete_map=kleuren_map
    )
    st.plotly_chart(fig)

# LUCHTHAVENS pagina
elif selected == 'Luchthavens':
    st.title("Luchthavens")
    st.subheader("Top 20 luchthavens")

    # Data inladen en tonen van de top luchthavens
    luchthaven_data = pd.read_csv("DatasetLuchthaven_murged2.csv")
    luchthaven_frequentie = pd.read_csv("luchthaven_frequentie.csv")
    
    fig_luchthavens = px.bar(
        luchthaven_frequentie, x='luchthaven', y='aantal_vluchten', title='Top 20 Meest Voorkomende Luchthavens',
        labels={'luchthaven': 'Luchthaven', 'aantal_vluchten': 'Aantal Vluchten'}, color_discrete_sequence=['blue']
    )
    fig_luchthavens.update_layout(xaxis_title='Luchthaven', yaxis_title='Aantal Vluchten', xaxis_tickangle=-45)
    st.plotly_chart(fig_luchthavens)

    st.subheader("Punctualiteit per luchthaven")
    grouped = luchthaven_data.groupby(['City', 'status']).size().unstack(fill_value=0)
    grouped_percentage = grouped.div(grouped.sum(axis=1), axis=0) * 100
    grouped_percentage_reset = grouped_percentage.reset_index().melt(id_vars='City', value_vars=['Te laat', 'Op tijd', 'Te vroeg'],
                                                                     var_name='status', value_name='percentage')

    fig_punctuality = px.bar(
        grouped_percentage_reset, x='City', y='percentage', color='status',
        title='Percentage vluchten die te laat, op tijd of te vroeg zijn per luchthaven',
        labels={'percentage': 'Percentage (%)', 'City': 'Luchthaven'},
        color_discrete_map={'Te laat': 'red', 'Op tijd': 'green', 'Te vroeg': 'blue'}
    )
    fig_punctuality.update_layout(barmode='stack', xaxis={'categoryorder': 'total descending'})
    st.plotly_chart(fig_punctuality)

    # Extra statistieken over gemiddelde vertraging en vluchtduur per jaar
    st.subheader("Vertraging per jaar")
    gemiddelde_vertraging = luchthaven_data.groupby(['City', 'Jaartal'])['verschil_minuten'].mean().reset_index()
    aantal_vluchten = luchthaven_data.groupby(['City', 'Jaartal']).size().reset_index(name='aantal_vluchten')
    gemiddelde_vertraging = gemiddelde_vertraging.merge(aantal_vluchten, on=['City', 'Jaartal'])

    # Toon vertraging en vluchten per jaar
    jaar_keuze = st.selectbox("Selecteer het jaar", options=["2019", "2020"])
    df_jaar = gemiddelde_vertraging[gemiddelde_vertraging['Jaartal'] == int(jaar_keuze)]
    
    fig_vertraging = px.bar(
        df_jaar, x='City', y='verschil_minuten', title=f'Gemiddelde vertraging van vluchten per luchthaven in {jaar_keuze}',
        labels={'City': 'Luchthaven', 'verschil_minuten': 'Gemiddelde vertraging (minuten)'},
        color='verschil_minuten', text='aantal_vluchten', color_continuous_scale=px.colors.sequential.Plasma
    )
    fig_vertraging.update_traces(textposition='outside')
    st.plotly_chart(fig_vertraging)
