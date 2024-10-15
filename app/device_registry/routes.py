# device registry routes

from datetime import datetime, timedelta
import random
from flask_restx import Namespace, Resource, fields
from flask import request
import uuid6
from common.db import db
from app.device_registry.models import Device

def convert_to_plus_3_gmt(utc_dt):
    """Convert UTC datetime to GMT+3"""
    return utc_dt + timedelta(hours=3)

def format_time(dt):
    """Format datetime to 'HH:MM:SS'"""
    return dt.strftime('%H:%M:%S')

api = Namespace('devices', description='Device registry operations')

# Define a model schema for the devices
device_model = api.model('Device', {
    'device_type': fields.String(required=True, description='Type of the device'),
    'device_id': fields.String(required=True, description='Unique ID of the device'),
})

# Define a model schema for the request payload
device_payload = api.model('DevicePayload', {
    'devices': fields.List(fields.Nested(device_model), required=True, description='List of devices', example=[
        {
            "device_type": "wall_adapter",
            "device_id": "WA-001"
        },
        {
            "device_type": "gas_device",
            "device_id": "GD-001"
        }
    ])
})

def generate_matx_id():
    """Generate a unique ID using UUID v7"""
    return str(uuid6.uuid7())

def generate_external_id():
    """Generate a 20-digit numeric external ID"""
    return ''.join([str(random.randint(0, 9)) for _ in range(20)])

@api.route('/new')
class DeviceList(Resource):
    @api.expect(device_payload)
    @api.doc('create_devices')
    def post(self):
        """Create new devices"""
        data = request.json
        devices = data.get('devices')

        if not devices or len(devices) != 2:
            return {"error": "Invalid input, please provide exactly 2 devices."}, 400

        wall_adapter = next((d for d in devices if d['device_type'] == 'wall_adapter'), None)
        gas_device = next((d for d in devices if d['device_type'] == 'gas_device'), None)

        if not wall_adapter or not gas_device:
            return {"error": "Both wall_adapter and gas_device are required."}, 400

        wall_adapter_id = wall_adapter['device_id']
        gas_device_id = gas_device['device_id']

        # Generate the external ID automatically
        external_id = generate_external_id()

        # Check for existing devices with the same IDs or external_id
        existing_device = Device.query.filter(
            (Device.wall_adapter_id == wall_adapter_id) | 
            (Device.gas_device_id == gas_device_id) | 
            (Device.external_id == external_id)
        ).first()

        if existing_device:
            return {"error": "Device ID or External ID already exists."}, 400

        # Generate a unique MATX ID
        matx_id = generate_matx_id()

        # Create and save the new device
        new_device = Device(matx_id=matx_id, wall_adapter_id=wall_adapter_id, gas_device_id=gas_device_id, external_id=external_id)
        db.session.add(new_device)
        db.session.commit()

        # Format the timestamp in GMT+3
        timestamp_gmt_plus_3 = convert_to_plus_3_gmt(datetime.utcnow())
        formatted_timestamp = format_time(timestamp_gmt_plus_3)

        return {
            "message": "Devices created successfully.",
            "timestamp": formatted_timestamp,  # Include formatted timestamp after message
            "matx_id": matx_id,
            "external_id": external_id,
            "devices": [
                {"device_type": "wall_adapter", "device_id": wall_adapter_id},
                {"device_type": "gas_device", "device_id": gas_device_id}
            ]
        }, 201

@api.route('/search')
class DeviceSearch(Resource):
    @api.doc('get_devices')
    def get(self):
        """Get devices by MATX ID, external ID, gas device ID, or wall adapter ID"""
        matx_id = request.args.get('matx_id')
        external_id = request.args.get('external_id')

        # Check if at least one parameter is provided
        if not (matx_id or external_id):
            return {"error": "At least one query parameter (matx_id, external_id) is required."}, 400

        # Build the query based on provided parameters
        query = Device.query
        if matx_id:
            query = query.filter_by(matx_id=matx_id)
        if external_id:
            query = query.filter_by(external_id=external_id)

        device = query.first()

        if not device:
            return {"error": "Devices not found for the provided parameters."}, 404

        # Format the timestamp in GMT+3
        timestamp_gmt_plus_3 = convert_to_plus_3_gmt(datetime.utcnow())
        formatted_timestamp = format_time(timestamp_gmt_plus_3)

        return {
            "matx_id": device.matx_id,
            "external_id": device.external_id,
            "devices": [
                {
                    "device_type": "wall_adapter",
                    "device_id": device.wall_adapter_id
                },
                {
                    "device_type": "gas_device",
                    "device_id": device.gas_device_id
                }
            ],
            "timestamp": formatted_timestamp  # Include formatted timestamp
        }, 200

@api.route('/')
class AllDevices(Resource):
    @api.doc('get_all_devices')
    def get(self):
        """Get all devices"""
        # Query the database for all devices
        devices = Device.query.all()

        # If no devices are found, return a message
        if not devices:
            return {'message': 'No devices found'}, 200

        # Prepare the response in the required format
        result = []
        for device in devices:
            device_entry = {
                "message": "Devices retrieved successfully.",
                "timestamp": format_time(convert_to_plus_3_gmt(datetime.utcnow())),  # Include formatted timestamp
                "matx_id": device.matx_id,
                "external_id": device.external_id,
                "devices": []
            }
            
            if device.wall_adapter_id:
                device_entry["devices"].append({
                    "device_type": "wall_adapter",
                    "device_id": device.wall_adapter_id
                })
            if device.gas_device_id:
                device_entry["devices"].append({
                    "device_type": "gas_device",
                    "device_id": device.gas_device_id
                })

            # Add the device entry to the result list
            result.append(device_entry)

        return result, 200
