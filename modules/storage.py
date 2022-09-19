import logging
import random
import threading
import requests
from requests.auth import HTTPBasicAuth
from modules.statuses import *
from configparser import ConfigParser

config = ConfigParser()
config.read('config.ini')
link = config['storage']['link']


# Chunk list
def chunks(lst, n):
    result = []
    for i in range(0, len(lst), n):
        result.append(lst[i:i + n])

    return result


def generate_id():
    letters = ['a', 'b', 'c', 'd', 'e', 'f']
    digits = ['0', '1', '2', '3', '4', '5', '6', '7', '8']
    sync_id = ''
    for i in range(8):
        sync_id += random.choice(letters + digits)
    sync_id += '-'
    for i in range(3):
        for j in range(4):
            sync_id += random.choice(letters + digits)
        sync_id += '-'
    for i in range(12):
        sync_id += random.choice(letters + digits)

    return sync_id


# Create tree from product path
def tree_from_path(path, end, p_id):
    tree = {}
    if len(path) == 1:
        tree[path[0]] = [{'name': end, 'id': p_id}]
    else:
        tree[path[0]] = tree_from_path(path[1:], end, p_id)
    return tree


# Merge two dicts
def merge_dicts(d1, d2):
    for k, v in d2.items():
        if type(v) is dict:
            if k in d1:
                d1[k] = merge_dicts(d1[k], v)
            else:
                d1[k] = v
        else:
            if k in d1:
                d1[k] = d1[k] + v
            else:
                d1[k] = v
    return d1


class ProductChecker(threading.Thread):
    def __init__(self, session, product_id):
        threading.Thread.__init__(self)
        self.result = None
        self.session = session
        self.url = 'https://online.moysklad.ru/api/remap/1.2/entity/'
        self.product_id = product_id

    def request(self, **kwargs):
        result = {'status': None, 'data': None}
        loop_count = 5

        i = 0
        while i < loop_count:
            try:
                r = self.session.get(**kwargs)
                r = r.json()
            except Exception as e:
                result['status'] = UNKNOWN_ERROR
                result['data'] = e
                logging.error(f'Product checker request error - {e}')
            else:
                if 'errors' in r:
                    if r['errors'][0]['code'] in (1073, 1049):
                        continue

                    elif r['errors'][0]['code'] == 1021:
                        result['status'] = NO_SUCH_ENTITY
                        result['data'] = None

                    else:
                        result['status'] = UNKNOWN_ERROR
                        result['data'] = r['errors'][0]
                        logging.error(f'Product checker storage error - {r["errors"][0]}')
                else:
                    result['status'] = OK
                    result['data'] = r
                    break

            i += 1

        return result

    def run(self):
        data = self.request(url=self.url + 'assortment', params={'filter': f'id={self.product_id};stockStore={link}'})

        if data['status'] != OK:
            return

        # Send delete product command if not found
        if not data['data']['rows']:
            self.result = {'id': self.product_id, 'delete': True}

        product = data['data']['rows'][0]

        product_name = product['name']
        if 'description' in data:
            description = data['description'].split('==')
            if len(description) == 3:
                product_name = f'{description[0]} {description[1]}'

        self.result = {'name': product_name, 'id': self.product_id, 'price': product['salePrices'][0]['value'] / 100,
                       'stock': int(product['stock'])}


class GroupChecker(threading.Thread):
    def __init__(self, session, group_id):
        threading.Thread.__init__(self)
        self.result = None
        self.session = session
        self.url = 'https://online.moysklad.ru/api/remap/1.2/entity/'
        self.group_id = group_id

    def request(self, **kwargs):
        result = {'status': None, 'data': None}
        loop_count = 5

        i = 0
        while i < loop_count:
            try:
                r = self.session.get(**kwargs)
                r = r.json()
            except Exception as e:
                result['status'] = UNKNOWN_ERROR
                result['data'] = e
                logging.error(f'Group checker request error - {e}')
            else:
                if 'errors' in r:
                    if r['errors'][0]['code'] in (1073, 1049):
                        continue

                    elif r['errors'][0]['code'] == 1021:
                        result['status'] = NO_SUCH_ENTITY
                        result['data'] = None

                    else:
                        result['status'] = UNKNOWN_ERROR
                        result['data'] = r['errors'][0]
                        logging.error(f'Group checker storage error - {r["errors"][0]}')
                else:
                    result['status'] = OK
                    result['data'] = r
                    break

            i += 1

        return result

    def run(self):
        group = self.request(url=self.url + f'productfolder/{self.group_id}')

        if group['status'] != OK:
            return

        path = group['data']['pathName'] + '/' + group['data']['name'] if group['data']['pathName'] \
            else group['data']['name']

        while 1:
            result = self.request(url=self.url + 'assortment', params={'filter': f'pathname~{path};'
                                                                                 f'stockMode=positiveOnly;'
                                                                                 f'stockStore={link}',
                                                                       'limit': 1})
            if result['status'] != OK or not result['data']['rows']:
                return

            break

        row = result['data']['rows'][0]
        if row['pathName'] == path or path + '/' in row['pathName']:
            self.result = {'name': group['data']['name'], 'id': self.group_id}


class Storage:
    def __init__(self):
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config['storage']['username'], config['storage']['password'])
        self.url = 'https://online.moysklad.ru/api/remap/1.2/entity/'

        self.bm_header = {
            'Lognex-Discount-API-Auth-Token': config['storage']['token']
        }
        self.retail_id = config['storage']['retail_id']
        self.bm_url = 'https://bm-app.com/moysklad/'
        self.retail_name = config['storage']['retail_name']
        self.bm_token = config['bonus']['token']

    def request(self, **kwargs):
        result = {'status': None, 'data': None}
        loop_count = 5

        i = 0
        while i < loop_count:
            try:
                r = self.session.get(**kwargs)
                r = r.json()
            except Exception as e:
                result['status'] = UNKNOWN_ERROR
                result['data'] = e
                logging.error(f'Storage request error - {e}')
            else:
                if 'errors' in r:
                    if r['errors'][0]['code'] in (1073, 1049):
                        continue

                    elif r['errors'][0]['code'] == 1021:
                        result['status'] = NO_SUCH_ENTITY
                        result['data'] = None

                    else:
                        result['status'] = UNKNOWN_ERROR
                        result['data'] = r['errors'][0]
                        logging.error(f'Storage storage error - {r["errors"][0]}')
                else:
                    result['status'] = OK
                    result['data'] = r
                    break

            i += 1

        return result

    def get_groups_by_parent_id(self, parent_id=None, first_element_id=None, last_element_id=None):
        if first_element_id or last_element_id and not parent_id:
            par = self.request(url=self.url + f'productfolder/{last_element_id if last_element_id else first_element_id}')
            if par['status'] != OK:
                return par
            if 'productFolder' in par['data']:
                parent_id = par['data']['productFolder']['meta']['href'].split('/')[-1]

        folder_name = 'Каталог товаров'

        # Get path for searching folders
        if parent_id:
            group = self.request(url=self.url + f'productfolder/{parent_id}')

            if group['status'] != OK:
                return group

            folder_name = group['data']['name']
            path = group['data']['pathName'] + '/' + group['data']['name'] if group['data']['pathName'] \
                else group['data']['name']

            if 'productFolder' in group['data']:
                parent = group['data']['productFolder']['meta']['href'].split('/')[-1]
            else:
                parent = 'main'
        else:
            path = ''
            parent = None

        # Get folders list
        folders = self.request(url=self.url + 'productfolder', params={'filter': f'pathName={path}'})

        if folders['status'] != OK:
            return folders

        if not folders['data']['rows']:
            return {'status': OK, 'data': []}

        folders = folders['data']['rows']
        folders.sort(key=lambda product: product['name'])

        # Remove useless data except ids
        raw_folders = [i['id'] for i in folders]

        first_page = None
        last_page = None

        # Cut everything before first element
        if first_element_id:
            try:
                index = raw_folders.index(first_element_id)
            except ValueError:
                return {'status': FOLDER_DOES_NOT_EXIST, 'data': None}
            else:
                cut_folders = raw_folders[index + 1:]
                first_page = False

        # Cut everything after last element
        elif last_element_id:
            try:
                index = raw_folders.index(last_element_id)
            except ValueError:
                return {'status': FOLDER_DOES_NOT_EXIST, 'data': None}
            else:
                cut_folders = raw_folders[:index]
                cut_folders.reverse()

        else:
            cut_folders = raw_folders
            first_page = True

        cut_folders = chunks(cut_folders, 5)

        # Get first 4 available folders
        result = []
        flag = False
        for chunk in cut_folders:
            threads = [GroupChecker(session=self.session, group_id=group_id) for group_id in chunk]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            for thread in threads:
                if thread.result:
                    result.append(thread.result)
                    if len(result) == 5:
                        flag = True
                        break
            if flag:
                break
        if result:
            if last_element_id:
                result.reverse()

            # Check if current page is the last
            folder_list = raw_folders[raw_folders.index(result[-1]['id']) + 1:]
            if self.if_group_any_groups_after(groups=folder_list):
                last_page = True

            # Check if current page is the first
            if first_page is None:
                folder_list = raw_folders[:raw_folders.index(result[0]['id'])]
                folder_list.reverse()
                if self.if_group_any_groups_after(groups=folder_list):
                    first_page = True
                else:
                    first_page = False

        return {'status': OK, 'data': {'groups': result, 'is_first_page': first_page, 'is_last_page': last_page,
                                       'parent_id': parent, 'name': folder_name}}

    def if_group_any_groups_after(self, groups):
        groups = chunks(groups, 5)

        for chunk in groups:
            threads = [GroupChecker(session=self.session, group_id=group_id) for group_id in chunk]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            for thread in threads:
                if thread.result:
                    return False

        return True

    def get_products_by_parent_id(self, parent_id):
        folder = self.request(url=self.url + f'productfolder/{parent_id}')

        if folder['status'] != OK:
            return folder

        # Text for message
        name = folder['data']['name']

        # Get parent for "back" button
        if 'productFolder' in folder['data']:
            pid = folder['data']['productFolder']['meta']['href'].split('/')[-1]
        else:
            pid = 'main'

        products = self.request(url=self.url + 'assortment',
                                params={'filter': f'productFolder={self.url + "productfolder/" + parent_id};'
                                                  f'stockMode=positiveOnly;'
                                                  f'stockStore={link}'})

        if products['status'] != OK:
            return products

        # Remove everything useless from products
        result = []
        for product in products['data']['rows']:
            button_name = product['name']
            if 'description' in product:
                description = product['description'].split('==')
                if len(description) == 3:
                    button_name = description[1]
            result.append({'name': button_name, 'id': product['id']})

        return {'status': OK, 'data': {'products': result, 'parent_id': pid, 'name': name}}

    def get_product(self, product_id):
        product = self.request(url=self.url + 'assortment', params={'filter': f'id={product_id};'
                                                                              f'stockStore={link}'})

        if product['status'] != OK:
            return product

        product = product['data']['rows'][0]
        parent_id = product['productFolder']['meta']['href'].split('/')[-1]

        picture = None
        image_data = self.request(url=product['images']['meta']['href'])

        if image_data['status'] != OK:
            return image_data

        if image_data['data']['rows']:
            href = image_data['data']['rows'][0]['meta']['downloadHref']

            try:
                pic_bytes = self.session.get(url=href)
            except Exception as e:
                logging.error(f'Getting product picture bytes error - {e}')
                return {'status': UNKNOWN_ERROR, 'data': str(e)}

            # I don't know what does it do...
            if not pic_bytes:
                logging.error(f'Getting picture bytes error - no picture bytes')
                return {'status': UNKNOWN_ERROR, 'data': None}

            picture = pic_bytes.content

        product_name = product['name']
        product_description = None

        if 'description' in product:
            description = product['description'].split('==')
            if len(description) == 3:
                product_name = f'{description[0]} {description[1]}'
                product_description = description[2]

        return {'status': OK, 'data': {'name': product_name,
                                       'price': product['salePrices'][0]['value'] / 100,
                                       'stock': int(product['stock']),
                                       'parent_id': parent_id,
                                       'picture': picture,
                                       'description': product_description}}

    def get_products_data(self, products):
        products = chunks(products, 5)
        result = []

        for chunk in products:
            threads = [ProductChecker(session=self.session, product_id=product_id) for product_id in chunk]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            for thread in threads:
                result.append(thread.result)

        return result

    def search(self, request):
        assortment = self.request(url=self.url + 'assortment',
                                  params={'filter': f'stockMode=positiveOnly;'
                                                    f'search={request};'
                                                    f'stockStore={link}'})

        if assortment['status'] != OK:
            return assortment

        result = {}

        if not assortment['data']['rows']:
            return {'status': NOT_FOUND, 'data': None}

        for i in assortment['data']['rows']:
            pn = i['pathName'].replace("\'", "`")
            path = pn.split('/')
            name = i['name']
            product_id = i['id']

            if 'description' in i:
                description = i['description'].split('==')
                if len(description) == 3:
                    name = description[1]

            a = tree_from_path(path=path, end=name, p_id=product_id)

            try:
                result = merge_dicts(result, a)
            except TypeError:
                logging.error('MERGING DICTS ERROR')
                logging.error(str(result))
                logging.error(str(a))
                return {'status': UNKNOWN_ERROR, 'data': None}

        return {'status': OK, 'data': {'tree': result}}

    def create_user(self, phone):
        sync_id = generate_id()
        data = {
            "retailStore": {
                "meta": {
                    "href": f"https://online.moysklad.ru/api/remap/1.1/entity/retailstore/{self.retail_id}",
                    "id": self.retail_id
                },
                "name": self.retail_name
            },
            "meta": {
                "href": f"https://online.moysklad.ru/api/remap/1.1/entity/counterparty/{sync_id}",
                "id": sync_id
            },
            "name": phone,
            "phone": phone,
        }

        attempt = 0
        while True:
            try:
                r = requests.post(url=self.bm_url + 'counterparty', headers=self.bm_header, json=data)
            except Exception as e:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': str(e)}
                continue

            if r.status_code not in (200, 201):
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}
            else:
                break

        attempt = 0
        while True:
            try:
                r = self.session.post(url=self.url + 'counterparty', json={'name': phone, 'phone': phone,
                                                                           'companyType': 'individual'})
            except Exception as e:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': str(e)}
                continue

            if r.status_code not in (200, 201):
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}
            else:
                break

        return {'status': OK, 'data': None}

    def get_balance(self, phone):
        headers = {'TOKEN': self.bm_token}
        attempt = 0
        while True:
            try:
                r = requests.post(url='https://bm-app.com/admin_v2/customers/findCustomer', headers=headers,
                                  json={'field': phone, 'offset': '0'})
            except Exception as e:
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': str(e)}
                continue

            if r.status_code != 200:
                if r.status_code == 401:
                    self.get_bm_token()
                    result = self.get_balance(phone=phone)
                    return result
                attempt += 1
                if attempt == 4:
                    return {'status': UNKNOWN_ERROR, 'data': {'code': r.status_code}}
            else:
                break

        r = r.json()

        if not r['customers']:
            return {'status': NOT_FOUND, 'data': None}

        response = {
            'balance': int(r['customers'][0]['customerMarkParameters']['mark']),
            'level': r['customers'][0]['customerMarkParameters']['level']
        }
        return {'status': OK, 'data': response}

    def get_bm_token(self):
        data = {
            'login': config['bonus']['login'],
            'password': config['bonus']['password']
        }
        r = requests.post(url='https://bm-app.com/adminLogIn', json=data)

        if r.status_code == 200:
            print('Замена токена успешна')
            self.bm_token = r.json()['token']
        else:
            print('Заменить токен не удалось')