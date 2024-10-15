from datetime import datetime, timedelta
import random
import string
from flask_restx import Namespace, Resource, fields # type: ignore
from flask import request # type: ignore
from flask_jwt_extended import create_access_token, get_jwt, jwt_required # type: ignore
from mailjet_rest import Client # type: ignore
from user_agents import parse # type: ignore

from app.user_management.models import OTP, User, UserLog
from common.db import db

api = Namespace('users', description='User management operations')

# Updated API models
login_model = api.model('Login', {
    'email': fields.String(required=True, description='User email'),
    'user_type': fields.String(description='User type (customer or business)', enum=['customer', 'business']),
    'channel': fields.String(required=True, description='Channel type (e.g., web, mobile)'),
})

verify_otp_model = api.model('VerifyOtp', {
    'email': fields.String(required=True, description='The user email'),
    'otp': fields.String(required=True, description='The OTP sent to the user'),
})

resend_otp_model = api.model('ResendOtp', {
    'email': fields.String(required=True, description='The user email'),
    'channel': fields.String(required=True, description='Channel type (e.g., web, mobile)'),
})



api_key = '98baa56555339c6e0edb75d67e09e24d'
api_secret = 'd874ddb225fa31b72b6c1e52912be0b8'
mailjet = Client(auth=(api_key, api_secret), version='v3.1')

def send_otp_via_mailjet(email, otp):
    template_id = 6286455
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
                "Subject": "Your OTP Code",
                "Variables": {
                    "otp": otp
                }
            }
        ]
    }
    
    try:
        result = mailjet.send.create(data=data)
        if result.status_code == 200:
            return result.status_code, result.json()
        else:
            return result.status_code, {'message': 'Failed to send OTP', 'details': result.json()}
    
    except Exception as e:
        return 500, {'message': 'Internal Server Error', 'details': str(e)}

def extract_user_agent_info(user_agent_string):
    user_agent = parse(user_agent_string)
    return f"{user_agent.browser.family} {user_agent.browser.version_string} on {user_agent.os.family} {user_agent.os.version_string}"

@api.route('/register')
class UserRegister(Resource):
    @api.doc('register_user')
    @api.expect(login_model)
    def post(self):
        try:
            data = request.json
            email = data['email']
            user_type = data.get('user_type', '').lower()  # Convert user_type to lowercase
            channel = data['channel']
            user_agent_string = request.headers.get('User-Agent', '')
            user_agent = extract_user_agent_info(user_agent_string)

            # Check if the user already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                return {'message': 'User already exists. Please login instead.'}, 400

            # Generate OTP and create a new OTP record
            otp = ''.join(random.choices(string.digits, k=6))
            otp_expiration = datetime.utcnow() + timedelta(minutes=10)
            
            otp_record = OTP(
                email=email,
                otp=otp,
                action='register',
                expired_at=otp_expiration,
                user_type=user_type,
                channel=channel,
                user_agent=user_agent
            )
            db.session.add(otp_record)
            db.session.commit()

            # Send OTP to the user via email
            status_code, response = send_otp_via_mailjet(email, otp)
            if status_code != 200:
                return {'message': 'Failed to send OTP'}, 500

            return {'message': f'OTP sent to {email} for registration.'}, 200
        except Exception as e:
            return {'message': str(e)}, 500

@api.route('/login')
class UserLogin(Resource):
    @api.doc('login_user')
    @api.expect({'email': fields.String(required=True, description='User email')})
    def post(self):
        try:
            data = request.json
            email = data['email']
            user_agent_string = request.headers.get('User-Agent', '')
            user_agent = extract_user_agent_info(user_agent_string)

            # Check if the user exists
            existing_user = User.query.filter_by(email=email).first()
            if not existing_user:
                return {'message': 'User does not exist. Please register first.'}, 400

            # Generate OTP and create a new OTP record
            otp = ''.join(random.choices(string.digits, k=6))
            otp_expiration = datetime.utcnow() + timedelta(minutes=10)
            
            otp_record = OTP(
                email=email,
                otp=otp,
                action='login',
                expired_at=otp_expiration,
                user_type=None,  # Not required for login
                channel='web',  # Default channel
                user_agent=user_agent
            )
            db.session.add(otp_record)
            db.session.commit()

            # Send OTP to the user via email
            status_code, response = send_otp_via_mailjet(email, otp)
            if status_code != 200:
                return {'message': 'Failed to send OTP'}, 500

            return {'message': f'OTP sent to {email} for login.'}, 200
        except Exception as e:
            return {'message': str(e)}, 500


@api.route('/verify-otp')
class UserVerifyOTP(Resource):
    @api.doc('verify_otp')
    @api.expect(verify_otp_model)
    def post(self):
        try:
            data = request.json
            email = data['email']
            otp = data['otp']

            # Fetch OTP record to validate
            otp_record = OTP.query.filter_by(email=email, otp=otp, is_valid=True).first()

            if otp_record and not otp_record.is_expired():
                existing_user = User.query.filter_by(email=email).first()

                # Check if OTP was for registration and user does not exist
                if otp_record.action == 'register' and not existing_user:
                    # Register the user with the provided user_type
                    user = User(email=email, user_type=otp_record.user_type)
                    db.session.add(user)
                    db.session.commit()
                    existing_user = user

                # Generate an access token after successful verification
                access_token = create_access_token(identity=email)

                # Invalidate the OTP after it's used
                otp_record.invalidate()

                # Log the OTP verification action
                log = UserLog(
                    user_id=existing_user.id,
                    email=email,
                    action='verify_otp',
                    channel=otp_record.channel,
                    user_agent=otp_record.user_agent
                )
                db.session.add(log)
                db.session.commit()

                # Fetch user information and convert UUIDs and datetime to ISO format
                user_info = {
                    'email': existing_user.email,
                    'user_id': str(existing_user.id),
                    'fullname': "",
                    'mobile': "",
                    'created_at': existing_user.created_at.isoformat(),
                    'user_type': existing_user.user_type
                }

                # Fetch paired devices
                paired_devices = []
                paired_device_records = existing_user.paired_devices
                if paired_device_records:
                    for paired_device in paired_device_records:
                        paired_devices.append({
                            'matx_id': paired_device.device.matx_id,
                            'name': paired_device.name,
                            'paired_at': paired_device.timestamp.isoformat()
                        })

                # Add the devices field based on whether paired_devices is empty or not
                user_info['devices'] = 'Yes' if paired_devices else 'No'

                # Prepare the response data
                response_data = {
                    'message': 'OTP verified successfully',
                    'access_token': access_token,
                    'user_info': user_info
                }

                # Include paired_devices only if there are any
                if paired_devices:
                    response_data['paired_devices'] = paired_devices

                return response_data, 200

            return {'message': 'Invalid or expired OTP'}, 400

        except Exception as e:
            return {'message': str(e)}, 500


@api.route('/resend-otp')
class UserResendOTP(Resource):
    @api.doc('resend_otp')
    @api.expect(resend_otp_model)
    def post(self):
        try:
            data = request.json
            email = data['email']
            channel = data['channel']

            user_agent_string = request.headers.get('User-Agent', '')
            user_agent = extract_user_agent_info(user_agent_string)

            recent_otps = OTP.query.filter_by(email=email).filter(OTP.created_at >= datetime.utcnow() - timedelta(minutes=10)).all()
            if len(recent_otps) >= 5:
                return {'message': 'Too many OTP requests. Please wait for 10 minutes before trying again.'}, 429

            # Generate a new OTP and update the record
            new_otp = ''.join(random.choices(string.digits, k=6))
            otp_expiration = datetime.utcnow() + timedelta(minutes=10)

            otp_record = OTP(email=email, otp=new_otp, expired_at=otp_expiration, action='resend', user_type=None, channel=channel, user_agent=user_agent)
            db.session.add(otp_record)
            db.session.commit()

            # Send new OTP via email
            status_code, response = send_otp_via_mailjet(email, new_otp)
            if status_code != 200:
                return {'message': 'Failed to resend OTP'}, 500

            # Log the action
            existing_user = User.query.filter_by(email=email).first()
            log = UserLog(
                user_id=existing_user.id if existing_user else None,
                action='resend_otp',
                channel=channel,
                user_agent=user_agent
            )
            db.session.add(log)
            db.session.commit()

            return {'message': f'OTP resent to {email}.'}, 200

        except Exception as e:
            return {'message': str(e)}, 500