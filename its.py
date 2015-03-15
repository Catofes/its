#!/bin/python2

#import mechanize
import cookielib
import re
import urllib2
import urllib
import time
import math
import threading
import falcon
import json
import systemd.journal
from wsgiref import simple_server


"""
def web_login():
    br = mechanize.Browser()
    cj = cookielib.LWPCookieJar()
    br.set_cookiejar(cj)

    #br.set_handle_gzip(True)
    br.set_handle_redirect(True)
    br.set_handle_referer(True)
    br.set_handle_robots(False)

    br.set_debug_http(True)
    br.addheaders = [('User-agent', 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.1.11) Gecko/20100701 Firefox/3.5.11')]
    response = br.open('http://its.pku.edu.cn/')
    for f in br.forms():
        print f

    data = response.read()
    m = re.search(r'unescape\(\"[0-9A-Za-z%]*\"\)', data, re.M)
    if m is None:
        return False
    key = urllib2.unquote(m.group()[10:-2])
    print key

    br.select_form('lif')
    username = "1100011354"
    password = "Sqrt21414"
    br.form.set_all_readonly(False)
    br.form['username1'] = username
    br.form['password'] = password
    br.form['fwrd'] = ["free"]
    br.form['username'] = username+key+password+key+str(12)
    br.submit()
"""

class ITS:
    def __init__(self):
        self.last_request_time = 0
        self.last_check_time = 0
        self.last_check_result = True
        self.last_request_response = ''
        self.last_request_result = True
        self.lost_count = 0
        self.lost_limit = 1
        self.check_url = ['http://plumz.me/',
                          'http://ipv4.i.catofes.com/']
        self.lock = threading.Lock()

    def c_lock(func):
        def acquire_lock(self, op):
            if self.lock.acquire(1):
                result = func(self, op)
                self.lock.release()
                return result
            else:
                return False
        return acquire_lock

    @c_lock
    def connect(self, op):
        if op == 'connect':
            range = '2'
            operation = 'connect'
        else:
            range = '4'
            operation = 'disconnectall'
        if op == 'connect':
            self.last_request_time = time.time()
        try:
            resp = urllib2.urlopen(
                "https://its.pku.edu.cn:5428/ipgatewayofpku",
                urllib.urlencode(
                    {
                        "uid": "gwxpwjz",
                        "password": "lijiao214",
                        "range": range,
                        "operation": operation,
                        "timeout": "1"
                    }
                ),timeout=5
            )
        except Exception as e:
            self.last_request_result = False
            systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.last_check_time)) +
                  " Reconnect Request Sent Error.")
            return False
        self.last_request_result = True
        self.last_request_response = resp.read().decode('GB2312')
        systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.last_check_time)) +
                  " Reconnect Request Sent Without Error.")
        return True

    def check(self):
        self.last_check_time = time.time()
        last_check_result = False
        for url in self.check_url:
            try:
                resp = urllib2.urlopen(
                    url,
                    timeout=3
                )
            except Exception as e:
                continue
            last_check_result = True
            break
        self.last_check_time = last_check_result
        if not self.last_check_result:
            systemd.journal.send(time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.last_check_time)) +
                  " Detect Connection Lost. Try to reconnect.")
            return False
        return True

    def check_fail(self):
        self.lost_count += 1
        if self.lost_count >= self.lost_limit:
            if self.lost_limit >= 64:
                self.lost_limit = math.floor(256*math.sqrt(self.lost_count/256.0))
            else:
                self.lost_limit *= 2
            if self.lost_limit >= 8:
                self.connect('disconnect')
            self.connect('connect')
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


class WebService:
    def __init__(self, its):
        self.its = its

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        resp.body = json.dumps({
            'check_status': self.its.last_check_result,
            'check_time': time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.its.last_check_time)),
            'request_time': time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.its.last_request_time)),
            'request_response': self.its.last_request_response,
            'next_reconnect_time': time.strftime('%Y-%m-%d  %H:%M:%S',
                                                 time.localtime((self.its.lost_limit - self.its.lost_count) * 5
                                                                + time.time()))
        })
        return True

    def on_post(self, req, resp):
        if self.its.connect('connect'):
            resp.status = falcon.HTTP_200
        else:
            resp.status = falcon.HTTP_400
        resp.body = json.dumps({
            'check_status': self.its.last_check_result,
            'check_time': time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.its.last_check_time)),
            'request_time': time.strftime('%Y-%m-%d  %H:%M:%S',time.localtime(self.its.last_request_time)),
            'request_response': self.its.last_request_response,
            'next_reconnect_time': time.strftime('%Y-%m-%d  %H:%M:%S',
                                                 time.localtime((self.its.lost_limit - self.its.lost_count) * 5
                                                                + time.time()))
        })
        return True

its = ITS()
app = falcon.API()
app.add_route('/connect', WebService(its))
thread1 = MyThread(its)

if __name__ == '__main__':
    thread1.daemon = True
    thread1.start()
    httpd = simple_server.make_server('127.0.0.1', 8000, app)
    httpd.serve_forever()

