import streamlit as st
import numpy as np
#import matplotlib.pyplot as plt

# Funzioni per calcoli umidità
def es_tetens(T_c):
    return 6.112 * np.exp((17.62 * T_c) / (243.12 + T_c))  # hPa

def mixing_ratio_g_per_kg(T_c, RH, p_hPa=1013.25):
    es = es_tetens(T_c)
    e = (RH / 100.0) * es  # hPa
    w = 0.622 * e / (p_hPa - e)  # kg vap/kg aria secca
    return w * 1000.0  # g/kg

def dew_point(T_c, RH):
    es = es_tetens(T_c)
    e = (RH / 100.0) * es
    ln_ratio = np.log(e / 6.112)
    Td = (243.12 * ln_ratio) / (17.62 - ln_ratio)
    return Td

st.title("Calcolatore confronto rapporti di mescolanza e punto di rugiada")

# Input utente
T_int = st.number_input("Temperatura interna (°C)", value=22.0)
RH_int = st.number_input("Umidità relativa interna (%)", value=50.0)
T_ext = st.number_input("Temperatura esterna (°C)", value=5.0)
RH_ext = st.number_input("Umidità relativa esterna (%)", value=80.0)
P_atm = st.number_input("Pressione atmosferica (hPa)", value=1013.25)

# Calcoli principali
w_int = mixing_ratio_g_per_kg(T_int, RH_int, P_atm)
w_ext = mixing_ratio_g_per_kg(T_ext, RH_ext, P_atm)
Td_int = dew_point(T_int, RH_int)
Td_ext = dew_point(T_ext, RH_ext)

ratio = w_int / w_ext if w_ext != 0 else np.nan

# Output
st.subheader("Risultati")
st.write(f"Rapporto di mescolanza interno: {w_int:.2f} g/kg")
st.write(f"Rapporto di mescolanza esterno: {w_ext:.2f} g/kg")
st.write(f"Rapporto (interno / esterno): {ratio:.2f}")
st.write(f"Punto di rugiada interno: {Td_int:.2f} °C")
st.write(f"Punto di rugiada esterno: {Td_ext:.2f} °C")

# Indicatore visivo testuale e colore per grafico
if np.isnan(ratio):
    verdict = "Dati non validi"
    verdict_color = 'gray'
    st.warning("Il rapporto di mescolanza esterno è zero: dati non validi.")
elif w_ext < w_int:
    verdict = "Apri"
    verdict_color = 'green'
    st.success("✅ L'aria esterna è più secca: aprendo le finestre ridurrai l'umidità interna.")
elif w_ext > w_int:
    verdict = "Chiudi"
    verdict_color = 'red'
    st.error("❌ L'aria esterna è più umida: aprendo le finestre aumenterai l'umidità interna.")
else:
    verdict = "Uguale"
    verdict_color = 'blue'
    st.info("ℹ️ L'aria esterna e interna hanno la stessa umidità specifica.")

# Grafico dinamico del rapporto di mescolanza
#RH_values = [20, 40, 60, 80, 100]
#T_range = np.linspace(-10, 40, 200)
#plt.figure(figsize=(8,5))
#for rh in RH_values:
#    w_curve = mixing_ratio_g_per_kg(T_range, rh, P_atm)
#    plt.plot(T_range, w_curve, label=f"RH {rh}%")

# Linee verticali per interno ed esterno
#plt.axvline(T_int, color='red', linestyle='--', label="T interna")
#plt.axvline(T_ext, color='blue', linestyle='--', label="T esterna")

# Punto evidenziato per interno/esterno
#plt.scatter([T_int], [w_int], color=verdict_color, s=100, zorder=5, label="Interno")
#plt.scatter([T_ext], [w_ext], color=verdict_color, s=100, zorder=5, marker='x', label="Esterno")

#plt.xlabel("Temperatura (°C)")
#plt.ylabel("Rapporto di mescolanza (g/kg)")
#plt.title(f"Rapporto di mescolanza vs Temperatura — {verdict}")
#plt.grid(True)
#plt.legend()
#st.pyplot(plt)
