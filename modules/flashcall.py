import requests
from configparser import ConfigParser
from modules.statuses import *
config = ConfigParser()
config.read('config.ini')


class FlashCall:
    def __init__(self):
        email = config['flashcall']['email']
        api_key = config['flashcall']['token']
        self.url = f'https://{email}:{api_key}@gate.smsaero.ru/v2/flashcall/'

    def send(self, phone, code):
        attempt = 0
        while True:
            r = requests.get(url=self.url + 'send', params={'phone': phone, 'code': code})

            if 200 <= r.status_code <= 299:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}
            else:
                break

        return {'status': OK, 'data': r.json()['data']['id']}

    def check(self, call_id):
        attempt = 0
        while True:
            r = requests.get(url=self.url + 'status', params={'id': call_id})

            if 200 <= r.status_code <= 299:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}
            else:
                break

        return {'status': OK, 'data': r.json()['data']['status']}
