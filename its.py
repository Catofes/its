#!/bin/python2
# -*- coding: UTF-8 -*-

import re
import urllib2
import urllib
import time
import math
import threading
import falcon
import json
import subprocess
import psycopg2
from wsgiref import simple_server
import config
import database


class ITS:
    class AccountManager:

        class AccountInfo:
            def __init__(self, name, password, type=0):
                self.name = name
                self.password = password
                self.last_connect_time = 0
                self.connect_limit_reach = False
                self.disconnect_count = 0
                self.type = type  # 0 for unlimited account. Should connect first. 1 for normal account. 2 for disable
                self.connect_count = 0

        def __init__(self):
            self.date = time.strftime('%Y-%m-%d', time.localtime(time.time() - 3600))
            self.accounts = []
            for account in config.accounts:
                self.accounts.append(self.AccountInfo(account[0], account[1], account[2]))

        def get_account(self):
            date = time.strftime('%Y-%m-%d', time.localtime(time.time() - 3600))
            if date != self.date:
                for account in self.accounts:
                    account.connect_limit_reach = False
                self.date = date
            # search for type 0
            for account in self.accounts:
                if account.type == 0:
                    if account.connect_limit_reach:
                        continue
                    return account
            # search for type 1
            for account in self.accounts:
                if account.type == 1:
                    if account.connect_limit_reach:
                        continue
                    return account
            return self.accounts[0]

    def __init__(self):
        self.last_request_time = 0
        self.last_check_time = 0
        self.last_check_result = True
        self.last_request_response = ''
        self.last_request_result = True
        self.lost_count = 0
        self.lost_limit = 1
        self.check_url = config.check_url
        self.account_manager = self.AccountManager()
        self.lock = threading.Lock()

    def c_lock(func):
        def acquire_lock(self, account=None):
            if self.lock.acquire(1):
                result = func(self, account)
                self.lock.release()
                return result
            else:
                return False

        return acquire_lock

    @c_lock
    def connect(self, account):
        self.last_request_time = time.time()
        if not account:
            account = self.account_manager.get_account()
        account.last_connect_time = time.time()
        try:
            resp = urllib2.urlopen(
                "https://its.pku.edu.cn:5428/ipgatewayofpku",
                urllib.urlencode(
                    {
                        "uid": account.name,
                        "password": account.password,
                        "range": '1',
                        "operation": 'connect',
                        "timeout": "1"
                    }
                ), timeout=5
            )
        except Exception as e:
            self.last_request_result = False
            print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 account.name + "   Connect Request Sent Error." + e.message)
            return False
        self.last_request_response = resp.read().decode('GB2312')
        if re.search(ur'今天不能再使用客户端', self.last_request_response, re.UNICODE):
            account.connect_limit_reach = True
            print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 account.name + "   Reach Daily API Limit.")
            self.last_check_result = False
            return False
        if re.search(ur'当前连接数超过预定值', self.last_request_response, re.UNICODE):
            self.disconnect(account)
            self.last_check_result = False
            return False
        self.last_check_result = True
        print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                             account.name + "   Connect Request Sent Without Error.")
        return True

    def disconnect(self, account):
        try:
            resp = urllib2.urlopen(
                "https://its.pku.edu.cn:5428/ipgatewayofpku",
                urllib.urlencode(
                    {
                        "uid": account.name,
                        "password": account.password,
                        "range": '4',
                        "operation": 'disconnectall',
                        "timeout": "1"
                    }
                ), timeout=5
            )
        except Exception as e:
            print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 account.name + "   Disconnectall Request Sent Error." + e.message)
            return False
        print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                             account.name + "   Disconnectall Request Sent Without Error.")
        return True

    def check(self):
        self.last_check_time = time.time()
        last_check_result = False
        for url in self.check_url:
            try:
                resp = urllib2.urlopen(
                    url,
                    timeout=5
                )
            except Exception as e:
                continue
            last_check_result = True
            break
        self.last_check_result = last_check_result
        if not self.last_check_result:
            print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 "Detect Connection Lost. Try to reconnect.")
            return False
        return True

    def check_fail(self):
        self.lost_count += 1
        if self.lost_count >= self.lost_limit:
            self.lost_count = 0
            if self.lost_limit >= 64:
                self.lost_limit = math.floor(256 * math.sqrt(self.lost_count / 256.0))
            else:
                self.lost_limit *= 2
            if self.lost_limit < 1:
                self.lost_limit = 1
            if self.lost_count >= 256:
                self.lost_limit = 256
            self.connect()
            return True
        return False

    def check_success(self):
        self.lost_count = 0
        self.lost_limit = (self.lost_limit / 2 + 1)
        return True

    def loop(self):
        while True:
            if self.check():
                self.check_success()
            else:
                self.check_fail()
            time.sleep(5)


class MyThread(threading.Thread):
    def __init__(self, its):
        threading.Thread.__init__(self)
        self.its = its

    def run(self):
        its.loop()


class Destination:
    def __init__(self, id, name, route_table, route_rule, allow_ips, disallow_ips=None):
        self.db = database.RDateBasePool()
        self.id = id
        self.name = name
        self.route_table = route_table
        self.route_rule = route_rule
        self.allow_ips = allow_ips
        self.disallow_ips = disallow_ips

    def create(self):
        if not self.route_table:
            return False
        p = subprocess.Popen(['ip', 'route', 'flush', 'table', self.route_table])
        p.wait()
        for line in self.route_rule:
            line.append('table')
            line.append(self.route_table)
            p = subprocess.Popen(line)
            p.wait()

    def test_ip(self, ip, name=""):
        if self.disallow_ips:
            for disallow_ip in self.disallow_ips:
                if re.match(disallow_ip, ip):
                    return False
        for allow_ip in self.allow_ips:
            if re.match(allow_ip, ip):
                return True
        if name:
            if self.db.execute(
                    "SELECT DISTINCT outer_id FROM groupouter JOIN usergroup USING (groupname) "
                    "WHERE username = %s AND groupouter.outer_id = %s ORDER BY outer_id;", (name, self.id)):
                return True
        return False


destinations = {}


class ChangeNet:
    @staticmethod
    def update(ip, destination_id, name):
        global destinations
        if not ip:
            return False
        if ip == "10.20.0.1":
            return False
        destination_id = int(destination_id)
        if destination_id not in destinations:
            return False
        destination = destinations[destination_id]
        if not destination.test_ip(ip, name):
            return False
        p = subprocess.Popen(['ip', 'rule', 'del', 'from', ip])
        p.wait()
        p = subprocess.Popen(['ip', 'rule', 'add', 'from', ip, 'lookup', destination.route_table, 'pref', '1000'])
        p.wait()
        print(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(time.time())) +
                             str(name) + " With IP " + str(ip) + " Change to Dest " + str(destination.name))
        return True


class WebService:
    def __init__(self, its):
        self.its = its
        global destinations
        self.db = database.RDateBasePool()
        results = self.db.execute('SELECT * FROM "outer";', ())
        for dest in results:
            destinations[dest['id']] = Destination(
                name=dest['name'],
                id=dest['id'],
                route_table=dest['route_table'],
                route_rule=json.loads(dest['route_rule']),
                allow_ips=json.loads(dest['allow_ips']),
                disallow_ips=json.loads(dest['disallow_ips'])
            )
        for destination in destinations.itervalues():
            destination.create()

    def _get_username(self, ip):
        result = self.db.execute(
            "SELECT username FROM radacct WHERE framedipaddress = %s ORDER BY acctupdatetime DESC LIMIT 1", (ip,))
        if not result:
            return ""
        else:
            return result[0]['username']

    def _get_allow_dest(self, name):
        result = self.db.execute(
            "SELECT DISTINCT outer_id FROM groupouter JOIN usergroup USING (groupname) WHERE username = %s ORDER BY outer_id;",
            (name,))
        if result:
            return result
        else:
            return []

    def _get_info(self, req, resp):
        ip = str(req.get_header("X-Real-IP"))
        p = subprocess.Popen('ip rule | grep ' + ip, shell=True, stdout=subprocess.PIPE)
        destination_table = p.stdout.readline().split(" ")
        if len(destination_table) > 2:
            destination_table = destination_table[len(destination_table) - 2]
        p.wait()

        allow_destination = []
        name = self._get_username(ip)
        dest = []
        if name:
            dest = self._get_allow_dest(name)

        global destinations
        for destination in destinations.itervalues():
            if destination.test_ip(ip) or ([destination.id] in dest):
                allow_destination.append({
                    'id': destination.id,
                    'name': destination.name
                })
        destination = ""
        for d in destinations.itervalues():
            if destination_table == d.route_table:
                destination = d.name
                break
        resp.body = json.dumps({
            'IP': req.get_header("X-Real-IP"),
            'destination': destination,
            'check_status': self.its.last_check_result,
            'check_time': time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self.its.last_check_time)),
            'request_time': time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self.its.last_request_time)),
            'request_response': self.its.last_request_response,
            'next_reconnect_time': time.strftime('%Y-%m-%d  %H:%M:%S',
                                                 time.localtime((self.its.lost_limit - self.its.lost_count) * 5
                                                                + time.time())),
            'allow_destination': allow_destination
        })

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        self._get_info(req, resp)

    def on_post(self, req, resp):
        if self.its.connect():
            resp.status = falcon.HTTP_200
        else:
            resp.status = falcon.HTTP_400
        self._get_info(req, resp)

    def on_put(self, req, resp):
        ip = req.get_header("X-Real-IP")
        name = self._get_username(ip)
        if not ip:
            resp.status = falcon.HTTP_400
            return
        if not req.get_param("dest"):
            resp.status = falcon.HTTP_400
            return
        if not ChangeNet.update(ip, req.get_param("dest"), name):
            resp.status = falcon.HTTP_400
            return
        return

    def on_delete(self, req, resp):
        if 'key' not in req.params.keys():
            resp.status = falcon.HTTP_400
            return
        if req.params['key'] != '301415':
            resp.status = falcon.HTTP_400
            return
        resp.status = falcon.HTTP_200
        resp.body = json.dumps([self.its.lost_count, self.its.lost_limit,
                                list(name.__dict__ for name in self.its.account_manager.accounts)])


class WebAdminService:
    def __init__(self):
        pass

    def on_get(self, req, resp):
        sec = req.get_param("sec")
        if not sec:
            resp.status = falcon.HTTP_403
            return
        if sec != "secretcode":
            resp.status = falcon.HTTP_403
            return
        ip = req.get_param("ip")
        if not ip:
            resp.status = falcon.HTTP_400
            return
        global destinations
        allow_destination = []
        for destination in destinations.itervalues():
            if destination.test_ip(ip):
                allow_destination.append({
                    'id': destination.id,
                    'name': destination.name
                })
        resp.body = json.dumps(allow_destination)

    def on_put(self, req, resp):
        sec = req.get_param("sec")
        if not sec:
            resp.status = falcon.HTTP_403
            return
        if sec != "secretcode":
            resp.status = falcon.HTTP_403
            return
        ip = req.get_param("ip")
        if not ip:
            resp.status = falcon.HTTP_400
            return
        if not req.get_param("dest"):
            resp.status = falcon.HTTP_400
            return
        if not ChangeNet.update(ip, req.get_param("dest")):
            resp.status = falcon.HTTP_400
            return

    def on_delete(self, req, resp):
        sec = req.get_param("sec")
        if not sec:
            resp.status = falcon.HTTP_403
            return
        if sec != "secretcode":
            resp.status = falcon.HTTP_403
            return
        ip = req.get_param("ip")
        if not ip:
            resp.status = falcon.HTTP_400
            return
        p = subprocess.Popen(['ip', 'rule', 'del', 'from', ip])
        p.wait()


its = ITS()
app = falcon.API()
app.add_route('/connect', WebService(its))
app.add_route('/admin', WebAdminService())
thread1 = MyThread(its)

if __name__ == '__main__':
    thread1.daemon = True
    thread1.start()
    httpd = simple_server.make_server('127.0.0.1', 8000, app)
    httpd.serve_forever()
