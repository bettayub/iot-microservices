from datetime import datetime
from common.db import db

class DeviceEventLog(db.Model):
    __tablename__ = 'device_event_log'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey('device.gas_device_id'), nullable=False)  # Foreign key to Device table
    start_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_timestamp = db.Column(db.DateTime, nullable=True)
    notification_timestamp = db.Column(db.DateTime, nullable=True)  # When the notification was sent
    offline_message_count = db.Column(db.Integer, nullable=False, default=0)  # Number of offline messages sent
    

    # Relationships
    device = db.relationship('Device', back_populates='event_logs')
