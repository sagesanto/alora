import sys, os, logging
import argparse
import requests
from flask import request, jsonify, Flask
from subscriber import Subscriber
from os.path import join

from slack_sdk.models.attachments import Attachment
from slack_sdk import WebClient

from alora.observatory.config import config, configure_logger, logging_dir, get_credential

class SlackNotifier(Subscriber):
    def __init__(self, own_port, webhook_url, critic_url, min_severity) -> None:
        self.slack_token = get_credential('slack','token')
        self.slack_channel = get_credential('slack','channel')
        self.slack_client = WebClient(token=self.slack_token)
        super().__init__("Slack",own_port, webhook_url, critic_url, min_severity)

    def send(self, message, **kwargs):
        # send message to slack channel
        return self.slack_client.chat_postMessage(channel=self.slack_channel, text=message, **kwargs)
    
    def whisper(self,message,**kwargs):
        user = get_credential('slack','whisper')
        return self.slack_client.chat_postEphemeral(channel=self.slack_channel, text=message, user=user, **kwargs)
    
    def dm(self,message,uid=None,**kwargs):
        user = uid if uid else get_credential('slack','whisper')
        return self.slack_client.chat_postMessage(channel=user, text=message, **kwargs)

    def setup_routes(self):
        @self.app.route('/', methods=['POST'])
        def receive():
            event = request.json
            print(f"Received event: {event}")
            # if event['event_type'] == 'crash':
            self.notify_crash(event)
            return jsonify({'status': 'success'})

    def notify_crash(self, event):        
        block = self.make_msg_block(event)
        print("Message success?",self.dm(message=f"*Alora Choir Notification* <@{get_credential('slack','whisper')}>",attachments=block)["ok"])
        # print("Message success?",self.whisper(message=f"*Critic Crash Alert* <@{os.getenv('WHISPER_TO')}>",attachments=block)["ok"])
    
    def make_msg_block(self, event):
        severity = event["severity"]
        timestamp = event["timestamp"]
        source = event["source"]
        topic = event["topic"]
        msg = event["msg"]

        color = {"critical":"#E01E5A", "error":"#E01E5A", "warning":"#eee600","info":"555555"}[severity]
        # filename = os.path.basename(event['event_src_path'])
        # timestamp = datetime.strptime(filename.strip(".txt"),'%Y_%m_%d_%H_%M_%S').strftime('%Y-%m-%d %H:%M:%S UTC')
        # dirname = os.path.basename(os.path.dirname(event['event_src_path']))

        # message = f"{timestamp}"
        # with open(event['event_src_path'], 'r') as f:
            # msg = f"{f.read()}"
        # message_parts = msg.split("Traceback:")
        # message+=f"\n{message_parts[0]}"
        # traceback = message_parts[1]
        # return Attachment(text=traceback, pretext=message, color="#36a64f",title="Traceback").to_dict()
        return [
            {"color": color,
             "blocks":[{
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity[0].upper()+severity[1:]} notification from {source}",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{timestamp}\nTopic: {topic}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Message*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": msg
                }
            }]}
        ]


if __name__ == '__main__':
    subscriber_port = 5101
    choir_port = config["CHOIR_PORT"]
    logger = configure_logger("Slack Notifier",join(logging_dir,"choir_slack.log"))
    subscriber = SlackNotifier(own_port=subscriber_port, webhook_url=f'http://localhost:{subscriber_port}', critic_url=f'http://localhost:{choir_port}', min_severity='info')