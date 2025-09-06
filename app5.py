
# Source: https://dev.netatmo.com/apidocumentation/oauth
# Notes:
# - Register an app on https://dev.netatmo.com/ (Top right, 'My apps')
# - Device: Home coach

from datetime import datetime, timedelta
import requests
import streamlit as st
import numpy as np

st.title("Calcolatore confronto rapporti di mescolanza e punto di rugiada")

# App credentials
CLIENT_ID = '68bc5cc2dc51f3e3360f3d22' # Sometimes called app ID, looks like: '5989eA5B1AF3d8fc015d4215'
CLIENT_SECRET = 'UeKLTCHiucBfiyBvVqmRN9iC9czdbmnMGcp' # looks like: 'BHtNLOTNSsbQFSqpCoGsQkOCjZJrothMwW'

# These tokens are generated in the 'app' created on dev.netatmo.com (scope: read_homecoach)
netatmo_access_token = '5e0f7e2dc5bdbd000c158377|8c67bc6f9def3ff2012ab2fb3038f5fd' # looks like: 'cde723283f7ab2d2786fb1f1|506be379de09b2ff5d3e25e56ebb8cdf'

netatmo_refresh_token = '5e0f7e2dc5bdbd000c158377|b8fc6cef23cbe46d45bb2ff666bf675f' # looks like: 'cde723283f7ab2d2786fb1f1|9977bb61decf0ed99db97b096e66fe77'

#SCOPE = 'read_homecoach'
MAC_homecoach = '70:ee:50:3e:c4:de' # MAC address of the device looks like: '21:ff:31:69:2d:19'

#SCOPE = 'read_station'
MAC_station = '70:ee:50:64:49:34' # MAC address of the device looks like: '21:ff:31:69:2d:19'

date_start = datetime.now()-timedelta(days=1)
date_start = int(date_start.replace(tzinfo=None).timestamp())
date_end = int(datetime.now().timestamp())

URL = 'https://api.netatmo.com/api/getmeasure'

# Create the header for API call
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {netatmo_access_token}"
}

# Create the payload for API call (homecoach)
params={'device_id': MAC_homecoach,
        #'module_id': MAC_homecoach,
        'scale': '1hour',
        'type': 'temperature,humidity,pressure,co2',
        #'date_begin': date_start,
        #'date_end': date_end,
        'limit': '1',
        'optimize': 'false',
        'real_time': 'true'}
#print(params)
#st.write(params)

# Make API call
response = requests.get(url=URL, params=params, headers=headers)
#print(response.content)
st.write(response.content)

data = response.json()

# Create the payload for API call (station)
params={'device_id': MAC_station,
        #'module_id': MAC_station,
        'scale': '1hour',
        #'type': 'temperature',
        'type': 'temperature,humidity,pressure,co2',
        #'date_begin': date_start,
        #'date_end': date_end,
        'limit': '1',
        'optimize': 'false',
        'real_time': 'true'}
#print(params)
#st.write(params)

response = requests.get(url=URL, params=params, headers=headers)
#print(response.content)
st.write(response.content)

body = response.json()['body']
st.write(body)

values = dict()
for key in body:{
    #values["temperature"] = body[key][0]
    #values["humidity"] = body[key][1]
    #values["pressure"] = body[key][2]
    #values["co2"] = body[key][3]
    temp = body[key][0]
}

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

# Create payload
URL = 'https://api.netatmo.com/oauth2/token'
payload={'grant_type': 'refresh_token',
         'refresh_token': netatmo_refresh_token,
         'client_id': CLIENT_ID,
         'client_secret': CLIENT_SECRET}
#print(payload)
st.write(payload)

# Create headers
headers = {
    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
}

## Make API call
#response = requests.post(url=URL, data=payload, headers=headers)
##print(response.content)
#st.write(response.content)

## Parse response data
#netatmo_access_token = response.json()['access_token']
#print(response.status_code)

w_int = 1
w_ext = 1
ratio = w_int / w_ext if w_ext != 0 else np.nan
Td_int = 1
Td_ext = 1

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
