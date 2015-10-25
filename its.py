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
import systemd.journal
import subprocess
from wsgiref import simple_server


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

        def __init__(self):
            self.date = time.strftime('%Y-%m-%d', time.localtime(time.time() - 3600))
            self.accounts = [
                self.AccountInfo('aaa', 'aaa', 0)
            ]

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
        self.check_url = ['http://plumz.me/generate_204',
                          'http://ipv4.i.catofes.com/']
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
            systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 account.name + "   Connect Request Sent Error.")
            return False
        self.last_request_response = resp.read().decode('GB2312')
        if re.search(ur'今天不能再使用客户端', self.last_request_response, re.UNICODE):
            account.connect_limit_reach = True
            systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 account.name + "   Reach Daily API Limit.")
            self.last_check_result = False
            return False
        if re.search(ur'当前连接数超过预定值', self.last_request_response, re.UNICODE):
            self.disconnect(account)
            self.last_check_result = False
            return False
        self.last_check_result = True
        systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
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
            systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
                                 account.name + "   Disconnectall Request Sent Error.")
            return False
        systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
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
            systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S  ', time.localtime(self.last_check_time)) +
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
        self.lost_limit = 1
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


class ChangeNet:
    @staticmethod
    def update(ip, destination):
        destinations = [
            'main',
            'japan',
        ]
        if not ip:
            return False
        if ip == "10.16.0.1":
            return False
        if not re.match("^10.16.*", ip):
            return False
        if destination not in destinations:
            return False
        p = subprocess.Popen(['ip', 'rule', 'del', 'from', ip])
        p.wait()
        p.terminate()
        p.wait()
        p = subprocess.Popen(['ip', 'rule', 'add', 'from', ip, 'lookup', destination])
        p.wait()
        p.terminate()
        p.wait()
        return True


class WebService:
    def __init__(self, its):
        self.its = its

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        p = subprocess.Popen(['ip', 'rule', 'list', '|', 'grep', req.get_header("X-Real-IP")],
                             stdout=subprocess.PIPE)
        destination = p.stdout.readline()
        p.wait()
        p.terminate()
        p.wait()
        resp.body = json.dumps({
            'IP': req.get_header("X-Real-IP"),
            'destination': destination,
            'check_status': self.its.last_check_result,
            'check_time': time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self.its.last_check_time)),
            'request_time': time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self.its.last_request_time)),
            'request_response': self.its.last_request_response,
            'next_reconnect_time': time.strftime('%Y-%m-%d  %H:%M:%S',
                                                 time.localtime((self.its.lost_limit - self.its.lost_count) * 5
                                                                + time.time()))
        })
        return True

    def on_post(self, req, resp):
        if self.its.connect():
            resp.status = falcon.HTTP_200
        else:
            resp.status = falcon.HTTP_400
        p = subprocess.Popen(['ip', 'rule', 'list', '|', 'grep', req.get_header("X-Real-IP")],
                             stdout=subprocess.PIPE)
        destination = p.stdout.readline()
        p.wait()
        p.terminate()
        p.wait()
        resp.body = json.dumps({
            'IP': req.get_header("X-Real-IP"),
            'destination': destination,
            'check_status': self.its.last_check_result,
            'check_time': time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self.its.last_check_time)),
            'request_time': time.strftime('%Y-%m-%d  %H:%M:%S', time.localtime(self.its.last_request_time)),
            'request_response': self.its.last_request_response,
            'next_reconnect_time': time.strftime('%Y-%m-%d  %H:%M:%S',
                                                 time.localtime((self.its.lost_limit - self.its.lost_count) * 5
                                                                + time.time()))
        })
        return True

    def on_put(self, req, resp):
        ip = req.get_header("X-Real-IP")
        if not ip:
            return falcon.HTTP_400
        if not req.get_param("dest"):
            return falcon.HTTP_400
        if not ChangeNet.update(ip, req.get_param("dest")):
            return falcon.HTTP_400
        p = subprocess.Popen(['ip', 'rule', 'list', '|', 'grep', req.get_header("X-Real-IP")],
                             stdout=subprocess.PIPE)
        destination = p.stdout.readline()
        p.wait()
        p.terminate()
        p.wait()

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


its = ITS()
app = falcon.API()
app.add_route('/connect', WebService(its))
thread1 = MyThread(its)

if __name__ == '__main__':
    thread1.daemon = True
    thread1.start()
    httpd = simple_server.make_server('127.0.0.1', 8000, app)
    httpd.serve_forever()
