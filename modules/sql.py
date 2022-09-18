import logging
import mysql.connector
from modules.statuses import *


class MysqlCollector:

    def __init__(self, server, username, passwd, db):
        self.server = server
        self.username = username
        self.passwd = passwd
        self.db = db

        my, cursor = self.connect()
        my.close()

    def connect(self):
        my = mysql.connector.connect(user=self.username, password=self.passwd, host=self.server,
                                     database=self.db)
        cursor = my.cursor()

        return my, cursor

    def select(self, table, cols='*', where=None):
        my, cursor = self.connect()

        sql = f'SELECT {", ".join(cols)} FROM `{table}`'
        add = ';' if where is None else f' WHERE {where};'
        sql = sql + add
        try:
            cursor.execute(sql)
        except Exception as err:
            logging.error(f'SQL select error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            raw = cursor.fetchall()
            if len(raw) > 1:
                result = []
                for row in raw:
                    result.append(dict(zip(cursor.column_names, row)))
            elif len(raw) == 1:
                result = dict(zip(cursor.column_names, raw[0]))
            else:
                result = []
            return {'status': OK, 'data': result}
        finally:
            my.close()

    def insert(self, table, data):
        my, cursor = self.connect()

        cols = [f'{x}' for x in data.keys()]
        vals = [f'\'{x}\'' for x in data.values()]
        sql = f'INSERT INTO `{table}` ({", ".join(cols)}) VALUES ({", ".join(vals)});'
        try:
            cursor.execute(sql)
            my.commit()
        except Exception as err:
            logging.error(f'SQL insert error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            return {'status': OK, 'data': None}
        finally:
            my.close()

    def update(self, table, values, where=None):
        my, cursor = self.connect()

        f_values = [f'{k}=\'{v}\'' for k, v in values.items()]
        sql = f'UPDATE `{table}` SET {", ".join(f_values)}'
        add = ';' if where is None else f' WHERE {where};'
        sql = sql + add
        try:
            cursor.execute(sql)
            my.commit()
        except Exception as err:
            logging.error(f'SQL update error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            return {'status': OK, 'data': None}
        finally:
            my.close()

    def delete(self, table, where=None):
        my, cursor = self.connect()

        sql = f'DELETE FROM {table}'
        add = ';' if where is None else f' WHERE {where};'
        sql += add

        try:
            cursor.execute(sql)
            my.commit()
        except Exception as err:
            logging.error(f'SQL delete error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            return {'status': OK, 'data': None}
        finally:
            my.close()
