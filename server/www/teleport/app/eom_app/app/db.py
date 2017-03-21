# -*- coding: utf-8 -*-

import builtins
import os
import sqlite3
import threading

from eom_common.eomcore.logger import log
from .configs import app_cfg
from .database.create import create_and_init
from .database.upgrade import DatabaseUpgrade

cfg = app_cfg()

__all__ = ['get_db', 'DbItem']


# 注意，每次调整数据库结构，必须增加版本号，并且在升级接口中编写对应的升级操作


class TPDatabase:
    DB_VERSION = 5

    DB_TYPE_UNKNOWN = 0
    DB_TYPE_SQLITE = 1
    DB_TYPE_MYSQL = 2

    def __init__(self):
        if '__teleport_db__' in builtins.__dict__:
            raise RuntimeError('TPDatabase object exists, you can not create more than one instance.')

        self.db_source = {'type': self.DB_TYPE_UNKNOWN}
        self.need_create = False  # 数据尚未存在，需要创建
        self.need_upgrade = False  # 数据库已存在但版本较低，需要升级
        self.current_ver = 0

        self._table_prefix = ''
        self._conn_pool = None

    @property
    def table_prefix(self):
        return self._table_prefix

    def init(self, db_source):
        self.db_source = db_source

        if db_source['type'] == self.DB_TYPE_MYSQL:
            log.e('MySQL not supported yet.')
            return False
        elif db_source['type'] == self.DB_TYPE_SQLITE:
            self._table_prefix = 'ts_'
            self._conn_pool = TPSqlitePool(db_source['file'])

            if not os.path.exists(db_source['file']):
                log.w('database need create.\n')
                self.need_create = True
                return True
        else:
            log.e('Unknown database type: {}'.format(db_source['type']))
            return False

        # 看看数据库中是否存在指定的数据表（如果不存在，可能是一个空数据库文件），则可能是一个新安装的系统
        # ret = self.query('SELECT COUNT(*) FROM `sqlite_master` WHERE `type`="table" AND `name`="{}account";'.format(self._table_prefix))
        ret = self.is_table_exists('group')
        if ret is None or not ret:
            # if ret is None or ret[0][0] == 0:
            log.w('database need create.\n')
            self.need_create = True
            return True

        # 尝试从配置表中读取当前数据库版本号（如果不存在，说明是比较旧的版本了）
        ret = self.query('SELECT `value` FROM `{}config` WHERE `name`="db_ver";'.format(self._table_prefix))
        log.w(ret)
        if ret is None or 0 == len(ret):
            self.current_ver = 1
        else:
            self.current_ver = int(ret[0][0])

        if self.current_ver < self.DB_VERSION:
            log.w('database need upgrade.\n')
            self.need_upgrade = True
            return True

        return True

    # def init_sqlite(self, db_file):
    #     self._table_prefix = 'ts_'
    #     self._conn_pool = TPSqlitePool(db_file)
    #
    #     if not os.path.exists(db_file):
    #         log.w('database need create.\n')
    #         self.need_create = True
    #         return
    #
    #     # 看看数据库中是否存在指定的数据表（如果不存在，可能是一个空数据库文件），则可能是一个新安装的系统
    #     # ret = self.query('SELECT COUNT(*) FROM `sqlite_master` WHERE `type`="table" AND `name`="{}account";'.format(self._table_prefix))
    #     ret = self.is_table_exists('group')
    #     if ret is None or not ret:
    #         # if ret is None or ret[0][0] == 0:
    #         log.w('database need create.\n')
    #         self.need_create = True
    #         return
    #
    #     # 尝试从配置表中读取当前数据库版本号（如果不存在，说明是比较旧的版本了）
    #     ret = self.query('SELECT `value` FROM {}config WHERE `name`="db_ver";'.format(self._table_prefix))
    #     if ret is None or 0 == len(ret) or ret[0][0] < TELEPORT_DATABASE_VERSION:
    #         log.w('database need upgrade.\n')
    #         self.need_upgrade = True

    def is_table_exists(self, table_name):
        """
        判断指定的表是否存在
        @param table_name: string
        @return: None or Boolean
        """
        # return self._conn_pool.is_table_exists(table_name)
        if self.db_source['type'] == self.DB_TYPE_SQLITE:
            ret = self.query('SELECT COUNT(*) FROM `sqlite_master` WHERE `type`="table" AND `name`="{}{}";'.format(self._table_prefix, table_name))
            if ret is None:
                return None
            if len(ret) == 0:
                return False
            if ret[0][0] == 0:
                return False
            return True
        elif self.db_source['type'] == self.DB_TYPE_MYSQL:
            return None
        else:
            return None

    def query(self, sql):
        return self._conn_pool.query(sql)

    def exec(self, sql):
        return self._conn_pool.exec(sql)

    def create_and_init(self, step_begin, step_end):
        if create_and_init(self, step_begin, step_end):
            self.need_create = False
            return True
        else:
            return False

    def upgrade_database(self, step_begin, step_end):
        if DatabaseUpgrade(self, step_begin, step_end).do_upgrade():
            # if upgrade_database(self, step_begin, step_end):
            self.need_upgrade = False
            return True
        else:
            return False


class TPDatabasePool:
    def __init__(self):
        self._locker = threading.RLock()
        self._connections = dict()

    # def is_table_exists(self, table_name):
    #     _conn = self._get_connect()
    #     if _conn is None:
    #         return None
    #     return self._is_table_exists(_conn, table_name)

    def query(self, sql):
        _conn = self._get_connect()
        if _conn is None:
            return None
        return self._do_query(_conn, sql)

    def exec(self, sql):
        _conn = self._get_connect()
        if _conn is None:
            return False
        return self._do_exec(_conn, sql)

    def _get_connect(self):
        with self._locker:
            thread_id = threading.get_ident()
            if thread_id not in self._connections:
                _conn = self._do_connect()
                self._connections[thread_id] = _conn
            else:
                _conn = self._connections[thread_id]

        return _conn

    def _do_connect(self):
        return None

    # def _is_table_exists(self, conn, table_name):
    #     return None

    def _do_query(self, conn, sql):
        return None

    def _do_exec(self, conn, sql):
        return None


class TPSqlitePool(TPDatabasePool):
    def __init__(self, db_file):
        super().__init__()
        self._db_file = db_file

    def _do_connect(self):
        try:
            return sqlite3.connect(self._db_file)
        except:
            log.e('[sqlite] can not connect, does the database file correct?')
            return None

    # def _is_table_exists(self, conn, table_name):
    #     ret = self._do_query(conn, 'SELECT COUNT(*) FROM `sqlite_master` WHERE `type`="table" AND `name`="{}{}";'.format(self._table_prefix, table_name))
    #     # ret = self.query('SELECT COUNT(*) FROM `sqlite_master` WHERE `type`="table" AND `name`="{}{}";'.format(self._table_prefix, table_name))
    #     if ret is None or ret[0][0] == 0:
    #         return False
    #     else:
    #         return True

    def _do_query(self, conn, sql):
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            db_ret = cursor.fetchall()
            return db_ret
        except sqlite3.OperationalError:
            return None
        finally:
            cursor.close()

    def _do_exec(self, conn, sql):
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            conn.commit()
            return True
        except sqlite3.OperationalError:
            return False
        finally:
            cursor.close()


class DbItem(dict):
    def load(self, db_item, db_fields):
        if len(db_fields) != len(db_item):
            raise RuntimeError('!=')
        for i in range(len(db_item)):
            self[db_fields[i]] = db_item[i]

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise


def get_db():
    """
    :rtype : TPDatabase
    """
    if '__teleport_db__' not in builtins.__dict__:
        builtins.__dict__['__teleport_db__'] = TPDatabase()
    return builtins.__dict__['__teleport_db__']
