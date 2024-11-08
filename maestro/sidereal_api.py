import flask
from astral import LocationInfo
from astropy.time import Time
from astral import LocationInfo
from datetime import datetime

app = flask.Flask(__name__)

def get_current_sidereal_time(location):
    currentTime = datetime.utcnow().replace(second=0, microsecond=0)
    return Time(currentTime).sidereal_time('mean', longitude=location.longitude)

@app.route('/lst',methods=["GET","POST"])
def lst():
    request = flask.request
    json = request.json
    longitude = float(json['longitude'])
    location = LocationInfo("obs", "obs", "GMT", longitude, 0)
    return str(get_current_sidereal_time(location))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
# Path: scheduleLib/genUtils.