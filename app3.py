# Source: https://dev.netatmo.com/apidocumentation/oauth
# Notes:
# - Register an app on https://dev.netatmo.com/ (Top right, 'My apps')
# - Device: Home coach

from datetime import datetime, timedelta
import requests

# User credentials
EMAIL = ''
PASSWORD = ''

# App credentials
CLIENT_ID = '68b74b4ac2bea2591d0ae884' # Sometimes called app ID, looks like: '5989eA5B1AF3d8fc015d4215'
CLIENT_SECRET = 'OPuXZVyQYeN4inJQ0tH8WRApLVQWCPhOl' # looks like: 'BHtNLOTNSsbQFSqpCoGsQkOCjZJrothMwW'

# These tokens are generated in the 'app' created on dev.netatmo.com (scope: read_homecoach)
netatmo_access_token = '5e0f7e2dc5bdbd000c158377|2e52514cffacf1028646b884f90df4c2' # looks like: 'cde723283f7ab2d2786fb1f1|506be379de09b2ff5d3e25e56ebb8cdf'

netatmo_refresh_token = '5e0f7e2dc5bdbd000c158377|41c022c9fccfe1da12325738fb4f1f00'# looks like: 'cde723283f7ab2d2786fb1f1|9977bb61decf0ed99db97b096e66fe77'

SCOPE = 'read_homecoach'
MAC = '70:ee:50:3e:c4:de' # MAC address of the device looks like: '21:ff:31:69:2d:19'

#SCOPE = 'read_station'
#MAC = '70:ee:50:64:49:34' # MAC address of the device looks like: '21:ff:31:69:2d:19'

date_start = datetime.now()-timedelta(days=1)
date_start = int(date_start.replace(tzinfo=None).timestamp())
date_end = int(datetime.now().timestamp())

URL = 'https://api.netatmo.com/api/getmeasure'

# Create the payload for API call
params={'device_id': MAC,
        #'module_id': MAC,
        'scale': '1hour',
        'type': 'temperature',
        #'type': 'temperature,humidity,co2,pressure,noise',
        #'date_begin': date_start,
        #'date_end': date_end,
        #'limit': '1024',
        'optimize': 'false',
        'real_time': 'false'}
print(params)

# Create the header for API call
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {netatmo_access_token}"
}

# Make API call
response = requests.get(url=URL, params=params, headers=headers)
print(response.content)

# Parse response data
print(response.json())

exit()

body = response.json()['body'][0]

values = dict()
values['temperature'] = [val[0] for val in body['value']]
values['humidity'] = [val[1] for val in body['value']]
values['co2'] = [val[2] for val in body['value']]
values['pressure'] = [val[3] for val in body['value']]
values['noise'] = [val[4] for val in body['value']]

# Add timestamps
datetime_start = datetime.fromtimestamp(body['beg_time'])

# Parse sampling interval
step_time = 1 # This default value should be overwritten, if there is only one sample
if 'step_time' in payload:
    step_time = payload['step_time']

# Create timestamps
values['timestamp'] = [datetime_start + timedelta(seconds=i*step_time) for i in range(0, len(values['temperature']))]

# Create dataframe
df = pd.DataFrame.from_dict(values)
df = df.set_index('timestamp')
df.head()

# Create payload
URL = 'https://api.netatmo.com/oauth2/token'
payload={'grant_type': 'refresh_token',
         'refresh_token': netatmo_refresh_token,
         'client_id': CLIENT_ID,
         'client_secret': CLIENT_SECRET}

# Create headers
headers = {
    'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
}

# Make API call
response = requests.post(url=URL, data=payload, headers=headers)
print(response.content)

# Parse response data
netatmo_access_token = response.json()['access_token']
print(response.status_code)
