# temp_storage.py
import time

TEMP_REGISTRATION_STORE = {}

def store_temp_registration(email, data):
    expiry_time = time.time() + 600  # 10 minutes from now
    TEMP_REGISTRATION_STORE[email] = {'data': data, 'expiry': expiry_time}

def get_temp_registration(email):
    entry = TEMP_REGISTRATION_STORE.get(email)
    if entry and entry['expiry'] > time.time():
        return entry['data']
    TEMP_REGISTRATION_STORE.pop(email, None)  # Remove expired entry
    return None
