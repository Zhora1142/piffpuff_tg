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
            try:
                r = requests.get(url=self.url + 'send', params={'phone': phone, 'code': code})
            except Exception as e:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': str(e)}
                continue

            if not(200 <= r.status_code <= 299):
                attempt += 1

                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}

                try:
                    r = r.json()
                except ValueError:
                    continue

                if r['success'] is False:
                    if r['message'] == 'Validation error.':
                        s = r['data']['phone'][0]
                        s = s.replace('wait ', '')
                        s = s.replace(' seconds', '')
                        return {'status': WAIT, 'data': s}
                    else:
                        return {'status': UNKNOWN_ERROR, 'data': None}

            else:
                break

        return {'status': OK, 'data': r.json()['data']['id']}

    def check(self, call_id):
        attempt = 0
        while True:
            try:
                r = requests.get(url=self.url + 'status', params={'id': call_id})
            except Exception as e:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': str(e)}
                continue

            if 200 <= r.status_code <= 299:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}
            else:
                r = r.json()
                if r['status'] is False:
                    return {'status': UNKNOWN_ERROR, 'data': None}
                break

        return {'status': OK, 'data': r.json()['data']['status']}
