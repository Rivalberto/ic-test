import streamlit as st
import numpy as np

# Funzione per calcolare e_s secondo Tetens
def es_tetens(T_c):
    return 6.112 * np.exp((17.62 * T_c) / (243.12 + T_c))  # hPa

# Funzione per calcolare rapporto di mescolanza (g/kg)
def mixing_ratio_g_per_kg(T_c, RH, p_hPa=1013.25):
    es = es_tetens(T_c)
    e = (RH / 100.0) * es  # hPa
    w = 0.622 * e / (p_hPa - e)  # kg vap/kg aria secca
    return w * 1000.0  # g/kg

st.title("Calcolatore rapporto tra rapporti di mescolanza")

# Input utente
T_int = st.number_input("Temperatura interna (°C)", value=22.0)
RH_int = st.number_input("Umidità relativa interna (%)", value=50.0)
T_ext = st.number_input("Temperatura esterna (°C)", value=5.0)
RH_ext = st.number_input("Umidità relativa esterna (%)", value=80.0)
P_atm = st.number_input("Pressione atmosferica (hPa)", value=1013.25)

# Calcolo rapporti di mescolanza
w_int = mixing_ratio_g_per_kg(T_int, RH_int, P_atm)
w_ext = mixing_ratio_g_per_kg(T_ext, RH_ext, P_atm)

# Evita divisione per zero
if w_ext != 0:
    ratio = w_int / w_ext
else:
    ratio = np.nan

# Output risultati
st.subheader("Risultati")
st.write(f"Rapporto di mescolanza interno: {w_int:.2f} g/kg")
st.write(f"Rapporto di mescolanza esterno: {w_ext:.2f} g/kg")
st.write(f"Rapporto (interno / esterno): {ratio:.2f}")

# Suggerimento ventilazione
if np.isnan(ratio):
    st.warning("Il rapporto di mescolanza esterno è zero: dati non validi.")
elif w_ext < w_int:
    st.success("L'aria esterna è più secca: aprire le finestre ridurrà l'umidità interna.")
elif w_ext > w_int:
    st.error("L'aria esterna è più umida: aprendo le finestre l'umidità interna aumenterà.")
else:
    st.info("L'aria esterna e interna hanno la stessa umidità specifica.")
