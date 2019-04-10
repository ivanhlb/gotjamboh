from cloudant import Cloudant
from flask import Flask, render_template, request, jsonify
import requests
import atexit
import os
import json

app = Flask(__name__, static_url_path='')

db_name = 'mydb'
client = None
db = None
if 'VCAP_SERVICES' in os.environ:
    vcap = json.loads(os.getenv('VCAP_SERVICES'))
    print('Found VCAP_SERVICES')
    if 'cloudantNoSQLDB' in vcap:
        creds = vcap['cloudantNoSQLDB'][0]['credentials']
        user = creds['username']
        password = creds['password']
        url = 'https://' + creds['host']
        client = Cloudant(user, password, url=url, connect=True)
        db = client.create_database(db_name, throw_on_exists=False)
elif "CLOUDANT_URL" in os.environ:
    client = Cloudant(os.environ['CLOUDANT_USERNAME'], os.environ['CLOUDANT_PASSWORD'],
                      url=os.environ['CLOUDANT_URL'], connect=True)
    db = client.create_database(db_name, throw_on_exists=False)
elif os.path.isfile('vcap-local.json'):
    with open('vcap-local.json') as f:
        vcap = json.load(f)
        print('Found local VCAP_SERVICES')
        creds = vcap['services']['cloudantNoSQLDB'][0]['credentials']
        user = creds['username']
        password = creds['password']
        url = 'https://' + creds['host']
        client = Cloudant(user, password, url=url, connect=True)
        db = client.create_database(db_name, throw_on_exists=False)

# On IBM Cloud Cloud Foundry, get the port number from the environment variable PORT
# When running this app on the local machine, default the port to 8000
# debug must be false for deployment, else it crashes

port = int(os.getenv('PORT', 8000))
debug = True if os.environ.get('PORT') is None else False


@app.route('/')
def root():
    return render_template('index.html')
# https://developer.mozilla.org/en-US/docs/Learn/HTML/Forms/Sending_and_retrieving_form_data


@app.route('/get', methods=['POST'])
def get():
    latitude = request.form["latitude"]
    longitude = request.form["longitude"]
    
    if not(latitude == "" or longitude == ""):          #if got permission to use location.
        key = os.getenv('key', open("key.txt").read())
        print(key)
        print(type(key))
        jsonStr = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json?latlng=" + latitude + "," + longitude + "&key=" + key).text
        # if API fails.
        if jsonStr is None:
            print("Unable to call Google's Reverse GeoCoding API")
        jsonValue = json.loads(jsonStr)
        if jsonValue["status"] == "OK":
            # get rough location of where you are, then check nearby roads.
            # jsonValue["results"][0]["address_components"][3]["short_name"]    #returns 'Toa Payoh'
            data = {
                "name": jsonValue["results"][0]["address_components"][3]["short_name"],
                "lat": latitude,
                "long": longitude
            }
            return render_template('results.html', data=data)
    else:
        return render_template('index.html')


@atexit.register
def shutdown():
    if client:
        client.disconnect()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=debug)
