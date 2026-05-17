from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/log-activities', methods=['POST'])
def log_activities():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body"}), 400

    print("Received:", data)

    # Do whatever you want with data here

    return jsonify({"status": "ok", "received": data}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8945)