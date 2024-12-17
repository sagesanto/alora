from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/solve', methods=['POST'])
def solve():
    data = request.get_json()
    filepath = data.get('filepath')
    flags = data.get('flags', [])
    
    args = ['solve-field', filepath] + flags
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555)