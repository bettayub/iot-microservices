# app/paired_devices_registry/models.py
from common.db import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
import uuid

class PairedDevice(db.Model):
    __tablename__ = 'assigned_device'

    id = db.Column(db.Integer, primary_key=True)
    matx_id = db.Column(db.String(36), db.ForeignKey('device.matx_id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)  
    name = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='paired_devices')
    device = db.relationship('Device', back_populates='paired_devices')