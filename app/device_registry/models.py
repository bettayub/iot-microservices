# device registry models

from datetime import datetime
from common.db import db
from app.user_management.models import User
from app.paired_devices_registry.models import PairedDevice
from app.notification_registry.models import DeviceEventLog
class Device(db.Model):
    __tablename__ = 'device'
    
    id = db.Column(db.Integer, primary_key=True)
    matx_id = db.Column(db.String(36), unique=True, nullable=False)
    wall_adapter_id = db.Column(db.String(50), unique=True, nullable=False)
    gas_device_id = db.Column(db.String(50), unique=True, nullable=False)
    external_id = db.Column(db.String(20), unique=True, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    paired_devices = db.relationship('PairedDevice', back_populates='device', cascade="all, delete-orphan")
    event_logs = db.relationship('DeviceEventLog', back_populates='device', cascade="all, delete-orphan")


    def __init__(self, matx_id, wall_adapter_id, gas_device_id, external_id):
        self.matx_id = matx_id
        self.wall_adapter_id = wall_adapter_id
        self.gas_device_id = gas_device_id
        self.external_id = external_id
