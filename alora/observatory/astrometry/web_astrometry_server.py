import os
import keyring
from flask import Flask, request, jsonify
from astroquery.astrometry_net import AstrometryNet
import subprocess

app = Flask(__name__)

def _solve(request_json):
    # send a request to astrometry to solve the image, wait for it to finish, and then write the result to the fits header of the image
    data = request_json
    filepath = data.get('filepath').replace("D:\\", "/mnt/d/").replace("C:\\", "/mnt/c/")
    flags = data.get('flags', [])
    ast = AstrometryNet()
    ast.api_key = keyring.get_password("astrometry_net", "api")
    
    args = ['solve-field', filepath] + flags
    astrom_args = {}
    allowed_args = 
    for key in data:
        if key != 'filepath':
            args.append(f'--{key}')
            args.append(str(data[key]))
        print(f"{key}: {data[key]}")

    if not filepath or not os.path.isfile(filepath):
        return jsonify({'error': 'Invalid file path'}), 400

    try:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'error': result.stderr}), 500

        return jsonify({'message': 'Astrometry.net processing complete', 'output': result.stdout}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/solve_async', methods=['POST'])
def solve_async():

@app.route('/solve', methods=['POST'])
def solve():
    return _solve(request.get_json())
    

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5555)