from flask_restx import Namespace, Resource, fields
from flask import request
from flask_jwt_extended import jwt_required
from common.db import db
from app.user_management.models import User
from app.device_registry.models import Device
from app.paired_devices_registry.models import PairedDevice

api = Namespace('assigning-devices-to-users', description='Assigned devices operations')

pairing_model = api.model('Pairing', {
    'matx_id': fields.String(required=True, description='MATX ID of the devices to be paired'),
    'user_id': fields.String(required=True, description='ID of the user to whom the devices are being paired'),
    'name': fields.String(required=False, description='Name for the paired device')  # Optional name field
})

@api.route('/user/<string:user_id>')
class PairedDevicesByUser(Resource):
    @api.doc('list_paired_devices_by_user')
    def get(self, user_id):
        """List all devices assigned to a specific user."""
        # Fetch paired devices by user_id
        pairs = PairedDevice.query.filter_by(user_id=user_id).all()

        if not pairs:
            return {'message': 'No paired devices found for the specified user'}, 404

        # Construct the response data
        paired_devices = [{
            'matx_id': pair.device.matx_id,
            'name': pair.name,
            'timestamp': pair.timestamp.isoformat()  # Convert timestamp to ISO format
        } for pair in pairs]

        return paired_devices, 200

@api.route('/all')
class AllPairedDevices(Resource):
    @api.doc('get_all_paired_devices')
    def get(self):
        """Get all paired devices for all users."""
        paired_devices = PairedDevice.query.all()

        if not paired_devices:
            return {'message': 'No paired devices found'}, 404

        # Return a list of all paired devices with user and device details
        result = [{
            'matx_id': pair.device.matx_id,
            'user_id': pair.user_id,
            'name': pair.name,
            'timestamp': pair.timestamp.isoformat()  # Convert timestamp to ISO format
        } for pair in paired_devices]

        return result, 200

@api.route('/')
class PairedDeviceList(Resource):
    @api.doc('pair_devices_to_user')
    @api.expect(pairing_model)
    def post(self):
        """Assign a device to a user using MATX ID."""
        data = request.json
        user_id = data.get('user_id')
        matx_id = data.get('matx_id')
        name = data.get('name')  # Get the name from the request

        # Fetch the user and device using the matx_id
        user = User.query.get(user_id)
        device = Device.query.filter_by(matx_id=matx_id).first()

        if not user:
            api.abort(404, 'User not found')

        if not device:
            api.abort(404, 'Device with the provided MATX ID not found')

        # Check if the device is already paired with this user
        existing_pair = PairedDevice.query.filter_by(user_id=user_id, matx_id=matx_id).first()
        if existing_pair:
            api.abort(400, 'Device already paired with this user')

        # Create a new paired device record
        paired_device = PairedDevice(
            user_id=user_id,
            matx_id=matx_id,
            name=name
        )
        db.session.add(paired_device)
        db.session.commit()

        return {'message': 'Device successfully paired with the user'}, 201
