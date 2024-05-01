import socket
import threading
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import struct
from queue import Queue

# a = struct.pack('!2s2i', b"##", 4, 1202)
# a += "abc".encode('utf-8')
# b, c, d = struct.unpack('!2s2i', a[:10])
# print("{} {} {}".format(b, c, d))


class Massage:
    def __init__(self):
        self.msg = []
        self.msg_code = b''
        self.msg_recv = b''
        self.msg_len = Queue()
        self.state = Queue()
        self.curr_num = 0
        self.curr_len = 0
        self.received_len = 0

    def add_head(self, dlen, state):
        self.msg_code += struct.pack('!2s2i', b"##", dlen, state)

    def pack(self, data, state):
        data_code = data.encode(encoding='utf-8')
        self.add_head(len(data_code), state)
        self.msg_code += data_code
        return self.msg_code

    def read(self, data_recv):
        self.msg_recv += data_recv
        self.read_head()
        self.change_msg()

    def read_head(self):
        if len(self.msg_recv) < 10:
            return
        head, recv_len, state = struct.unpack('!2s2i', self.msg_recv[:10])
        if head == b'##':
            self.msg_len.put(recv_len)
            self.state.put(state)
            if self.curr_len == 0:
                self.curr_len = self.msg_len.get()
            self.msg_recv = self.msg_recv[10:]
            self.msg.append('')

    def change_msg(self):
        if self.curr_len > self.received_len:
            if len(self.msg_recv) < self.curr_len - self.received_len:
                self.msg[self.curr_num] += self.msg_recv.decode('utf-8')
                self.received_len += len(self.msg_recv)
                self.msg_recv = b''
            else:
                self.msg[self.curr_num] += self.msg_recv[:self.curr_len - self.received_len].decode('utf-8')
                self.received_len = 0
                self.msg_recv = self.msg_recv[self.curr_len - self.received_len:]
                self.curr_len = 0 if self.msg_len.empty else self.msg_len.get()
                self.curr_num += 1
                self.read_head()

    def get_msg(self):
        self.curr_num -= 1
        msg = self.msg[0]
        self.msg = self.msg[1:]
        return msg

    def msg_empty(self):
        if len(self.msg) == 0:
            return True
        else:
            return False


a = Massage()
b = "sdalkfjffffffffjfjfjfjfjfjfjfjfjfjfjfjfjfjfjfjfjfjbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb3333333333333333333333333333332rwaef"
k = "123456789123456789123456789abcd"
bp = a.pack(b, 1)
d = Massage()
kp = d.pack(k, 2)
kp = kp[:-4]
test = b'abcd'
recv = Massage()
recv.read(bp)
recv.read(kp)
print(kp)
recv.read(test)
print(test)
while not recv.msg_empty():
    pp = recv.get_msg()
    print(pp)
a = lambda x: x + 1
print(a)