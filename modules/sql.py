import logging
import mysql.connector
from modules.statuses import *


class MysqlCollector:

    def __init__(self, server, username, passwd, db):
        self.server = server
        self.username = username
        self.passwd = passwd
        self.db = db

        self.my = None
        self.cursor = None

        self.connect()
        self.close()

    def connect(self):
        self.my = mysql.connector.connect(user=self.username, password=self.passwd, host=self.server,
                                          database=self.db)
        self.cursor = self.my.cursor()

    def select(self, table, cols='*', where=None):
        self.connect()

        sql = f'SELECT {", ".join(cols)} FROM `{table}`'
        add = ';' if where is None else f' WHERE {where};'
        sql = sql + add
        try:
            self.cursor.execute(sql)
        except Exception as err:
            logging.error(f'SQL select error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            raw = self.cursor.fetchall()
            if len(raw) > 1:
                result = []
                for row in raw:
                    result.append(dict(zip(self.cursor.column_names, row)))
            elif len(raw) == 1:
                result = dict(zip(self.cursor.column_names, raw[0]))
            else:
                result = []
            return {'status': OK, 'data': result}
        finally:
            self.close()

    def insert(self, table, data):
        self.connect()

        cols = [f'{x}' for x in data.keys()]
        vals = [f'\'{x}\'' for x in data.values()]
        sql = f'INSERT INTO `{table}` ({", ".join(cols)}) VALUES ({", ".join(vals)});'
        try:
            self.cursor.execute(sql)
            self.my.commit()
        except Exception as err:
            logging.error(f'SQL insert error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            return {'status': OK, 'data': None}
        finally:
            self.close()

    def update(self, table, values, where=None):
        self.connect()

        f_values = [f'{k}=\'{v}\'' for k, v in values.items()]
        sql = f'UPDATE `{table}` SET {", ".join(f_values)}'
        add = ';' if where is None else f' WHERE {where};'
        sql = sql + add
        try:
            self.cursor.execute(sql)
            self.my.commit()
        except Exception as err:
            logging.error(f'SQL update error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            return {'status': OK, 'data': None}
        finally:
            self.close()

    def delete(self, table, where=None):
        self.connect()

        sql = f'DELETE FROM {table}'
        add = ';' if where is None else f' WHERE {where};'
        sql += add
        print(sql)

        try:
            self.cursor.execute(sql)
            self.my.commit()
        except Exception as err:
            logging.error(f'SQL delete error - {err}')
            return {'status': UNKNOWN_ERROR, 'data': str(err)}
        else:
            return {'status': OK, 'data': None}
        finally:
            self.close()

    def close(self):
        self.my.close()
