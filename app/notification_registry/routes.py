from flask import Blueprint, request
from flask_restx import Api, Resource
from mailjet_rest import Client
from datetime import datetime, timedelta

api = Blueprint('notification_registry', __name__)
api = Api(api)

api_key = '98baa56555339c6e0edb75d67e09e24d'
api_secret = 'd874ddb225fa31b72b6c1e52912be0b8'
mailjet = Client(auth=(api_key, api_secret), version='v3.1')

def send_offline_notification(email, notification_message):
    """
    Send offline notification using Mailjet.
    
    Args:
        email (str): Recipient's email address.
        notification_message (str): Message to include in the notification.
    """
    template_id = 6306768
    data = {
        'Messages': [
            {
                "From": {
                    "Email": "ayubbett1998@gmail.com",
                    "Name": "MatX"
                },
                "To": [
                    {
                        "Email": email,
                        "Name": "Recipient Name"
                    }
                ],
                "TemplateID": template_id,
                "TemplateLanguage": True,
                "Subject": "Gas Device Offline!",
                "Variables": {
                    "message": notification_message
                }
            }
        ]
    }

    # Send the notification
    try:
        result = mailjet.send.create(data=data)
        if result.status_code == 200:
            print(f"Offline notification sent successfully for Template ID: {template_id}")
        else:
            print(f"Failed to send offline notification for Template ID: {template_id}: {result.json()}")
    except Exception as e:
        print(f"Exception occurred while sending offline notification Template ID {template_id}: {str(e)}")


def send_reminder_notification(email, notification_message):
    """
    Send reminder notification using Mailjet.
    
    Args:
        email (str): Recipient's email address.
        notification_message (str): Message to include in the notification.
    """
    template_id = 6315934
    data = {
        'Messages': [
            {
                "From": {
                    "Email": "ayubbett1998@gmail.com",
                    "Name": "MatX"
                },
                "To": [
                    {
                        "Email": email,
                        "Name": "Recipient Name"
                    }
                ],
                "TemplateID": template_id,
                "TemplateLanguage": True,
                "Subject": "Device Reminder Status",
                "Variables": {
                    "message": notification_message
                }
            }
        ]
    }

    # Send the notification
    try:
        result = mailjet.send.create(data=data)
        if result.status_code == 200:
            print(f"Reminder notification sent successfully for Template ID: {template_id}")
        else:
            print(f"Failed to send reminder notification for Template ID: {template_id}: {result.json()}")
    except Exception as e:
        print(f"Exception occurred while sending reminder notification Template ID {template_id}: {str(e)}")

# Example usage
# send_offline_notification('recipient@example.com', 'Your device is offline or needs attention.')
# send_reminder_notification('recipient@example.com', 'Your device needs a status check.')
