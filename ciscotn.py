import telnetlib
import sys
import time
import re

INSTRUCTION = """\
-u USERNAME -p PSWD -h HOST [-e]
-u - username
-p - password
-h - host
-e - enable mode\
"""


def exit(string=None):
    if string is None:
        string = INSTRUCTION
    print string
    sys.exit()


def get_args():
    def _get_a(item):
        a = item.split(' ')
        return (a[0], a[1] if len(a) > 1 else None)
    args_string = ' '.join(sys.argv[1:])
    args = dict([_get_a(a) for a in args_string.split('-') if a])
    for a in ['u', 'p', 'h']:
        if a not in args:
            exit()
    if not re.match(r'[\d]+\.[\d]+\.[\d]+\.[\d+]', args['h']):
        exit('%s is not ip' % args['h'])
    return dict(user=args['u'], pswd=args['p'], host=args['h'],
                enable=True if 'e' in args else False)


class CiscoTnError(Exception):
    def __init__(self, msg=None, reason=None):
        if reason:
            msg = '%s: \n %s' % (msg, reason)
        Exception.__init__(self, msg)


class LoginError(CiscoTnError):
    def __init__(self, host, login):
        msg = "Enable to login to host %s" % (host)
        CiscoTnError.__init__(self, msg, login)


class EnableError(CiscoTnError):
    def __init__(self, host, enbl):
        CiscoTnError.__init__(
            self, "Enable to elevate a privelege in eq %s" % (host), enbl)


class MvrError(CiscoTnError):
    def __init__(self, host, port, reason):
        msg = "Error in mvr config for host %s port %s" % (host, port)
        CiscoTnError.__init__(self, msg, reason)


class CiscoTn(object):
    """docstring for CiscoTn"""
    def __init__(self, user, pswd, host,
                 enable=True, sleep=3, max_read_time=5):
        super(CiscoTn, self).__init__()
        self.max_read_time = max_read_time
        self.sleep = sleep
        self.tn = telnetlib.Telnet(host)
        self.read_until("Username:")
        self.tn.write('%s\n' % user)
        self.read_until("Password:")
        self.tn.write('%s\n' % pswd)
        login = self.read_until(">")
        if enable:
            if login.find('>') < 0:
                raise LoginError(host, login)
            self.write("enable")
            self.read_until("Password:")
            self.tn.write('%s\n' % pswd)
            enbl = self.wait()
        else:
            enbl = login
        if enbl.find('#') < 0:
            raise EnableError(host, enbl)
        self.conf = False

    def read_until(self, val, leaf=None):
        def can_mode(data, tm_start, tm_end):
            val_not_in = data.find(val) < 0
            tm = tm_end - tm_start
            return val_not_in or tm > self.max_read_time

        data = self.tn.read_until(val, self.sleep)
        if leaf:
            tm_start = time.time()
            tm_end = time.time()
            while can_mode(data, tm_start, tm_end):
                self.write('')
                data += self.tn.read_until(val, self.sleep)
                print data
        return data

    def wait(self, leaf=None):
        return self.read_until("#", leaf)

    def write(self, val):
        self.tn.write(' %s \n' % val)

    def do_sleep(self):
        time.sleep(self.sleep)

    def close(self):
        self.tn.write(" exit \n")
        self.tn = None

    def save(self):
        self.tn.write(" copy run start \n")
        self.tn.write(" \n")

    def to_conf(self):
        self.tn.write(" conf t \n")
        self.conf = True

    def end_conf(self):
        self.tn.write(" end\n")
        self.conf = False

    def delete_int(self, num, name='vlan'):
        self.tn.write(" no int %s %s \n" % (name, num))
        self.wait()

    def delete_int_range(self, start, end, name='vlan'):
        self.to_conf()
        for num in xrange(start, end+1):
            self.delete_int(num, name)
        self.end_conf()

    def show_ver(self):
        self.write("show ver")
        shver = self.wait(True)
        print shver

    def undeb(self):
        self.write('undeb all')

    def noipsoursceguard(self, num):
        self.tn.write(" conf \n")
        self.tn.write(" int e 1/%s \n" % (num))
        self.wait()
        self.tn.write(" no ip source-guard \n")
        self.end_conf()

    def testiptv(self, host, port):
        def _test(msg):
            self.tn.write(msg)
            print self.tn.read_until('#')
        print
        print host, '==>', port
        self.tn.write(' sh mvr interface \n')
        mvrint = self.tn.read_until('#').split('\n')[2:]
        if filter(lambda s: 'Inactive' in s, mvrint):
            raise MvrError(host, port, 'No port mvr configured')
        rec = filter(lambda s: 'Receiver' in s, mvrint)
        if not rec or not filter(lambda s: 'Eth1/%s' % port in s, rec):
            raise MvrError(host, port, 'No port mvr-receiver configured')
        if not filter(lambda s: 'Source' in s, mvrint):
            raise MvrError(host, port, 'No port mvr-source configured')
        print '---------------------'

