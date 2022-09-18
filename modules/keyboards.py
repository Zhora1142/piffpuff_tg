from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from configparser import ConfigParser

config = ConfigParser()
config.read('config.ini')

main_menu = InlineKeyboardMarkup()
main_menu.add(InlineKeyboardButton(text='💳 Бонусная система', callback_data='bonus'))
main_menu.add(InlineKeyboardButton(text='🔎 Поиск', callback_data='search'),
              InlineKeyboardButton(text='📦 Ассортимент', callback_data='select_group'))
main_menu.add(InlineKeyboardButton(text='❗ Акции', callback_data='sales'))
main_menu.add(InlineKeyboardButton(text='🧺 Корзина', callback_data='show_basket'))
main_menu.add(InlineKeyboardButton(text='👤 Менеджер', callback_data='manager'))

hello = InlineKeyboardMarkup()
hello.add(InlineKeyboardButton(text='Понятно', callback_data='menu'))

back = InlineKeyboardMarkup()
back.add(InlineKeyboardButton(text='Назад', callback_data='menu'))

manager = InlineKeyboardMarkup()
manager.add(InlineKeyboardButton(text='Менеджер', url=config['tg']['manager_link']))
manager.add(InlineKeyboardButton(text='Назад', callback_data='menu'))

register = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, input_field_placeholder='Номер телефона')
register.add(KeyboardButton(text='Отправить номер Telegram', request_contact=True))
register.add(KeyboardButton(text='Отмена'))

again = InlineKeyboardMarkup()
again.add(InlineKeyboardButton(text='Повторить звонок', callback_data='send_new_call'))
again.add(InlineKeyboardButton(text='Отмена', callback_data='cancel_call'))
