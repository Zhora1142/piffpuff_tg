import requests
import vk_api

from json import dumps, loads
from modules.storage import Storage
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from modules.statuses import *
from modules.sql import MysqlCollector
from configparser import ConfigParser

config = ConfigParser()
config.read('config.ini')

s = Storage()
sql = MysqlCollector(**config['sql'])
sql_sales = MysqlCollector(server=config['sql']['server'], username=config['sql']['username'],
                           passwd=config['sql']['passwd'], db='bot')
session = vk_api.VkApi(**config['vk'], api_version='5.131')
api = session.get_api()


def generate_folders(parent_id=None, last_element_id=None, first_element_id=None):
    keyboard = InlineKeyboardMarkup()

    data = s.get_groups_by_parent_id(parent_id=parent_id,
                                     last_element_id=last_element_id,
                                     first_element_id=first_element_id)

    if data['status'] != OK:
        return data

    if not data['data']:
        return generate_products(parent_id=parent_id)

    if not data['data']['groups']:
        return {'status': EMPTY_FOLDER, 'data': None}

    for folder in data['data']['groups']:
        cdata = f'select_group?p={folder["id"]}'
        keyboard.add(InlineKeyboardButton(text=folder['name'], callback_data=cdata))

    buttons = []
    if not data['data']['is_first_page']:
        cdata = f'select_group?l={data["data"]["groups"][0]["id"]}'
        buttons.append(InlineKeyboardButton(text='◀', callback_data=cdata))

    if not data['data']['is_last_page']:
        cdata = f'select_group?f={data["data"]["groups"][-1]["id"]}'
        buttons.append(InlineKeyboardButton(text='▶', callback_data=cdata))

    keyboard.add(*buttons)

    if data['data']['parent_id']:
        pid = None if data['data']['parent_id'] == 'main' else data['data']['parent_id']
        if pid:
            keyboard.add(InlineKeyboardButton(text='🎛 В меню', callback_data=f'menu'),
                         InlineKeyboardButton(text='↪ Назад', callback_data=f'select_group?p={pid}'))
        else:
            keyboard.add(InlineKeyboardButton(text='🎛 В меню', callback_data=f'menu'),
                         InlineKeyboardButton(text='↪ Назад', callback_data=f'select_group'))
    else:
        keyboard.add(InlineKeyboardButton(text='🎛 В меню', callback_data=f'menu'))

    return {'status': OK, 'data': {'reply_markup': keyboard, 'text': data['data']['name']}}


def generate_products(parent_id, offset=0):
    keyboard = InlineKeyboardMarkup()

    data = s.get_products_by_parent_id(parent_id=parent_id)

    if data['status'] != OK:
        return data['status']

    if not data['data']['products']:
        return {'status': EMPTY_FOLDER, 'data': None}

    products = data['data']['products'][offset * 5:offset * 5 + 5]

    if not products:
        return generate_products(parent_id=parent_id)

    for product in products:
        keyboard.add(InlineKeyboardButton(text=product['name'],
                                          callback_data=f'select_product?p={product["id"]},o={offset}'))

    buttons = []
    if data['data']['products'][0] != products[0]:
        buttons.append(InlineKeyboardButton(text='◀', callback_data=f'show_products?p={parent_id},o={offset - 1}'))

    if data['data']['products'][-1] != products[-1]:
        buttons.append(InlineKeyboardButton(text='▶', callback_data=f'show_products?p={parent_id},o={offset + 1}'))

    keyboard.add(*buttons)

    keyboard.add(InlineKeyboardButton(text='🎛 В меню', callback_data='menu'),
                 InlineKeyboardButton(text='↪ Назад', callback_data=f'select_group?p={data["data"]["parent_id"]}'))

    return {'status': OK, 'data': {'reply_markup': keyboard, 'text': data['data']['name']}}


def generate_product(product_id, user_id, from_basket=0, from_search=0, offset=0):
    product = s.get_product(product_id=product_id)

    if product['status'] != OK:
        return product

    message = f'{product["data"]["name"]}\n\n'
    if product['data']['description']:
        message += f'{product["data"]["description"]}\n\n'

    if product['data']['stock'] <= 0:
        stock_info = 'нет'
    elif 1 <= product['data']['stock'] <= 5:
        stock_info = 'мало'
    else:
        stock_info = 'много'

    message += f'Наличие: {stock_info}\n'
    message += f'Цена: {product["data"]["price"]} руб.'

    keyboard = InlineKeyboardMarkup()

    user_basket = sql.select(table='users', where=f'id={user_id}')

    user_basket = loads(user_basket['data']['basket'])

    buttons = []
    if product_id not in user_basket:
        cdata = f'add?i={product_id},s={product["data"]["stock"]},b={from_basket}'
        buttons.append(InlineKeyboardButton(text='Добавить в корзину', callback_data=cdata))
    else:
        buttons.append(InlineKeyboardButton(text=f'{user_basket[product_id]} шт.', callback_data='null'))
        cdata = f'rem?i={product_id},s={product["data"]["stock"]},b={from_basket}'
        buttons.append(InlineKeyboardButton(text='-', callback_data=cdata))

        if user_basket[product_id] + 1 <= product['data']['stock']:
            cdata = f'add?i={product_id},s={product["data"]["stock"]},b={from_basket}'
            buttons.append(InlineKeyboardButton(text='+', callback_data=cdata))

    keyboard.add(*buttons)

    buttons = [InlineKeyboardButton(text='В меню', callback_data='menu_search' if from_search else 'menu')]

    if from_basket:
        cdata = 'show_basket'
    elif from_search:
        cdata = f'ss?o={offset}'
    else:
        cdata = f'show_products?p={product["data"]["parent_id"]},o={offset}'

    buttons.append(InlineKeyboardButton(text='Назад', callback_data=cdata))
    keyboard.add(*buttons)

    r = {'status': OK, 'data': {'reply_markup': keyboard}}
    if product['data']['picture']:
        r['data']['photo'] = product['data']['picture']
        r['data']['caption'] = message
    else:
        r['data']['text'] = message

    return r


def generate_basket(user_id, selected=0):
    user_basket = sql.select(table='users', where=f'id={user_id}')
    user_basket = loads(user_basket['data']['basket'])
    keyboard = InlineKeyboardMarkup()

    if not user_basket:
        message = 'Корзина пуста'
        keyboard.add(InlineKeyboardButton(text='В меню', callback_data='menu'))

        return {'status': OK, 'data': {'reply_markup': keyboard, 'text': message}}

    message = 'Корзина:\n'
    products = [k for k in user_basket.keys()]

    products = s.get_products_data(products=products)

    temp = []
    for product in products:
        if 'delete' in product:
            user_basket.pop(product['id'])
        else:
            temp.append(product)
    products = temp

    sql.update(table='users', values={'basket': dumps(user_basket)}, where=f'id={user_id}')

    if not user_basket:
        message = 'Корзина пуста'
        keyboard.add(InlineKeyboardButton(text='В меню', callback_data='menu'))

        return {'status': OK, 'data': {'reply_markup': keyboard, 'text': message}}

    if selected and selected > len(products) - 1:
        selected = 0

    price = 0
    message += '\n' + '-' * 28

    for product in products:
        message += '\n'

        if products.index(product) == selected:
            message += '👉🏻'

        message += f'{product["name"]} ({user_basket[product["id"]]}) шт.'

        if product['stock'] <= 0:
            message += '\n❗Товар закончился'
        elif user_basket[product['id']] > product['stock']:
            message += f'\n❗В наличии только {product["stock"]} шт.'
            price += product['price'] * product['stock']
        else:
            price += product['price'] * user_basket[product['id']]
        message += '\n' + '-' * 28

    message += f'\n\nОбщая сумма: {price} руб.'

    buttons = []
    cdata = f'select_product?p={products[selected]["id"]},f=1'
    buttons.append(InlineKeyboardButton(text='К товару', callback_data=cdata))
    cdata = f'del?i={products[selected]["id"]},s={selected}'
    buttons.append(InlineKeyboardButton(text='Удалить товар', callback_data=cdata))
    keyboard.add(*buttons)

    keyboard.add(InlineKeyboardButton(text='Очистить корзину', callback_data='clear_basket'))

    buttons = []
    if selected > 0:
        buttons.append(InlineKeyboardButton(text='🔼', callback_data=f'show_basket?s={selected - 1}'))
    if selected + 1 <= len(products) - 1:
        buttons.append(InlineKeyboardButton(text='🔽', callback_data=f'show_basket?s={selected + 1}'))
    keyboard.add(*buttons)

    keyboard.add(InlineKeyboardButton(text='В меню', callback_data='menu'))

    return {'status': OK, 'data': {'reply_markup': keyboard, 'text': message}}


def generate_basket_empty(user_id):
    user_basket = sql.select(table='users', where=f'id={user_id}')
    user_basket = loads(user_basket['data']['basket'])

    if not user_basket:
        return None

    message = 'Корзина:\n'
    products = [k for k in user_basket.keys()]

    products = s.get_products_data(products=products)

    temp = []
    for product in products:
        if 'delete' in product:
            user_basket.pop(product['id'])
        else:
            temp.append(product)
    products = temp

    sql.update(table='users', values={'basket': dumps(user_basket)}, where=f'id={user_id}')

    if not user_basket:
        return None

    price = 0
    message += '\n' + '-' * 28

    for product in products:
        message += '\n'

        message += f'{product["name"]} ({user_basket[product["id"]]}) шт.'

        if product['stock'] <= 0:
            message += '\n❗Товар закончился'
        elif user_basket[product['id']] > product['stock']:
            message += f'\n❗В наличии только {product["stock"]} шт.'
            price += product['price'] * product['stock']
        else:
            price += product['price'] * user_basket[product['id']]
        message += '\n' + '-' * 28

    message += f'\n\nОбщая сумма: {price} руб.'

    return message


def search(user_id, request=None, offset=0):
    tree = sql.select(table='users', where=f'id={user_id}')

    title = 'Результаты поиска'

    path = tree['data']['search_path'].split('*')
    if path == ['']:
        path = []
    if request is None:
        pass
    elif request == 'back':
        path = path[:-1]
    else:
        path.append(request)
        title += f'\n\n{request}'
    sql.update(table='users', values={'search_path': '*'.join(path)}, where=f'id={user_id}')

    tree = loads(tree['data']['search_request'])

    result = tree
    for i in path:
        if i not in result:
            return {'status': SEARCH_ERROR, 'data': None}

        result = result[i]

    keyboard = InlineKeyboardMarkup()

    if isinstance(result, dict):
        keys = list(result.keys())
        k = keys[offset * 5: offset * 5 + 5]
        for i in k:
            keyboard.add(InlineKeyboardButton(text=i, callback_data=f'ss?r={i}'))

        buttons = []
        if keys[0] != k[0]:
            buttons.append(InlineKeyboardButton(text='◀', callback_data=f'ss?o={offset-1}'))
        if keys[-1] != k[-1]:
            buttons.append(InlineKeyboardButton(text='▶', callback_data=f'ss?o={offset+1}'))
        keyboard.add(*buttons)
    else:
        products = result[offset * 5:offset * 5 + 5]
        for i in products:
            keyboard.add(InlineKeyboardButton(text=i['name'], callback_data=f'select_product?p={i["id"]},o={offset},'
                                                                            f's=1'))
        buttons = []
        if result[0] != products[0]:
            buttons.append(InlineKeyboardButton(text='◀', callback_data=f'ss?o={offset - 1}'))
        if result[-1] != products[-1]:
            buttons.append(InlineKeyboardButton(text='▶', callback_data=f'ss?o={offset + 1}'))
        keyboard.add(*buttons)

    buttons = [InlineKeyboardButton(text='В меню', callback_data=f'menu_search')]

    if path:
        buttons.append(InlineKeyboardButton(text='Назад', callback_data=f'ss?r=back'))

    keyboard.add(*buttons)

    return {'status': OK, 'data': {'text': title, 'reply_markup': keyboard}}


def generate_sales(page=0):
    sales = sql_sales.select(table='sales')['data']
    if not isinstance(sales, list):
        sales = [sales]

    if page > len(sales) - 1:
        page = 0

    keyboard = InlineKeyboardMarkup()

    keyboard.add(InlineKeyboardButton(text=sales[page]['button_text'], url=sales[page]['button_link']))
    buttons = []
    if page != 0:
        buttons.append(InlineKeyboardButton(text='◀', callback_data=f'sales?p={page - 1}'))
    if page < len(sales) - 1:
        buttons.append(InlineKeyboardButton(text='▶', callback_data=f'sales?p={page + 1}'))

    keyboard.add(*buttons)

    keyboard.add(InlineKeyboardButton(text='В меню', callback_data='menu'))

    photo_data = api.photos.getById(photos=sales[page]['photo_id'])[0]['sizes']
    photo_data.sort(key=lambda v: -v['width'])
    photo_url = photo_data[0]['url']
    r = requests.get(photo_url)
    photo_bytes = r.content

    text = f'<b>{sales[page]["title"]}</b>\n\n' \
           f'{sales[page]["description"]}'

    return {'status': OK, 'data': {'caption': text, 'photo': photo_bytes, 'reply_markup': keyboard}}
