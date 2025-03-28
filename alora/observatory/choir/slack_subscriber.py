import sys, os, logging
import argparse
import requests
from flask import request, jsonify, Flask
from subscriber import Subscriber
from os.path import join

from slack_sdk.models.attachments import Attachment
from slack_sdk import WebClient

from alora.config import config, configure_logger, logging_dir, get_credential

class SlackNotifier(Subscriber):
    def __init__(self, own_port, webhook_url, critic_url, min_severity) -> None:
        self.slack_client = WebClient(token=get_credential('slack','token'))
        self.channels = config["SLACK_CHANNELS"]
        self.whispers = config["SLACK_WHISPERS"]
        super().__init__("Slack",own_port, webhook_url, critic_url, min_severity)

    def send(self, message, **kwargs):
        # send message to slack channel
        success = True
        for channel in self.channels:
            success = success and self.slack_client.chat_postMessage(channel=channel, text=message, **kwargs)["ok"]
        return success
    
    def whisper(self,message,**kwargs):
        success = True
        for user in self.whispers:
            success = success and self.slack_client.chat_postEphemeral(channel=self.channels[0], text=message, user=user, **kwargs)["ok"]
        return success

    def dm(self,message,uid:str=None,**kwargs):
        success = True
        users = [uid] if uid else self.whispers
        for user in users:
            success = success and self.slack_client.chat_postMessage(channel=user, text=message, **kwargs)["ok"]
        return success
    
    def setup_routes(self):
        @self.app.route('/', methods=['POST'])
        def receive():
            event = request.json
            print(f"Received event: {event}")
            self.notify_crash(event)
            return jsonify({'status': 'success'})

    def notify_crash(self, event):        
        block = self.make_msg_block(event)
        print("DM message success?",self.dm(message="*Alora Choir Notification*",attachments=block))
        print("Channel message success?",self.send(message="*Alora Choir Notification*",attachments=block))
        # print("Message success?",self.whisper(message=f"*Critic Crash Alert* <@{os.getenv('WHISPER_TO')}>",attachments=block)["ok"])
    
    def make_msg_block(self, event):
        severity = event["severity"]
        timestamp = event["timestamp"]
        source = event["source"]
        topic = event["topic"]
        msg = event["msg"]

        color = {"critical":"#E01E5A", "error":"#E01E5A", "warning":"#eee600","info":"555555"}[severity]
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
    subscriber = SlackNotifier(own_port=subscriber_port, webhook_url=f'http://127.0.0.1:{subscriber_port}', critic_url=f'http://127.0.0.1:{choir_port}', min_severity='info')