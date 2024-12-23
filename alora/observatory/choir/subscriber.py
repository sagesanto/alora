import requests
from flask import request, jsonify, Flask

from alora.config import config as cfg

class Subscriber:
    def __init__(self, name, own_port, webhook_url, critic_url, min_severity) -> None:
        self.name = name
        self.own_port = own_port
        self.webhook_url = webhook_url
        self.critic_url = critic_url
        self.min_severity = min_severity
        self.app = Flask(__name__)
        self.setup_routes()
        self.subscribe()
        self.app.run(port=own_port)

    def write_out(self,*args):
        print(" ".join([str(a) for a in args]))

    def subscribe(self):
        url = f'{self.critic_url}/subscribe'
        data = {'webhook_url': self.webhook_url, 'severity': self.min_severity, 'name':self.name}
        try:
            response = requests.post(url, json=data,timeout=3)
        except Exception as e:
            self.write_out(f"Failed to subscribe to Choir:\n{e}")
            exit()
        return response.json()
    
    def setup_routes(self):
        # override this method to actually do something with the events
        @self.app.route('/', methods=['POST'])
        def receive():
            event = request.json
            self.write_out("recieved event: ",event)
            return jsonify({'status': 'success'})

if __name__ == '__main__':
    choir_port = cfg['CHOIR_PORT']
    
    subscriber_port = 5101
    subscriber = Subscriber("test_subscriber",own_port=subscriber_port, webhook_url=f'http://127.0.0.1:{subscriber_port}', critic_url=f'http://127.0.0.1:{choir_port}', min_severity='info')