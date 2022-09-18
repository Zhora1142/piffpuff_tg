import telebot
from telebot.types import InputMediaPhoto
from modules.message_generator import *
from modules.keyboards import *
from modules.flashcall import FlashCall
from json import loads
from re import fullmatch
from random import randint
from datetime import datetime
config = ConfigParser()
config.read('config.ini')

telebot.apihelper.ENABLE_MIDDLEWARE = True

bot = telebot.TeleBot(token=config['tg']['token'], parse_mode='HTML')
s = Storage()
sql = MysqlCollector(**config['sql'])
f = FlashCall()

ERROR_TEXT = 'Неизвестная ошибка. Попробуйте ещё раз, или свяжитесь с менеджером.'


@bot.middleware_handler(update_types=['message', 'callback_query'])
def middleware(bot_instance, upd):
    if upd.message:
        chat_id = upd.message.chat.id
    else:
        chat_id = upd.callback_query.message.chat.id

    r = sql.select(table='users', where=f'id={chat_id}')

    if not r['data']:
        d = {'id': chat_id,
             'basket': '{}',
             'status': 'menu',
             'search_request': '{}',
             'search_path': ''}
        sql.insert(table='users', data=d)


@bot.message_handler(content_types=['contact', 'text'], func=lambda msg: sql.select(table='users', where=f'id={msg.chat.id}')['data']['status'] == 'bonus')
def bonus(msg):
    chat_id = msg.chat.id
    if msg.content_type == 'text':
        if msg.text.lower() == 'отмена':
            sql.update(table='users', values={'status': 'menu'}, where=f'id={chat_id}')
            m = bot.send_message(chat_id=chat_id, text='Привязка аккаунта отменена', reply_markup=ReplyKeyboardRemove())
            bot.delete_message(message_id=m.id, chat_id=chat_id)
            text = '<b>Главное меню</b>\n\n' \
                   'Выбери одну из кнопок на клавиатуре'
            bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu)
            return
        else:
            number = msg.text
            if not fullmatch(r'(\+7|8)\d{10}', number):
                text = 'Введите номер в формате <b>+7XXXXXXXXXX</b>'
                bot.send_message(chat_id=chat_id, text=text)
                return
    else:
        number = msg.contact.phone_number

    code = str(randint(1111, 9999))
    r = f.send(phone=number, code=code)

    m = bot.send_message(chat_id=chat_id, text='.', reply_markup=ReplyKeyboardRemove())
    bot.delete_message(chat_id=chat_id, message_id=m.id)

    if r['status'] != OK:
        sql.update(table='users', values={'status': 'menu'}, where=f'id={chat_id}')
        text = 'Произошла ошибка. Пожалуйста, повторите попытку немного позже.'
        bot.send_message(chat_id=chat_id, text=text, reply_markup=back)
        return

    sql.update(table='users', values={'status': 'call'}, where=f'id={chat_id}')
    text = '<b>Необходимо подтвердить номер телефона.</b>\n\n' \
           'Напишите в чат четыре последние цифры номера, с которого Вам позвонят.'
    m = bot.send_message(chat_id=chat_id, text=text, reply_markup=again)
    data = {
        'id': chat_id,
        'code': code,
        'phone': number,
        'moment': int(datetime.now().timestamp()),
        'msg_id': m.id,
        'call_id': r['data']
    }

    sql.insert(table='codes', data=data)


@bot.callback_query_handler(func=lambda call: sql.select(table='users', where=f'id={call.message.chat.id}')['data']['status'] == 'call')
def call_repeater(call):
    chat_id = call.message.chat.id
    message_id = call.message.id
    if call.data == 'cancel_call':
        bot.answer_callback_query(callback_query_id=call.id)
        sql.update(table='users', values={'status': 'menu'}, where=f'id={chat_id}')
        sql.delete(table='codes', where=f'id={chat_id}')
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text='Подтверждение отменено')
        text = '<b>Главное меню</b>\n\n' \
               'Выбери одну из кнопок на клавиатуре'
        bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu)
    elif call.data == 'send_new_call':
        data = sql.select(table='codes', where=f'id={chat_id}')['data']
        now = int(datetime.now().timestamp())
        moment = data['moment']

        if now - moment <= 65:
            text = f'Подождите {65 - (now - moment)} секунд'
            bot.answer_callback_query(callback_query_id=call.id, text=text, show_alert=True)
            return
        else:
            status = f.check(call_id=data['call_id'])
            if status['data'] in (0, 4):
                text = f'Ваш звонок в очереди. Пожалуйста, подождите немного.'
                bot.answer_callback_query(callback_query_id=call.id, text=text, show_alert=True)
                return

        code = str(randint(1111, 9999))
        r = f.send(phone=data['phone'], code=code)

        if r['status'] != OK:
            text = 'Произошла ошибка. Пожалуйста, попробуйте ещё раз позже.'
            bot.answer_callback_query(callback_query_id=call.id, text=text, show_alert=True)
            return

        sql.update(table='codes', values={'code': code, 'moment': datetime.now().timestamp()}, where=f'id={chat_id}')

        text = 'Код отправлен повторно'
        bot.answer_callback_query(callback_query_id=call.id, text=text, show_alert=True)


@bot.message_handler(content_types=['text'], func=lambda msg: sql.select(table='users', where=f'id={msg.chat.id}')['data']['status'] == 'call')
def code_handler(msg):
    chat_id = msg.chat.id
    data = sql.select(table='codes', where=f'id={chat_id}')['data']

    if msg.text == data['code']:
        sql.update(table='users', values={'status': 'menu'}, where=f'id={chat_id}')
        sql.insert(table='bonus', data={'phone': data['phone'], 'id': chat_id})
        sql.delete(table='codes', where=f'id={chat_id}')

        balance = s.get_balance(phone=data['phone'])
        if balance['status'] != OK:
            if s.create_user(phone=data['phone'])['status'] != OK:
                sql.delete(table='bonus', where=f'id={chat_id}')
                bot.edit_message_text(chat_id=chat_id, message_id=data['msg_id'], text='Произошла ошибка')
                text = 'Произошла ошибка, не удалось зарегистрировать аккаунт в бонусной системе. Пожалуйста, ' \
                       'попробуйте ненмого позже.'
                bot.send_message(chat_id=chat_id, text=text, reply_markup=back)
                return
            balance = s.get_balance(phone=data['phone'])
        bot.edit_message_text(chat_id=chat_id, message_id=data['msg_id'], text='Номер подтверждён')

        text = f'<b>Бонусная система</b>\n\n' \
               f'<b>Номер</b>: {data["phone"]}\n' \
               f'<b>Бонусы</b>: {balance["data"]}'
        bot.send_message(chat_id=chat_id, text=text, reply_markup=back)
    else:
        bot.send_message(chat_id=chat_id, text='Неверный код.')


@bot.message_handler(commands=['start'], func=lambda msg: sql.select(table='users', where=f'id={msg.chat.id}')['data']['status'] == 'menu')
def start(msg):
    text = 'Привет\n\n' \
           'Перед тобой бот магазина PiffPuff, с помощью которого ты сможешь ознакомиться со списком доступных ' \
           'товаров, связаться с менеджером и сделать заказ, а также зарегистрироваться в бонусной системе'

    bot.send_message(chat_id=msg.chat.id, text=text, reply_markup=hello)


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    message_id = call.message.id

    if call.data == 'menu':
        bot.answer_callback_query(callback_query_id=call.id)
        text = '<b>Главное меню</b>\n\n' \
               'Выбери одну из кнопок на клавиатуре'

        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'photo':
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=main_menu)

    elif call.data == 'menu_search':
        sql.update(table='users', values={'search_request': '{}', 'search_path': ''})
        bot.answer_callback_query(callback_query_id=call.id)
        text = '<b>Главное меню</b>\n\n' \
               'Выбери одну из кнопок на клавиатуре'

        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'photo':
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=main_menu)

    elif 'select_group' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            request_data['parent_id'] = None
            request_data['last_element_id'] = None
            request_data['first_element_id'] = None
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'p':
                    request_data['parent_id'] = st[1]
                elif st[0] == 'f':
                    request_data['first_element_id'] = st[1]
                elif st[0] == 'l':
                    request_data['last_element_id'] = st[1]

        data = generate_folders(**request_data)
        if data['status'] != OK:
            if data['status'] == UNKNOWN_ERROR:
                bot.answer_callback_query(callback_query_id=call.id, text=ERROR_TEXT)
            else:
                bot.edit_message_text(text='Главное меню', chat_id=chat_id, message_id=message_id,
                                      reply_markup=main_menu)
            return

        bot.answer_callback_query(callback_query_id=call.id)
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, **data['data'])

    elif 'show_products' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            request_data['parent_id'] = None
            request_data['offset'] = 0
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'p':
                    request_data['parent_id'] = st[1]
                elif st[0] == 'o':
                    request_data['offset'] = int(st[1])

        data = generate_products(**request_data)

        if data['status'] != OK:
            if data['status'] == UNKNOWN_ERROR:
                bot.answer_callback_query(callback_query_id=call.id, text=ERROR_TEXT)
            else:
                bot.edit_message_text(text='Главное меню', chat_id=chat_id, message_id=message_id,
                                      reply_markup=main_menu)
            return

        bot.answer_callback_query(callback_query_id=call.id)

        if call.message.content_type == 'photo':
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_message(chat_id=chat_id, **data['data'])
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, **data['data'])

    elif 'select_product' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            request_data['product_id'] = None
            request_data['from_basket'] = 0
            request_data['offset'] = 0
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'p':
                    request_data['product_id'] = st[1]
                elif st[0] == 'f':
                    request_data['from_basket'] = int(st[1])
                elif st[0] == 'o':
                    request_data['offset'] = int(st[1])
                elif st[0] == 's':
                    request_data['from_search'] = int(st[1])

        data = generate_product(**request_data, user_id=chat_id)

        if data['status'] != OK:
            if data['status'] == UNKNOWN_ERROR:
                bot.answer_callback_query(callback_query_id=call.id, text=ERROR_TEXT)
            else:
                bot.edit_message_text(text='Главное меню', chat_id=chat_id, message_id=message_id,
                                      reply_markup=main_menu)
            return

        if 'photo' in data['data']:
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_photo(**data['data'], chat_id=chat_id)
        else:
            bot.edit_message_text(**data['data'], chat_id=chat_id, message_id=message_id)

    elif 'add' in call.data:
        stock = 0
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            request_data['product_id'] = None
            request_data['from_basket'] = 0
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'i':
                    request_data['product_id'] = st[1]
                elif st[0] == 's':
                    stock = int(st[1])
                elif st[0] == 'b':
                    request_data['from_basket'] = int(st[1])

        user_basket = sql.select(table='users', where=f'id={chat_id}')
        user_basket = loads(user_basket['data']['basket'])

        product_id = request_data['product_id']

        if product_id in user_basket:
            if user_basket[product_id] + 1 > stock:
                user_basket[product_id] = stock
            else:
                user_basket[product_id] += 1
        else:
            if stock < 1:
                text = 'Товара больше нет в наличии.'
                bot.answer_callback_query(callback_query_id=call.id, text=text, show_alert=True)
                return
            else:
                user_basket[product_id] = 1

        sql.update(table='users', values={'basket': dumps(user_basket)}, where=f'id={chat_id}')

        data = generate_product(**request_data, user_id=chat_id)
        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'photo':
            if 'caption' in data['data']:
                data['data'].pop('photo')
                bot.edit_message_caption(**data['data'], chat_id=chat_id, message_id=message_id)
            else:
                data['data']['caption'] = data['data']['text']
                data['data'].pop('text')
                bot.edit_message_caption(**data['data'], chat_id=chat_id, message_id=message_id)
        else:
            if 'caption' in data['data']:
                data['data']['text'] = data['data']['caption']
                data['data'].pop('caption')
                bot.edit_message_text(**data['data'], chat_id=chat_id, message_id=message_id)
            else:
                bot.edit_message_text(**data['data'], chat_id=chat_id, message_id=message_id)

    elif 'rem' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            request_data['product_id'] = None
            request_data['from_basket'] = 0
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'i':
                    request_data['product_id'] = st[1]
                elif st[0] == 'b':
                    request_data['from_basket'] = int(st[1])

        user_basket = sql.select(table='users', where=f'id={chat_id}')
        user_basket = loads(user_basket['data']['basket'])

        product_id = request_data['product_id']

        if product_id in user_basket:
            user_basket[product_id] -= 1
            if user_basket[product_id] <= 0:
                user_basket.pop(product_id)

        sql.update(table='users', values={'basket': dumps(user_basket)}, where=f'id={chat_id}')

        data = generate_product(**request_data, user_id=chat_id)

        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'photo':
            if 'caption' in data['data']:
                data['data'].pop('photo')
                bot.edit_message_caption(**data['data'], chat_id=chat_id, message_id=message_id)
            else:
                data['data']['caption'] = data['data']['text']
                data['data'].pop('text')
                bot.edit_message_caption(**data['data'], chat_id=chat_id, message_id=message_id)
        else:
            if 'caption' in data['data']:
                data['data']['text'] = data['data']['caption']
                data['data'].pop('caption')
                bot.edit_message_text(**data['data'], chat_id=chat_id, message_id=message_id)
            else:
                bot.edit_message_text(**data['data'], chat_id=chat_id, message_id=message_id)

    elif 'show_basket' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            request_data['selected'] = 0
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 's':
                    request_data['selected'] = int(st[1])

        data = generate_basket(**request_data, user_id=chat_id)

        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'photo':
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_message(chat_id=chat_id, **data['data'])
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, **data['data'])

    elif 'del' in call.data:
        request = call.data.split('?')
        request_data = {}
        product_id = None
        if len(request) == 1:
            request_data['selected'] = 0
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 's':
                    request_data['selected'] = int(st[1])
                if st[0] == 'i':
                    product_id = st[1]

        user_basket = sql.select(table='users', where=f'id={chat_id}')
        user_basket = loads(user_basket['data']['basket'])

        if product_id in user_basket:
            user_basket.pop(product_id)

        sql.update(table='users', values={'basket': dumps(user_basket)}, where=f'id={chat_id}')

        data = generate_basket(user_id=chat_id, **request_data)

        bot.answer_callback_query(callback_query_id=call.id, text='Товар удалён из корзины')
        bot.edit_message_text(**data['data'], chat_id=chat_id, message_id=message_id)

    elif 'clear_basket' in call.data:
        sql.update(table='users', values={'basket': '{}'}, where=f'id={chat_id}')

        data = generate_basket(user_id=chat_id)

        bot.answer_callback_query(callback_query_id=call.id, text='Корзина очищена')
        bot.edit_message_text(message_id=message_id, chat_id=chat_id, **data['data'])

    elif call.data == 'search':
        sql.update(table='users', values={'status': 'search'}, where=f'id={chat_id}')

        bot.answer_callback_query(callback_query_id=call.id)
        bot.edit_message_text(text='Отправьте поисковой запрос', chat_id=chat_id, message_id=message_id)

    elif 'ss' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            pass
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'r':
                    request_data['request'] = st[1]
                if st[0] == 'o':
                    request_data['offset'] = int(st[1])

        data = search(user_id=chat_id, **request_data)
        if data['status'] != OK:
            bot.answer_callback_query(callback_query_id=call.id, text=ERROR_TEXT)
            return

        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'photo':
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_message(chat_id=chat_id, **data['data'])
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, **data['data'])

    elif 'sales' in call.data:
        request = call.data.split('?')
        request_data = {}
        if len(request) == 1:
            pass
        else:
            for string in request[-1].split(','):
                st = string.split('=')
                if st[0] == 'p':
                    request_data['page'] = int(st[1])

        data = generate_sales(**request_data)

        bot.answer_callback_query(callback_query_id=call.id)
        if call.message.content_type == 'text':
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_photo(chat_id=chat_id, **data['data'])
        else:
            data['data']['media'] = InputMediaPhoto(media=data['data']['photo'], caption=data['data']['caption'],
                                                    parse_mode='HTML')
            data['data'].pop('photo')
            data['data'].pop('caption')
            bot.edit_message_media(**data['data'], chat_id=chat_id, message_id=message_id)

    elif call.data == 'manager':
        user_basket = generate_basket_empty(chat_id)
        if not user_basket:
            text = 'Нажмите кнопку снизу, чтобы связаться с менеджером.'
        else:
            text = f'Нажмите кнопку снизу, чтобы связаться с менеджером\n\n' \
                   f'<b>И перешлите ему это сообщение</b>\n\n' \
                   f'{user_basket}'

        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=manager)

    elif call.data == 'bonus':
        data = sql.select(table='bonus', where=f'id={chat_id}')['data']
        bot.answer_callback_query(callback_query_id=call.id)
        if not data:
            sql.update(table='users', values={'status': 'bonus'}, where=f'id={chat_id}')
            text = 'Чтобы начать пользоваться бонусной системы, необходимо привязать свой аккаунт.\n\n' \
                   'Отправьте в чат свой номер телефона, или воспользуйтесь кнопкой, чтобы отправить номер, который' \
                   'привязан к Telegram'
            bot.delete_message(chat_id=chat_id, message_id=message_id)
            bot.send_message(chat_id=chat_id, text=text, reply_markup=register)
        else:
            balance = s.get_balance(phone=data['phone'])
            text = f'<b>Бонусная система</b>\n\n' \
                   f'<b>Номер</b>: {data["phone"]}\n' \
                   f'<b>Бонусы</b>: {balance["data"]}'
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=back)

    elif call.data == 'null':
        bot.answer_callback_query(callback_query_id=call.id)


@bot.message_handler()
def handler(msg):
    chat_id = msg.chat.id
    message_id = msg.id

    status = sql.select(table='users', where=f'id={chat_id}')
    status = status['data']['status']

    if status == 'menu':
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    elif status == 'search':
        data = s.search(request=msg.text)

        if data['status'] != OK:
            if data['status'] == NOT_FOUND:
                text = 'По Вашему запросу ничего не найдено.'
            else:
                text = 'Произошла ошибка. Подождите немного и попытайтесь ещё раз.'
            sql.update(table='users', values={'status': 'menu'}, where=f'id={chat_id}')
            bot.send_message(text=text, reply_markup=back, chat_id=chat_id)
            return

        tree = data['data']['tree']
        sql.update(table='users', values={'search_request': dumps(tree, ensure_ascii=False), 'search_path': '',
                                          'status': 'menu'},
                   where=f'id={chat_id}')

        data = search(user_id=chat_id)
        if data['status'] != OK:
            text = 'Произошла ошибка. Подождите немного и попытайтесь ещё раз.'
            bot.edit_message_text(text=text, reply_markup=back, message_id=message_id, chat_id=chat_id)
            return

        bot.send_message(chat_id=chat_id, **data['data'])


if __name__ == '__main__':
    print('Bot started')
    bot.infinity_polling()
