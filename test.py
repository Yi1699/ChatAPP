import os.path
import socket
import threading
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import struct
from queue import Queue
import time

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

    # 内部函数 添加包头
    def add_head(self, dlen, state):
        self.msg_code += struct.pack('!2s2i', b"##", dlen, state)

    # 外部调用接口 用于打包消息
    def pack(self, data, state):
        data_code = data.encode(encoding='utf-8')
        self.add_head(len(data_code), state)
        self.msg_code += data_code
        return self.msg_code

    # 为要发送的文件数据包进行打包
    def pack_file(self, data, state):
        self.add_head(len(data), state)
        self.msg_code += data
        return self.msg_code

    # 接收消息并放入缓冲区
    def read(self, data_recv):
        self.msg_recv += data_recv
        self.read_head()
        self.change_msg()

    def read_file(self, data_recv):
        self.msg_recv += data_recv
        self.read_head()
        if self.curr_len > self.received_len:  # 如果当前消息的长度大于已接收的长度，说明仍未接收完毕
            # 如果剩余已接收但未处理的消息比剩余未处理的消息短，说明仍有消息未发送完毕，此时将所有消息加入当前处理的消息中
            if len(self.msg_recv) < self.curr_len - self.received_len:
                self.msg[self.curr_num] += self.msg_recv
                self.received_len += len(self.msg_recv)
                self.msg_recv = b''
            else:  # 否则未处理的消息部分已经全部被接受，只需截取部分消息加入当前消息中
                self.msg[self.curr_num] += self.msg_recv[:self.curr_len - self.received_len]
                self.received_len = 0
                self.msg_recv = self.msg_recv[self.curr_len - self.received_len:]
                self.curr_len = 0 if self.msg_len.empty else self.msg_len.get()
                self.curr_num += 1
                self.read_head()

    # 读取消息头
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
            if state == 207:
                self.msg.append(b'')
            else:
                self.msg.append('')

    # 转换消息格式 将同一个消息的不同包作为同一个消息内容放入消息队列中
    def change_msg(self):
        if self.curr_len > self.received_len:   # 如果当前消息的长度大于已接收的长度，说明仍未接收完毕
            # 如果剩余已接收但未处理的消息比剩余未处理的消息短，说明仍有消息未发送完毕，此时将所有消息加入当前处理的消息中
            if len(self.msg_recv) < self.curr_len - self.received_len:
                self.msg[self.curr_num] += self.msg_recv.decode('utf-8')
                self.received_len += len(self.msg_recv)
                self.msg_recv = b''
            else:   # 否则未处理的消息部分已经全部被接受，只需截取部分消息加入当前消息中
                self.msg[self.curr_num] += self.msg_recv[:self.curr_len - self.received_len].decode('utf-8')
                self.received_len = 0
                self.msg_recv = self.msg_recv[self.curr_len - self.received_len:]
                self.curr_len = 0 if self.msg_len.empty else self.msg_len.get()
                self.curr_num += 1
                self.read_head()

    # 外部调用接口，获取消息队列的第一个消息
    def get_msg(self):
        self.curr_num -= 1
        msg = self.msg[0]
        self.msg = self.msg[1:]
        return msg, self.state.get()

    # 外部调用接口，判断消息队列是否为空
    def msg_empty(self):
        if len(self.msg) == 0:
            return True
        else:
            return False



# a = Massage()
# b = "sdalkfjffffffffjfjfjfjfjfjfjfjfjfjfjfjfjfjfjfjfjfjbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb3333333333333333333333333333332rwaef"
# k = "123456789123456789123456789abcd"
# bp = a.pack(b, 1)
# d = Massage()
# kp = d.pack(k, 2)
# kp = kp[:-4]
# test = b'abcd'
# recv = Massage()
# recv.read(bp)
# recv.read(kp)
# print(kp)
# recv.read(test)
# print(test)
# while not recv.msg_empty():
#     pp = recv.get_msg()
#     print(pp)
# a = lambda x: x + 1
# print(a)


temp_msg = Massage()


def send():
    global temp_msg
    send_total = 0
    fp = r'C:\Users\ChenJiayi\Pictures\1.bmp'
    file_size = os.path.getsize(fp)
    file_name = os.path.split(fp)[1]
    fi = open(fp, "rb+")
    while send_total < file_size:
        buffer = fi.read(1000)
        msg = Massage()
        msg = msg.pack_file(buffer, 207)
        # fo.write(msg)
        send_total += len(buffer)
        time.sleep(0.001)
        temp_msg.read_file(msg)
    a = Massage()
    a = a.pack_file(b"", 505)
    temp_msg.read_file(a)


def rcv():
    global temp_msg
    with open("C:\\Users\\ChenJiayi\\Desktop\\AnyFiles\\test.bmp", "wb+") as f:
        while True:
            time.sleep(0.001)
            while not temp_msg.msg_empty():
                a, s = temp_msg.get_msg()
                if s == 505:
                    return
                # b = a.decode(errors='ignore')
                f.write(a)


t1 = threading.Thread(target=send)
t2 = threading.Thread(target=rcv)
t1.start()
t2.start()
t1.join()
t2.join()
