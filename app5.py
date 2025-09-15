
# Source: https://dev.netatmo.com/apidocumentation/oauth
# Notes:
# - Register an app on https://dev.netatmo.com/ (Top right, 'My apps')
# - Device: Home coach

from datetime import datetime, timedelta, timezone, tzinfo
import requests
import streamlit as st
#from streamlit_gsheets import GSheetsConnection
import math
import numpy as np
import csv
import pandas as pd
from io import StringIO
import json

def calculate_A_T(temperature_celsius):
    """
    Calcola la parte esponenziale della funzione di pressione di vapore saturo (A(T)).
    La temperatura deve essere in gradi Celsius.
    """
    return 6.1094 * math.exp((17.625 * temperature_celsius) / (temperature_celsius + 243.04))

def calculate_Pv_from_T_RH(temperature_celsius, relative_humidity_decimal):
    """
    Calcola la pressione di vapore reale (Pv) in hPa da temperatura e umidità relativa.
    """
    if temperature_celsius < -80: # Limite di validità per la formula di Arden Buck
        raise ValueError("Temperatura troppo bassa per la formula di Arden Buck.")
    return relative_humidity_decimal * calculate_A_T(temperature_celsius)

def calculate_dew_point(temperature_celsius, relative_humidity_decimal):
    """
    Calcola il punto di rugiada (Td) in gradi Celsius da temperatura e umidità relativa.
    """
    if not (0 <= relative_humidity_decimal <= 1):
        raise ValueError("L'umidità relativa deve essere tra 0 e 1 (decimale).")

    # Calcola la pressione di vapore reale (Pv)
    pv = calculate_Pv_from_T_RH(temperature_celsius, relative_humidity_decimal)

    # Inverti la formula di Arden Buck per trovare il punto di rugiada
    # Td = (243.04 * ln(Pv / 6.1094)) / (17.625 - ln(Pv / 6.1094))
    try:
        ln_pv_div_const = math.log(pv / 6.1094)
        td = (243.04 * ln_pv_div_const) / (17.625 - ln_pv_div_const)
        return td
    except ValueError:
        # Questo può accadere se pv è 0 o negativo (non fisico)
        # o se il denominatore diventa 0 (condizioni estreme)
        return float('-inf') # Punto di rugiada estremamente basso per aria molto secca

def calculate_absolute_humidity_density(pv_hpa, temperature_celsius):
    """
    Calcola l'umidità assoluta (densità di vapore acqueo) in g/m^3.
    pv_hpa: Pressione di vapore reale in hPa.
    temperature_celsius: Temperatura dell'aria in gradi Celsius.
    """
    # Costante dei gas specifica per il vapore acqueo (J/(kg·K))
    R_v = 461.5 

    # Converte la pressione di vapore da hPa a Pascal (Pa)
    pv_pa = pv_hpa * 100 

    # Converte la temperatura da Celsius a Kelvin
    temperature_kelvin = temperature_celsius + 273.15

    # Calcola la densità di vapore acqueo (kg/m^3)
    # rho_v = Pv / (Rv * T)
    if temperature_kelvin <= 0: # Evita divisione per zero o temperature non fisiche
        return 0.0 # Non è possibile calcolare o vapore non esiste a 0K

    rho_v_kg_per_m3 = pv_pa / (R_v * temperature_kelvin)

    # Converte da kg/m^3 a g/m^3
    rho_v_g_per_m3 = rho_v_kg_per_m3 * 1000

    return rho_v_g_per_m3

def calculate_mixing_ratio_from_pv(pv_hpa, p_atm_hpa):
    """
    Calcola il rapporto di miscela (w) in g/kg da Pv e Patm.
    pv_hpa: Pressione di vapore reale in hPa.
    p_atm_hpa: Pressione atmosferica in hPa.
    """
    if (p_atm_hpa - pv_hpa) <= 0: # Condizione di saturazione o non fisica
        return float('inf') # Rappresenta umidità estremamente alta

    constant_0622 = 0.622 # Rapporto tra peso molecolare vapore acqueo e aria secca
    w_kg_per_kg = (constant_0622 * pv_hpa) / (p_atm_hpa - pv_hpa)
    return w_kg_per_kg * 1000 # Converte a g/kg

def calculate_specific_humidity_from_mixing_ratio(mixing_ratio_g_per_kg):
    """
    Calcola l'umidità specifica (q) in g/kg dal rapporto di miscela (w).
    mixing_ratio_g_per_kg: Rapporto di miscela in g/kg.
    """
    # Converte w da g/kg a kg/kg per il calcolo
    w_kg_per_kg = mixing_ratio_g_per_kg / 1000

    if (1 + w_kg_per_kg) == 0: # Evita divisione per zero
        return float('inf')

    q_kg_per_kg = w_kg_per_kg / (1 + w_kg_per_kg)
    return q_kg_per_kg * 1000 # Converte a g/kg


def should_open_windows_based_on_TRH(
    t_indoor_celsius, rh_indoor_percent,
    t_outdoor_celsius, rh_outdoor_percent,
    p_atm_hpa # La pressione atmosferica viene ora passata come argomento
):
    """
    Determina se è utile aprire le finestre per abbassare l'umidità interna
    basandosi su temperature e umidità relative.
    Restituisce una tupla (True/False, ratio_w_indoor_to_w_outdoor, pv_indoor, pv_outdoor).
    True se l'aria esterna è più secca, False altrimenti.
    ratio_w_indoor_to_w_outdoor è il rapporto w_indoor / w_outdoor.
    pv_indoor e pv_outdoor sono le pressioni di vapore reali.

    t_indoor_celsius: Temperatura interna in gradi Celsius.
    rh_indoor_percent: Umidità relativa interna in percentuale (es. 50 per 50%).
    t_outdoor_celsius: Temperatura esterna in gradi Celsius.
    rh_outdoor_percent: Umidità relativa esterna in percentuale (es. 70 per 70%).
    p_atm_hpa: Pressione atmosferica in hPa.
    """
    rh_indoor_decimal = rh_indoor_percent / 100.0
    rh_outdoor_decimal = rh_outdoor_percent / 100.0

    # Calcola la pressione di vapore reale per l'aria interna ed esterna
    try:
        pv_indoor = calculate_Pv_from_T_RH(t_indoor_celsius, rh_indoor_decimal)
        pv_outdoor = calculate_Pv_from_T_RH(t_outdoor_celsius, rh_outdoor_decimal)
    except ValueError as e:
        print(f"Errore nel calcolo della pressione di vapore: {e}")
        return False, None, None, None # Restituisce False e None per i valori in caso di errore

    # Gestione di casi limite per evitare divisioni per zero o valori non fisici
    if pv_indoor >= p_atm_hpa or pv_outdoor >= p_atm_hpa:
        # Condizioni estreme (saturazione o super-saturazione).
        # In questi casi, l'aria è estremamente umida, e non è utile aprire le finestre.
        return False, float('inf'), pv_indoor, pv_outdoor # Restituisce inf per il ratio se saturo

    # Calcola i termini del rapporto di miscela
    term1_numerator = pv_indoor
    term1_denominator = (p_atm_hpa - pv_indoor)

    term2_numerator = (p_atm_hpa - pv_outdoor)
    term2_denominator = pv_outdoor

    # Evita divisione per zero o valori molto piccoli nel denominatore
    if term1_denominator <= 0 or term2_denominator <= 0:
        return False, None, pv_indoor, pv_outdoor # Condizioni non fisiche o aria interna/esterna satura

    ratio_w_indoor_to_w_outdoor = (term1_numerator / term1_denominator) * \
                                  (term2_numerator / term2_denominator)

    # Restituisce True se l'aria interna è più umida dell'esterna (rapporto > 1)
    return ratio_w_indoor_to_w_outdoor > 1, ratio_w_indoor_to_w_outdoor, pv_indoor, pv_outdoor

# --- Funzione principale per l'interazione con l'utente ---
def main():

    # App credentials
    CLIENT_ID = st.secrets.netatmo.client.id
    CLIENT_SECRET = st.secrets.netatmo.client.secret
    
    #conn = st.connection("gsheets", type=GSheetsConnection)
    #df = conn.read(worksheet="Example 1")

    ##st.dataframe(df)
    
    #for row in df.itertuples():
    #    st.write(f"{row.Access} {row.Refresh} {row.Expiration} {row.Scope}")

    st.session_state['Access'] = st.secrets.netatmo.tokens.access
    st.session_state['Refresh'] = st.secrets.netatmo.tokens.refresh
    st.session_state['Expiration'] = st.secrets.netatmo.tokens.expiration
    st.session_state['Scope'] = st.secrets.netatmo.tokens.scope
    
    #if 'Access' not in st.session_state:
    #    st.session_state['Access'] = 'no_valid'
    #    st.session_state['Expiration'] = 0
    #    st.info('No access token available')
    #if 'Refresh' not in st.session_state:
    #    st.session_state['Refresh'] = ''
    #if 'Expiration' not in st.session_state:
    #    st.session_state['Expiration'] = 0
    #if 'Scope' not in st.session_state:
    #    st.session_state['Scope'] = ['read_station', 'read_homecoach']

    #df = pd.DataFrame({'Access': netatmo_access_token, 'Refresh': netatmo_refresh_token, 'Expiration': token_expiration, 'Scope': token_scope})
    #df.to_csv('out.csv', index=False)
    #st.write(df)    

    URL = 'https://raw.githubusercontent.com/Rivalberto/ic-test/refs/heads/main/tokens.csv'
    response = requests.get(URL)
    if response.status_code == 200:
        tokens = pd.read_csv(StringIO(response.text))
    else:
        st.error("Failed to load data from GitHub.")
        exit()
    
    st.write(response.status_code)
    st.write(response.raw)
    #st.write(response.json())
    st.write(tokens)

    exit()
    
    inputdata = {}
    inputdata["path"] = "tokens.csv"
    inputdata["branch"] = "main"
    inputdata["message"] = "Automated update " + str(datetime.now())
    inputdata["content"] = "ciao"
    #if sha:
        #inputdata["sha"] = str(sha)
    inputdata["sha"] = response['sha']

    github_user = st.secrets.github.user
    github_token = st.secrets.github.token

    URL = "https://api.github.com/repos/Rivalberto/ic-test/contents/tokens.csv"
    response = requests.put(URL, auth=(github_user,github_token), data = json.dumps(inputdata))

    st.write(response.content.decode())

    exit()
    
    if st.session_state['Expiration'] < int(datetime.now(timezone.utc).timestamp()):

        st.info("Requesting a new access token")
        
        # Create payload
        URL = 'https://api.netatmo.com/oauth2/token'
        payload={'grant_type': 'refresh_token',
                 'refresh_token': st.session_state['Refresh'],
                 'client_id': CLIENT_ID,
                 'client_secret': CLIENT_SECRET}
        
        # Create headers
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
        }
        
        ## Make API call
        response = requests.post(url=URL, data=payload, headers=headers)
        #st.write(response.content)
        #st.write(response.status_code)
        
        # Parse response data
        st.session_state['Access'] = response.json()['access_token']
        st.session_state['Refresh'] = response.json()['refresh_token']
        st.session_state['Expiration'] = int(datetime.now(timezone.utc).timestamp())+min(int(response.json()['expires_in']), int(response.json()['expire_in']))-800
        st.session_state['Scope'] = response.json()['scope']

        #st.secrets.netatmo.tokens.access = st.session_state['Access']
        #st.secrets.netatmo.tokens.refresh = st.session_state['Refresh']
        #st.secrets.netatmo.tokens.expiration = st.session_state['Expiration']
        #st.secrets.netatmo.tokens.scope = st.session_state['Scope']
    
    #SCOPE = 'read_homecoach'
    MAC_homecoach = '70:ee:50:3e:c4:de' # MAC address of the device looks like: '21:ff:31:69:2d:19'
    
    #SCOPE = 'read_station'
    MAC_station = '70:ee:50:64:49:34' # MAC address of the device looks like: '21:ff:31:69:2d:19'
    MAC_station_module_ext = '02:00:00:65:33:f2'
    
    date_start = datetime.now(timezone.utc)-timedelta(minutes=59)
    #date_start = int(date_start.replace(tzinfo=None).timestamp())
    date_start = int(date_start.timestamp())
    
    URL = 'https://api.netatmo.com/api/getmeasure'
    
    # Create the header for API call
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {st.session_state['Access']}"
    }
    
    # Create the payload for API call (homecoach)
    params={'device_id': MAC_homecoach,
            'scale': '30min',
            'type': 'temperature,humidity,pressure,co2',
            'date_begin': date_start,
            #'date_end': date_end,
            #'limit': '1024',
            'optimize': 'false',
            'real_time': 'true'}
    #print(params)
    #st.write(params)
    
    # Make API call
    response = requests.get(url=URL, params=params, headers=headers)
    #print(response.content)
    #st.write(response.content)
    
    if 'body' in response.json():
        body = response.json()['body']
    else:
        st.error("Error with the data downloading")
        return
    values_homecoach = dict()
    for key in body:
        values_homecoach["time"] = datetime.fromtimestamp(int(key), tz=timezone.utc).time()
        values_homecoach["temperature"] = body[key][0]
        values_homecoach["humidity"] = body[key][1]
        values_homecoach["pressure"] = body[key][2]
        values_homecoach["co2"] = body[key][3]
        #st.write(f"\nTemperature: {values_homecoach["temperature"]:.2f} °C")
        #st.write(f"\nHumidity: {values_homecoach["humidity"]:.2f} %")
        #st.write(f"\nHumidity: {values_homecoach["pressure"]:.2f} hPa")
        #st.write(f"\nCO2: {values_homecoach["co2"]:.2f} ppm")
    #st.write("Final values:")
    #st.write(values_homecoach)
    
    # Create the payload for API call (station module ext)
    params={'device_id': MAC_station,
            'module_id': MAC_station_module_ext,
            'scale': '30min',
            #'type': 'temperature',
            'type': 'temperature,humidity',
            'date_begin': date_start,
            #'date_end': date_end,
            #'limit': '1024',
            'optimize': 'false',
            'real_time': 'true'}
    #print(params)
    #st.write(params)
    
    response = requests.get(url=URL, params=params, headers=headers)
    #print(response.content)
    #st.write(response.content)

    if 'body' in response.json():
        body = response.json()['body']
    else:
        st.error("Error with the data downloading")
        return
    values_station_ext = dict()
    for key in body:
        values_station_ext["time"] = datetime.fromtimestamp(int(key), tz=timezone.utc).time()
        values_station_ext["temperature"] = body[key][0]
        values_station_ext["humidity"] = body[key][1]
        #st.write(f"\nTemperature: {values_station_ext["temperature"]:.2f} °C")
        #st.write(f"\nHumidity: {values_station_ext["humidity"]:.2f} %")
    #st.write("Final values:")
    #st.write(values_station_ext)

    # Create the payload for API call (station)
    params={'device_id': MAC_station,
            'scale': '30min',
            #'type': 'temperature',
            'type': 'temperature,humidity,pressure,co2',
            'date_begin': date_start,
            #'date_end': date_end,
            #'limit': '1024',
            'optimize': 'false',
            'real_time': 'true'}
    #print(params)
    #st.write(params)
    
    response = requests.get(url=URL, params=params, headers=headers)
    #print(response.content)
    #st.write(response.content)
    
    if 'body' in response.json():
        body = response.json()['body']
    else:
        st.error("Error with the data downloading")
        return
    values_station = dict()
    for key in body:
        values_station["time"] = datetime.fromtimestamp(int(key), tz=timezone.utc).time()
        values_station["temperature"] = body[key][0]
        values_station["humidity"] = body[key][1]
        values_station["pressure"] = body[key][2]
        values_station["co2"] = body[key][3]
        #st.write(f"\nTemperature: {values_station_ext["temperature"]:.2f} °C")
        #st.write(f"\nHumidity: {values_station_ext["humidity"]:.2f} %")
    #st.write("Final values:")
    #st.write(values_station_ext)
    
    ## Add timestamps
    #datetime_start = datetime.fromtimestamp(body['beg_time'])
    
    ## Parse sampling interval
    #step_time = 1 # This default value should be overwritten, if there is only one sample
    #if 'step_time' in payload:
    #    step_time = payload['step_time']
    
    ## Create timestamps
    #values['timestamp'] = [datetime_start + timedelta(seconds=i*step_time) for i in range(0, len(values['temperature']))]
    
    ## Create dataframe
    #df = pd.DataFrame.from_dict(values)
    #df = df.set_index('timestamp')
    #df.head()
    
    st.title("Calcolatore confronto rapporti di mescolanza e punto di rugiada")
    
    t_indoor_tav = values_homecoach["temperature"]
    rh_indoor_tav = values_homecoach["humidity"]
    t_indoor_cam = values_station["temperature"]
    rh_indoor_cam = values_station["humidity"]
    t_outdoor = values_station_ext["temperature"]
    rh_outdoor = values_station_ext["humidity"]
    p_atm_tav = values_homecoach["pressure"]
    p_atm_cam = values_station["pressure"]

    st.subheader(f"Dati letti dai sensori Taverna (UTC {values_homecoach['time']}), Camera (UTC {values_station['time']}), Esterno (UTC {values_station_ext['time']})")
    
    st.write(f"Temperatura taverna: {t_indoor_tav:.1f} °C")
    st.write(f"Umidità relativa taverna: {rh_indoor_tav:.0f} %")
    st.write(f"Temperatura camera: {t_indoor_cam:.1f} °C")
    st.write(f"Umidità relativa camera: {rh_indoor_cam:.0f} %")
    st.write(f"Temperatura esterna: {t_outdoor:.1f} °C")
    st.write(f"Umidità relativa esterna: {rh_outdoor:.0f} %")
    st.write(f"Pressione atmosferica camera: {p_atm_cam:.1f} hPA")
    st.write(f"Pressione atmosferica taverna: {p_atm_tav:.1f} hPA")
    
    #if not (0 <= rh_indoor <= 100 and 0 <= rh_outdoor <= 100):
    #    st.warning("Errore: L'umidità relativa deve essere tra 0 e 100%.")
    #    return

    st.subheader("Dati calcolati")
    
    # Calcola il punto di rugiada taverna
    rh_indoor_decimal_tav = rh_indoor_tav / 100.0
    td_indoor_tav = calculate_dew_point(t_indoor_tav, rh_indoor_decimal_tav)
    st.write(f"Punto di rugiada taverna calcolato: {td_indoor_tav:.2f} °C")

    # Calcola il punto di rugiada camera
    rh_indoor_decimal_cam = rh_indoor_cam / 100.0
    td_indoor_cam = calculate_dew_point(t_indoor_cam, rh_indoor_decimal_cam)
    st.write(f"Punto di rugiada camera calcolato: {td_indoor_cam:.2f} °C")

    # Calcola il punto di rugiada esterno
    rh_outdoor_decimal = rh_outdoor / 100.0
    td_outdoor = calculate_dew_point(t_outdoor, rh_outdoor_decimal)
    st.write(f"Punto di rugiada esterno calcolato: {td_outdoor:.2f} °C")
    
    can_open_tav, ratio_value_tav, pv_indoor_val_tav, pv_outdoor_val = should_open_windows_based_on_TRH(
            t_indoor_tav, rh_indoor_tav,
            t_outdoor, rh_outdoor,
            p_atm_cam # Usare p_atm ext???
    )
    
    can_open_cam, ratio_value_cam, pv_indoor_val_cam, pv_outdoor_val = should_open_windows_based_on_TRH(
            t_indoor_cam, rh_indoor_cam,
            t_outdoor, rh_outdoor,
            p_atm_cam # Usare p_atm ext???
    )
    
    # Calcola e stampa l'umidità assoluta (densità)
    if pv_indoor_val_tav is not None and pv_indoor_val_cam is not None and pv_outdoor_val is not None:
        abs_hum_indoor_tav = calculate_absolute_humidity_density(pv_indoor_val_tav, t_indoor_tav)
        abs_hum_indoor_cam = calculate_absolute_humidity_density(pv_indoor_val_cam, t_indoor_cam)
        abs_hum_outdoor = calculate_absolute_humidity_density(pv_outdoor_val, t_outdoor)
        st.write(f"Umidità Assoluta Taverna: {abs_hum_indoor_tav:.2f} g/m³")
        st.write(f"Umidità Assoluta Camera: {abs_hum_indoor_cam:.2f} g/m³")
        st.write(f"Umidità Assoluta Esterna: {abs_hum_outdoor:.2f} g/m³")
    else:
        st.warning("Impossibile calcolare l'umidità assoluta a causa di errori precedenti.")

    # Calcola e stampa il rapporto di miscela (w) e l'umidità specifica (q)
    if pv_indoor_val_tav is not None and pv_indoor_val_cam is not None and pv_outdoor_val is not None:
        w_indoor_tav = calculate_mixing_ratio_from_pv(pv_indoor_val_tav, p_atm_tav)
        q_indoor_tav = calculate_specific_humidity_from_mixing_ratio(w_indoor_tav)
        w_indoor_cam = calculate_mixing_ratio_from_pv(pv_indoor_val_cam, p_atm_cam)
        q_indoor_cam = calculate_specific_humidity_from_mixing_ratio(w_indoor_cam)
        
        w_outdoor = calculate_mixing_ratio_from_pv(pv_outdoor_val, p_atm_cam)
        q_outdoor = calculate_specific_humidity_from_mixing_ratio(w_outdoor)
        
        st.write(f"Umidità Specifica Taverna (q_indoor_tav): {q_indoor_tav:.2f} g/kg")
        st.write(f"Umidità Specifica Camera (q_indoor_cam): {q_indoor_cam:.2f} g/kg")
        st.write(f"Umidità Specifica Esterna (q_outdoor): {q_outdoor:.2f} g/kg")
            
        st.write(f"Rapporto di Miscela Taverna (w_indoor_tav): {w_indoor_tav:.2f} g/kg")
        st.write(f"Rapporto di Miscela Camera (w_indoor_cam): {w_indoor_cam:.2f} g/kg")
        st.write(f"Rapporto di Miscela Esterno (w_outdoor): {w_outdoor:.2f} g/kg")
            
    else:
        st.warning("Impossibile calcolare rapporto di miscela e umidità specifica a causa di errori precedenti.")
    
    # Indicatore visivo testuale e colore per grafico
    st.subheader("Risultato")
    if ratio_value_tav is not None:
        st.write(f"Per la taverna, il rapporto (w_indoor_tav / w_outdoor) è: {ratio_value_tav:.4f}")
        if ratio_value_tav > 1:
            verdict = "Apri"
            verdict_color = 'green'
            st.success("✅ L'aria esterna è più secca: aprendo le finestre della taverna ridurrai l'umidità interna.")
        elif ratio_value_tav < 1:
            verdict = "Chiudi"
            verdict_color = 'red'
            st.error("❌ L'aria esterna è più umida: aprendo le finestre della taverna aumenterai l'umidità interna.")
        else:
            verdict = "Uguale"
            verdict_color = 'blue'
            st.info("ℹ️ L'aria esterna e della taverna hanno la stessa umidità specifica.")
    else:
        st.warning("Impossibile calcolare il rapporto (w_indoor / w_outdoor) a causa di condizioni non valide o estreme.")

    if ratio_value_cam is not None:
        st.write(f"Per la camera, il rapporto (w_indoor_cam / w_outdoor) è: {ratio_value_cam:.4f}")
        if ratio_value_cam > 1:
            verdict = "Apri"
            verdict_color = 'green'
            st.success("✅ L'aria esterna è più secca: aprendo le finestre della camera ridurrai l'umidità interna.")
        elif ratio_value_cam < 1:
            verdict = "Chiudi"
            verdict_color = 'red'
            st.error("❌ L'aria esterna è più umida: aprendo le finestre della camera aumenterai l'umidità interna.")
        else:
            verdict = "Uguale"
            verdict_color = 'blue'
            st.info("ℹ️ L'aria esterna e della camera hanno la stessa umidità specifica.")
    else:
        st.warning("Impossibile calcolare il rapporto (w_indoor / w_outdoor) a causa di condizioni non valide o estreme.")

    #except ValueError:
    #    st.write("\nErrore: Assicurati di inserire valori numerici validi per temperature, umidità e pressione.")
    #except Exception as e:
    #    st.write(f"\nSi è verificato un errore inaspettato: {e}")

if __name__ == "__main__":
    main()
