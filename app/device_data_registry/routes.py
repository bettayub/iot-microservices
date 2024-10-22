# device_data_registry routes
from datetime import datetime, timedelta
import re
from flask import request # type: ignore
from flask_restx import Namespace, Resource # type: ignore
from psycopg2 import IntegrityError # type: ignore
from sqlalchemy.exc import SQLAlchemyError
from app.notification_registry.models import DeviceEventLog
from app.notification_registry.routes import send_offline_notification, send_reminder_notification
from app.paired_devices_registry.models import PairedDevice
from app.user_management.models import User
from common.db import db
from app.device_registry.models import Device
from app.device_data_registry.models import DeviceData
import logging
import struct

api = Namespace('data', description='Device Data operations')

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s')


# Helper function to check if the first notification should be sent (0-15 minutes)# Helper function to check if the first notification should be sent (0-15 minutes)
def can_send_first_notification(device_id):
    """Check if the first notification can be sent for the given device ID."""
    current_time = datetime.utcnow()
    device_id = str(device_id)
    
    last_log = DeviceEventLog.query.filter_by(device_id=device_id, end_timestamp=None).first()
    
    if last_log:
        offline_duration = current_time - last_log.start_timestamp
        # Send first notification if offline for <= 15 minutes and not sent yet
        if offline_duration <= timedelta(minutes=15) and last_log.offline_message_count < 1:
            return True
    return False

# Helper function to check if the second notification should be sent (after 60 minutes)
def can_send_second_notification(device_id):
    """Check if the second notification can be sent for the given device ID."""
    current_time = datetime.utcnow()
    device_id = str(device_id)
    
    last_log = DeviceEventLog.query.filter_by(device_id=device_id, end_timestamp=None).first()
    
    if last_log:
        offline_duration = current_time - last_log.start_timestamp
        # Send second notification if offline for >= 60 minutes and less than 2 notifications have been sent
        if offline_duration >= timedelta(minutes=2) and last_log.offline_message_count < 2:
            return True
    return False

# Helper function to log the notification and increment the offline message count
def log_notification(device_id, current_time):
    """Log the time when the notification was sent and increment the offline message count."""
    device_id = str(device_id)
    
    existing_log = DeviceEventLog.query.filter_by(device_id=device_id, end_timestamp=None).first()

    if existing_log:
        existing_log.notification_timestamp = current_time
        existing_log.offline_message_count += 1  # Increment the offline message count
    else:
        # This should not happen as log_notification is called only when a log exists
        new_log = DeviceEventLog(
            device_id=device_id,
            start_timestamp=current_time,
            notification_timestamp=current_time,
            offline_message_count=1  # Start with 1 since it's the first notification
        )
        db.session.add(new_log)
    
    db.session.commit()
# API route for uploading device data


@api.route('/upload')
class UploadData(Resource):
    def post(self):
        data = request.json
        try:
            hex_data = data.get('d')
            wall_adapter_id = data.get('g')
            gas_device_id = data.get('n')
            additional_data = data.get('data', [])

            if hex_data.startswith('4e'):
                return self.process_bulk_data(hex_data, wall_adapter_id, gas_device_id)

            byte_data = bytes.fromhex(hex_data.strip())
            message_type = byte_data[0:1].hex()

            message_type_mappings = {
                "1d": "ALL DATA DUMPED",
                "2d": "No Data Node",
                "3d": "Connection type: NB-IoT",
                "4d": "Connection type: Wi-Fi",
                "5d": "Power source: Battery",
                "6d": "Power source: Electricity",
                "7d": "Gateway Battery < 20%",
                "8d": "Gateway Battery < 5%",
                "9d": "Gateway Battery < 2%",
                "1e": "Node Battery < 20%",
                "2e": "Node Battery < 5%",
                "3e": "Node Battery < 2%",
                "4e": "Bulk data from gas device",
                "5e": "Bulk data from wall adapter"
            }

            if message_type == "5e":
                return self.process_5e_data(hex_data, wall_adapter_id, gas_device_id, additional_data)

            parsed_data = self.parse_single_data(byte_data, message_type)

            wall_adapter_device = Device.query.filter_by(wall_adapter_id=wall_adapter_id).first()
            if not wall_adapter_device:
                return {"status": "error", "message": "Invalid wall adapter device ID."}, 400

            paired_device = PairedDevice.query.filter_by(matx_id=wall_adapter_device.matx_id).first()
            if not paired_device:
                return {"status": "error", "message": "Device is not paired with any user."}, 400

            user_email = paired_device.user.email

            device_data = DeviceData(
                wall_adapter_id=wall_adapter_id,
                gas_device_id=gas_device_id,
                user_id=paired_device.user.id,
                matx_id=wall_adapter_device.matx_id,
                data=byte_data
            )
            db.session.add(device_data)
            db.session.commit()

            self.check_offline_status(wall_adapter_id, user_email)

            return {
                "status": "success",
                "message": "Data uploaded successfully.",
                "data": parsed_data
            }, 201

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing the request: {str(e)}")
            return {"status": "error", "message": "An error occurred while processing the request."}, 500

    def process_5e_data(self, hex_data, wall_adapter_id, gas_device_id, additional_data):
        try:
            wall_adapter_device = Device.query.filter_by(wall_adapter_id=wall_adapter_id).first()
            if not wall_adapter_device:
                return {"status": "error", "message": "Invalid wall adapter device ID."}, 400

            paired_device = PairedDevice.query.filter_by(matx_id=wall_adapter_device.matx_id).first()
            if not paired_device:
                return {"status": "error", "message": "Device is not paired with any user."}, 400

            device_name = paired_device.name or "Unnamed Device"
            current_time = datetime.now()
            
            processed_data = []
            for entry in additional_data:
                entry_hex = entry['d']
                byte_data = bytes.fromhex(entry_hex.strip())
                parsed_data = self.parse_single_data(byte_data, entry_hex[:2])

                data_entry = {
                    "device_id": wall_adapter_id,
                    "name": device_name,
                    "date": current_time.strftime("%d/%m/%Y"),
                    "time": current_time.strftime("%H:%M"),
                    "connection_type": parsed_data["connection_type"],
                    "power_source": parsed_data["power_source"],
                    "wa_battery_status": str(parsed_data["wall_adapter_battery"]),
                    "wa_message_count": str(parsed_data["wall_adapter_message_count"]),
                    "gas_device_id": gas_device_id,
                    "weight": parsed_data["weight"],
                    "gd_battery_status": str(parsed_data["gas_device_battery"]),
                    "gd_message_count": str(parsed_data["gas_device_message_count"]),
                    "matx_id": wall_adapter_device.matx_id
                }
                processed_data.append(data_entry)

                device_data = DeviceData(
                    wall_adapter_id=wall_adapter_id,
                    gas_device_id=gas_device_id,
                    user_id=paired_device.user.id,
                    matx_id=wall_adapter_device.matx_id,
                    data=byte_data
                )
                db.session.add(device_data)

            db.session.commit()
            self.check_offline_status(wall_adapter_id, paired_device.user.email)

            return {
                "status": "success",
                "data": processed_data
            }, 201

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing 5e data: {str(e)}")
            return {"status": "error", "message": f"An error occurred while processing 5e data: {str(e)}"}, 500

    def parse_single_data(self, byte_data, message_type):
        connection_type_mapping = {"df": "NB-IoT", "de": "Wi-Fi"}
        power_source_mapping = {"c8": "Electricity", "c9": "Battery"}

        parsed_data = {
            "connection_type": None,
            "power_source": None,
            "wall_adapter_battery": None,
            "wall_adapter_message_count": None,
            "weight": None,
            "gas_device_battery": None,
            "gas_device_message_count": None
        }

        if message_type in ["1d", "1e", "2e", "3e"]:  # 13 BYTES messages
            parsed_data["connection_type"] = connection_type_mapping.get(byte_data[1:2].hex().lower(), "Unknown")
            parsed_data["power_source"] = power_source_mapping.get(byte_data[2:3].hex().lower(), "Unknown")
            parsed_data["wall_adapter_battery"] = int(byte_data[3])
            parsed_data["wall_adapter_message_count"] = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]
            
            weight_hex_part1 = byte_data[7:8].hex()
            weight_hex_part2 = byte_data[8:9].hex()
            parsed_data["weight"] = f"{int(weight_hex_part1, 16)}.{int(weight_hex_part2, 16):02d}"
            
            parsed_data["gas_device_battery"] = int(byte_data[9])
            parsed_data["gas_device_message_count"] = struct.unpack('>I', b'\x00' + byte_data[10:13])[0]

        elif message_type in ["2d", "3d", "4d", "5d", "6d", "7d", "8d", "9d"]:  # 7 BYTES messages
            parsed_data["connection_type"] = connection_type_mapping.get(byte_data[1:2].hex().lower(), "Unknown")
            parsed_data["power_source"] = power_source_mapping.get(byte_data[2:3].hex().lower(), "Unknown")
            parsed_data["wall_adapter_battery"] = int(byte_data[3])
            parsed_data["wall_adapter_message_count"] = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]

        return parsed_data

    def process_bulk_data(self, hex_data, wall_adapter_id, gas_device_id):
        try:
            match = re.match(r'4e([0-9a-f]{12})\[(.*?)\]', hex_data, re.IGNORECASE)
            if not match:
                return {"status": "error", "message": "Invalid bulk data format."}, 400

            wall_adapter_data = match.group(1)
            gas_device_entries = match.group(2).split(',')

            wall_adapter_device = Device.query.filter_by(wall_adapter_id=wall_adapter_id).first()
            if not wall_adapter_device:
                return {"status": "error", "message": "Invalid wall adapter device ID."}, 400

            paired_device = PairedDevice.query.filter_by(matx_id=wall_adapter_device.matx_id).first()
            if not paired_device:
                return {"status": "error", "message": "Device is not paired with any user."}, 400

            device_name = paired_device.name or "Unnamed Device"
            results = []

            wa_parsed_data = self.parse_data(wall_adapter_data, 'wall_adapter')
            current_time = datetime.now()

            for entry in gas_device_entries:
                gd_parsed_data = self.parse_data(entry, 'gas_device')
                combined_data = {
                    "device_id": wall_adapter_id,
                    "name": device_name,
                    "date": current_time.strftime("%d/%m/%Y"),
                    "time": current_time.strftime("%H:%M"),
                    **wa_parsed_data,
                    "gas_device_id": gas_device_id,
                    **gd_parsed_data,
                    "matx_id": wall_adapter_device.matx_id
                }

                device_data = DeviceData(
                    wall_adapter_id=wall_adapter_id,
                    gas_device_id=gas_device_id,
                    user_id=paired_device.user.id,
                    matx_id=wall_adapter_device.matx_id,
                    data=bytes.fromhex(wall_adapter_data + entry)
                )
                db.session.add(device_data)

                results.append({
                    "status": "success",
                    "message": "Data uploaded successfully.",
                    "data": combined_data
                })

            db.session.commit()
            self.check_offline_status(wall_adapter_id, paired_device.user.email)

            return results, 201

        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing bulk data: {str(e)}")
            return {"status": "error", "message": "An error occurred while processing bulk data."}, 500

    def parse_data(self, hex_data, data_type):
        connection_type_mapping = {"df": "NB-IoT", "de": "Wi-Fi"}
        power_source_mapping = {"c8": "Electricity", "c9": "Battery"}

        if data_type == 'wall_adapter':
            return {
                "connection_type": connection_type_mapping.get(hex_data[0:2], "Unknown"),
                "power_source": power_source_mapping.get(hex_data[2:4], "Unknown"),
                "wa_battery_status": str(int(hex_data[4:6], 16)),
                "wa_message_count": str(int(hex_data[6:12], 16))
            }
        elif data_type == 'gas_device':
            return {
                "weight": f"{int(hex_data[0:2], 16)}.{int(hex_data[2:4], 16):02d}",
                "gd_battery_status": str(int(hex_data[4:6], 16)),
                "gd_message_count": str(int(hex_data[6:12], 16))
            }

    def check_offline_status(self, wall_adapter_id, user_email):
        current_time = datetime.utcnow()
        
        device = Device.query.filter_by(wall_adapter_id=wall_adapter_id).first()
        if not device:
            logging.error(f"Device with wall_adapter_id {wall_adapter_id} not found in the device table.")
            return
        
        gas_device_id = device.gas_device_id
        
        last_log = DeviceEventLog.query.filter_by(device_id=gas_device_id, end_timestamp=None).first()
        
        if last_log:
            offline_duration = current_time - last_log.start_timestamp
            
            if offline_duration <= timedelta(minutes=15) and last_log.offline_message_count < 1:
                send_offline_notification(user_email, wall_adapter_id)
                self.log_notification(gas_device_id, current_time)
            elif offline_duration >= timedelta(minutes=60) and last_log.offline_message_count < 2:
                send_reminder_notification(user_email, wall_adapter_id)
                self.log_notification(gas_device_id, current_time)
        else:
            new_log = DeviceEventLog(device_id=gas_device_id, start_timestamp=current_time, offline_message_count=0)
            db.session.add(new_log)
            db.session.commit()

    def log_notification(self, gas_device_id, timestamp):
        last_log = DeviceEventLog.query.filter_by(device_id=gas_device_id).order_by(DeviceEventLog.start_timestamp.desc()).first()
        if last_log:
            last_log.offline_message_count += 1
            last_log.end_timestamp = timestamp
            db.session.commit()


@api.route('/user/<string:user_id>')
class GetUserData(Resource):
    def get(self, user_id):
        try:
            user = User.query.get(user_id)
            if not user:
                api.abort(404, f"User with ID {user_id} not found")

            paired_devices = PairedDevice.query.filter_by(user_id=user_id).all()
            if not paired_devices:
                return {"status": "success", "data": [], "message": "No paired devices found for this user"}, 200

            result = []

            for paired_device in paired_devices:
                device = Device.query.filter_by(matx_id=paired_device.matx_id).first()
                if not device:
                    continue

                device_data_entries = DeviceData.query.filter_by(wall_adapter_id=device.wall_adapter_id).order_by(DeviceData.timestamp.desc()).all()
                if not device_data_entries:
                    continue

                for data in device_data_entries:
                    gmt_plus_3_time = data.timestamp + timedelta(hours=3)
                    hex_data = data.data.hex()

                    if hex_data.startswith('4e'):
                        # Parse bulk data similar to POST endpoint
                        match = re.match(r'4e([0-9a-f]{12})\[(.*?)\]', hex_data, re.IGNORECASE)
                        if match:
                            wall_adapter_data = match.group(1)
                            gas_device_entries = match.group(2).split(',')

                            wa_parsed_data = self.parse_data(wall_adapter_data, 'wall_adapter')
                            
                            for entry in gas_device_entries:
                                gd_parsed_data = self.parse_data(entry, 'gas_device')
                                combined_data = {
                                    "device_id": device.wall_adapter_id,
                                    "name": paired_device.name or "Unnamed Device",
                                    "date": gmt_plus_3_time.strftime("%d/%m/%Y"),
                                    "time": gmt_plus_3_time.strftime("%H:%M"),
                                    **wa_parsed_data,
                                    "gas_device_id": device.gas_device_id,
                                    **gd_parsed_data,
                                    "matx_id": device.matx_id
                                }
                                result.append(combined_data)
                    else:
                        parsed_data = self.parse_single_data(data.data, data.data[0:1].hex())
                        result.append({
                            "device_id": device.wall_adapter_id,
                            "name": paired_device.name or "Unnamed Device",
                            "date": gmt_plus_3_time.strftime("%d/%m/%Y"),
                            "time": gmt_plus_3_time.strftime("%H:%M"),
                            "connection_type": parsed_data["connection_type"],
                            "power_source": parsed_data["power_source"],
                            "wa_battery_status": str(parsed_data["wall_adapter_battery"]),
                            "wa_message_count": str(parsed_data["wall_adapter_message_count"]),
                            "gas_device_id": device.gas_device_id,
                            "weight": parsed_data["weight"],
                            "gd_battery_status": str(parsed_data["gas_device_battery"]),
                            "gd_message_count": str(parsed_data["gas_device_message_count"]),
                            "matx_id": device.matx_id
                        })

            if not result:
                return {"status": "success", "data": [], "message": "No device data found for this user"}, 200

            return {"status": "success", "data": result}, 200

        except Exception as e:
            logging.error(f"Error retrieving user data for user_id {user_id}: {str(e)}")
            return {"status": "error", "message": "An error occurred while retrieving the user data"}, 500

    def parse_single_data(self, byte_data, message_type):
        connection_type_mapping = {"df": "NB-IoT", "de": "Wi-Fi"}
        power_source_mapping = {"c8": "Electricity", "c9": "Battery"}

        parsed_data = {
            "connection_type": None,
            "power_source": None,
            "wall_adapter_battery": None,
            "wall_adapter_message_count": None,
            "weight": None,
            "gas_device_battery": None,
            "gas_device_message_count": None
        }

        if message_type in ["1d", "1e", "2e", "3e"]:  # 13 BYTES messages
            parsed_data["connection_type"] = connection_type_mapping.get(byte_data[1:2].hex().lower(), "Unknown")
            parsed_data["power_source"] = power_source_mapping.get(byte_data[2:3].hex().lower(), "Unknown")
            parsed_data["wall_adapter_battery"] = int(byte_data[3])
            parsed_data["wall_adapter_message_count"] = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]
            
            weight_hex_part1 = byte_data[7:8].hex()
            weight_hex_part2 = byte_data[8:9].hex()
            parsed_data["weight"] = f"{int(weight_hex_part1, 16)}.{int(weight_hex_part2, 16):02d}"
            
            parsed_data["gas_device_battery"] = int(byte_data[9])
            parsed_data["gas_device_message_count"] = struct.unpack('>I', b'\x00' + byte_data[10:13])[0]

        elif message_type in ["2d", "3d", "4d", "5d", "6d", "7d", "8d", "9d"]:  # 7 BYTES messages
            parsed_data["connection_type"] = connection_type_mapping.get(byte_data[1:2].hex().lower(), "Unknown")
            parsed_data["power_source"] = power_source_mapping.get(byte_data[2:3].hex().lower(), "Unknown")
            parsed_data["wall_adapter_battery"] = int(byte_data[3])
            parsed_data["wall_adapter_message_count"] = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]

        return parsed_data

    def parse_data(self, hex_data, data_type):
        connection_type_mapping = {"df": "NB-IoT", "de": "Wi-Fi"}
        power_source_mapping = {"c8": "Electricity", "c9": "Battery"}

        if data_type == 'wall_adapter':
            return {
                "connection_type": connection_type_mapping.get(hex_data[0:2], "Unknown"),
                "power_source": power_source_mapping.get(hex_data[2:4], "Unknown"),
                "wa_battery_status": str(int(hex_data[4:6], 16)),
                "wa_message_count": str(int(hex_data[6:12], 16))
            }
        elif data_type == 'gas_device':
            return {
                "weight": f"{int(hex_data[0:2], 16)}.{int(hex_data[2:4], 16):02d}",
                "gd_battery_status": str(int(hex_data[4:6], 16)),
                "gd_message_count": str(int(hex_data[6:12], 16))
            }
