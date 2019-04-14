from cloudant import Cloudant
from flask import Flask, render_template, request, jsonify
import requests
import atexit
import os
import json
from datetime import *
import csv
import numpy as np
import cv2

app = Flask(__name__, static_url_path='')

np.__version__
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

# region Helper functions

# region actual traffic analysis


def url_to_image(url: str):
    urlImg = requests.get(url)
    image = np.asarray(bytearray(urlImg.content), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    return image


def detect_traffic(img):
    car_cascade = cv2.CascadeClassifier('cars.xml')
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # detects cars using trained cascade and grayscale img.
    cars = car_cascade.detectMultiScale(gray, 1.01, 1)
    return len(cars)
# endregion


def is_address_comp_neighbourhood(*address_comps: dict):
    best_result = None
    for address_comp in address_comps:
        if 'types' in address_comp:
            if 'neighborhood' in address_comp['types']:
                # found rough area where user is in.
                return address_comp['long_name']
            elif 'route' in address_comp['types']:
                # Lor 4 Toa Payoh vs Lorong 4 Toa Payoh
                best_result = address_comp['short_name']
    return best_result


def get_region_str(api_results: list):
    for result in api_results:
        result = is_address_comp_neighbourhood(*result["address_components"])
        if result is not None:
            return result
    return None


def get_sqr_dis(lat1: float, long1: float, lat2: float, long2: float):
    # A^2 + B^2 = C^2 #(x1 - x2)^2 + (y1 - y2)^2 = dis^2
    return ((lat1 - lat2) * (lat1 - lat2)) + ((long1 - long2) * (long1 - long2))


def call_google_api(data: dict):
    # use env var on deployed vers, use gitignored local file for local testing. Google API key is not exposed to anyone else.
    file = open("key.txt")
    key = os.getenv('key', file.read())
    file.close()
    jsonStr = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json?latlng=" + data['lat'] + "," + data['long'] + "&key=" + key).text
    # if API fails.
    if jsonStr is None:
        print("Unable to call Google's Reverse GeoCoding API")
    jsonValue = json.loads(jsonStr)
    if jsonValue["status"] == "OK":
        # get rough location of where you are, then check nearby roads.
        data["name"] = get_region_str(jsonValue["results"])
    return data
# region data.gov.sg data


def get_camera_area():
    data = {}
    dataFile = open("data.csv")
    dataReader = csv.reader(dataFile)
    for row in dataReader:
        # col 0: id, col 1: lat, col 2: long, col 3: area string
        # only need area actually to print to web app.
        data[row[0]] = {"area": row[3]}
    dataFile.close()
    return data

# endregion

# region finalize data

def get_final_camera_data(lat: float = None, long: float = None):
    apiString = requests.get(
        "https://api.data.gov.sg/v1/transport/traffic-images").text
    api_value = json.loads(apiString)
    camera_data = api_value["items"][0]["cameras"]
    temp = get_camera_area()
    final_data = []
    for camera in camera_data:
        temp[camera["camera_id"]]["image"] = camera["image"]
        temp[camera["camera_id"]]["cars_detected"] = detect_traffic(
            url_to_image(camera["image"]))
        if lat is not None and long is not None:
            temp[camera["camera_id"]]["distance"] = get_sqr_dis(
                lat, long, camera["location"]["latitude"], camera["location"]["longitude"])
    for id, cam in temp.items():
        final_data.append(cam)
    if lat is not None and long is not None:
        final_data.sort(key=lambda k: k['distance'])
    return final_data

# endregion


@app.route('/')
def root():
    get_camera_area()
    return render_template('index.html')
# https://developer.mozilla.org/en-US/docs/Learn/HTML/Forms/Sending_and_retrieving_form_data


@app.route('/get', methods=['POST'])
def get():
    data = {
        "name": None,
        "lat": request.form["latitude"],
        "long": request.form["longitude"]
    }
    # if got permission to use location.
    if not(data["lat"] == "" or data["long"] == ""):
        call_google_api(data)
        data["cameras"] = get_final_camera_data(
            float(data["lat"]), float(data["long"]))
    else:
        data["cameras"] = get_final_camera_data()
    return render_template('results.html', data=data)


@atexit.register
def shutdown():
    if client:
        client.disconnect()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=debug)
