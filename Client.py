import json
import os.path
import socket
import threading
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import struct
from queue import Queue
import datetime
import time

Server_host = socket.gethostname()# '47.109.66.188'
Server_port = 8000
Buffer_size = 1024
# sign_state = -1
# login_state = -1


# 消息类，用于打包和接收消息
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

    # 接收文件消息并放入缓冲区 文件数据流无需编码解码 直接使用字节流读取并发送
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


# 客户端线程，一个用户建立一个线程
class ClientThread(threading.Thread, QObject):
    chat_ui_signal = pyqtSignal()   # 聊天主界面信号
    message_show = pyqtSignal()  # 添加新消息信号
    box_signal = pyqtSignal()
    file_signal = pyqtSignal()

    def __init__(self, state, account, password, win_ui):
        threading.Thread.__init__(self)
        QObject.__init__(self)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # 新建一个socket
        self.account = account
        self.password = password
        self.msg_recv = Massage()
        self.return_state = state
        self.win_ui = win_ui
        self.user_list = {}  # 在线用户列表
        self.msg_data = ""  # 接收的新消息
        self.msg_sender = ""    # 接收的新消息发送方
        self.file_size = 0
        self.file_name = ""
        self.chat_ui_signal.connect(lambda: self.win_ui.chat_ui(self.user_list, self.account))    # 连接聊天界面
        self.message_show.connect(lambda: self.win_ui.msg_show(self.msg_sender, self.msg_data))     # 连接添加新消息函数
        self.box_signal.connect(lambda: self.win_ui.msg_box(self.return_state))
        self.file_signal.connect(lambda: self.win_ui.recv_file(self.file_size, self.file_name))
        self.send_thread = SendThread(self.sock, self.account)
        self.send_thread.daemon = True
        self.send_thread.start()
        # self.chat_ui_signal.emit()

    # 用于线程非正常退出时返回状态码
    def join(self, timeout=None):
        super().join()
        return self.return_state

    # 线程运行函数重载
    def run(self):
        try:    # 尝试连接服务器端，并发送登录信息
            self.sock.connect((Server_host, Server_port))
            if self.return_state == 200:
                self.send_thread.login(self.account, self.password)
            elif self.return_state == 204:
                self.send_thread.sign(self.account, self.password)
        except:     # 无法连接则抛出异常 终止线程
            self.return_state = 403
            self.box_signal.emit()
            # self.chat_ui_signal.emit()
            # self.new_msg_show("123","abc")
            return self.return_state
        # 循环接收消息 每次从消息队列取出一个消息进行处理
        while True:
            self.msg_recv.read(self.sock.recv(Buffer_size))
            while not self.msg_recv.msg_empty():
                msg, state = self.msg_recv.get_msg()
                # 每次读取一条消息,根据状态码作出相应动作
                if state == 201:  # 登录成功（服务器发来在线成员）
                    self.user_list = json.loads(msg)
                    self.chat_ui_signal.emit()  # 打开聊天界面
                    # return self.return_state
                elif state == 203:  # 接收到服务端消息
                    data = json.loads(msg)
                    self.new_msg_show(data["rsc"], data["content"])     # 聊天框加入新消息
                elif state == 205:  # 注册成功 退出当前线程 用户需进行登录操作
                    self.return_state = 205
                    self.box_signal.emit()
                    return state
                elif state == 206:
                    self.return_state = 206
                    data = json.loads(msg)
                    self.new_msg_show(data["rsc"], data["filename"])
                    self.file_size = data["filesize"]
                    self.file_name = data["filename"]
                    self.file_signal.emit()
                elif state == 401:  # 密码错误
                    self.return_state = state
                    self.box_signal.emit()
                    return state
                elif state == 402:  # 账号已被使用
                    self.return_state = 402
                    self.box_signal.emit()
                    return state
                else:
                    self.return_state = 2
                    return self.return_state

    def get_msg(self):
        return self.msg_recv

    def new_msg_show(self, sender, msg):
        sender = sender + " " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.msg_sender = '<span style=\" color: #ff0000;\">%s</span>' % sender
        self.msg_data = msg
        self.message_show.emit()


# 发送线程 用于用户发送消息
class SendThread(threading.Thread):
    def __init__(self, client_socket, account):
        threading.Thread.__init__(self)
        self.sock = client_socket   # 客户端创建的socket
        self.msg_list = Queue()     # 发送消息队列
        self.account = account  # 当前登录用户的账号

    # 重载线程运行函数 循环从消息队列中提取消息进行发送
    def run(self):
        # self.sock.connect((Server_host, Server_port))
        while True:
            new_msg = self.wait_send()
            self.sock.sendall(new_msg)

    # 阻塞等待消息队列加入消息 当有新消息则进行处理
    def wait_send(self):
        while True:
            if not self.msg_list.empty():
                return self.msg_list.get()

    # 外部调用接口，封装数据包加入消息队列
    def add_msg(self, data, state):
        data_send = Massage()
        data_send = data_send.pack(data, state)
        self.msg_list.put(data_send)

    # 发送登录信息
    def login(self, account, password):
        msg_login = {"account": account, "password": password}
        msg_json = json.dumps(msg_login)
        self.add_msg(msg_json, 200)  # 登录状态

    def sign(self, account, password):
        msg_sign = {"account": account, "password": password}
        msg_json = json.dumps(msg_sign)
        self.add_msg(msg_json, 204)  # 注册状态

    # 发送聊天消息
    def send_msg(self, data, account):
        msg_send = {"dst": account, "rsc": self.account, "content": data}
        msg_json = json.dumps(msg_send)
        self.add_msg(msg_json, 202)  # 发送状态

    # def send_file(self, file_path):
    #     self.send_msg(file_path, "1122")


class FileSendThread(threading.Thread, QObject):
    box_signal = pyqtSignal()
    bar_signal = pyqtSignal()
    bar_close_signal = pyqtSignal()

    def __init__(self,  src_account, dst_account, file_path, win_ui):
        threading.Thread.__init__(self)
        QObject.__init__(self)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dst_account = dst_account
        self.src_account = src_account
        self.file_path = file_path
        self.file_name = os.path.split(self.file_path)[1]
        self.send_total = 0  # 已发送的数据长度
        self.file_size = os.path.getsize(self.file_path)
        self.win_ui = win_ui
        self.state = -1
        self.percent = self.send_total / self.file_size * 100
        self.box_signal.connect(lambda: self.win_ui.msg_box(self.state))
        self.bar_signal.connect(lambda: self.win_ui.bar_setval(self.percent))
        self.bar_close_signal.connect(self.win_ui.bar_win.close)
        try:
            self.fp = open(self.file_path, "rb")
        except:
            self.state = 104
            self.box_signal.emit()

    def run(self):
        try:
            self.sock.connect((Server_host, Server_port))
            self.send_file_msg()
            # fo = open(f"C:\\Users\\ChenJiayi\\Desktop\\AnyFiles\\{self.file_name}", "wb+")
            time.sleep(0.001)
            while self.send_total < self.file_size:
                buffer = self.fp.read(1000)
                msg = Massage()
                msg = msg.pack_file(buffer, 207)
                self.sock.sendall(msg)
                # fo.write(msg)
                self.send_total += len(buffer)
                self.percent = int(self.send_total / self.file_size * 100)
                self.bar_signal.emit()
                time.sleep(0.001)
            self.fp.close()
        except:
            self.state = 405
            self.box_signal.emit()
            self.fp.close()
            def pbar_change():
                for i in range(11):
                    time.sleep(1)
                    self.percent = i * 10
                    self.bar_signal.emit()
                time.sleep(1)
                self.bar_close_signal.emit()
            worker = threading.Thread(target=pbar_change)
            worker.daemon = True
            worker.start()
            return self.state

    def send_file_msg(self):
        file_msg = {"filename": self.file_name,
                    "size": self.file_size,
                    "dst": self.dst_account,
                    "src": self.src_account}
        file_msg_json = json.dumps(file_msg)
        msg = Massage()
        msg = msg.pack(file_msg_json, 206)
        self.sock.sendall(msg)


class FileReceiveThread(threading.Thread, QObject):
    box_signal = pyqtSignal()
    bar_signal = pyqtSignal()
    bar_close_signal = pyqtSignal()

    def __init__(self, account, file_path, file_size, win_ui):
        threading.Thread.__init__(self)
        QObject.__init__(self)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.account = account  # 接收文件的账号信息
        self.file_path = file_path  # 保存文件路径
        # self.file_name = os.path.split(self.file_path)[1]
        self.rcv_total = 0  # 已接收的数据长度
        self.file_size = file_size  # 文件大小
        self.file_recv = Massage()  # 接收文件用的消息类
        self.win_ui = win_ui
        self.state = -1
        self.percent = self.rcv_total / self.file_size * 100
        self.box_signal.connect(lambda: self.win_ui.msg_box(self.state))
        self.bar_signal.connect(lambda: self.win_ui.bar_setval(self.percent))
        self.bar_close_signal.connect(self.win_ui.bar_win.close)
        try:
            self.fp = open(self.file_path, "wb+")
        except:
            self.state = 106
            self.box_signal.emit()

    def run(self):
        try:
            self.sock.connect((Server_host, Server_port))
            self.send_file_state()  # 告诉服务器准备接收文件
            while True:  # 循环接收文件 直到发送完毕
                self.file_recv.read_file(self.sock.recv(Buffer_size))
                while not self.msg_recv.msg_empty():
                    msg, state = self.file_rcv.get_msg()
                    # 每次读取一条消息
                    if state == 207:  # 文件传输中
                        self.rcv_total += len(msg)
                        self.fp.write(msg)
                        self.bar_signal.emit()  # 更新进度条
                    elif state == 209 or self.file_size == self.rcv_total:
                        self.state = 209
                        self.box_signal.emit()
                        self.bar_close_signal.emit()  # 关闭进度条以及弹窗提示已完成
                        return
        except:
            self.state = 405
            self.box_signal.emit()
            self.fp.close()
            return self.state

    # 告诉服务器准备接收文件
    def send_file_state(self):
        file_msg = {"filename": self.file_name,
                    "size": self.file_size,
                    "account": self.account}
        file_msg_json = json.dumps(file_msg)
        msg = Massage()
        msg = msg.pack(file_msg_json, 208)
        self.sock.sendall(msg)


# GUI类
class GUI(QWidget):
    progress_update = pyqtSignal()

    def __init__(self):  # 登录窗口，布局，注册窗口，布局，主聊天窗口和布局
        super().__init__()
        self.login_win = QWidget()
        self.login_layout = QGridLayout()
        self.sign_win = QWidget()
        self.sign_layout = QGridLayout()
        self.main_win = QWidget()
        self.main_layout = QGridLayout()
        self.bar_win = QWidget()
        self.bar_win_layout = QGridLayout()  # 进度条部件窗口 用于文件传输
        self.file_bar = QProgressBar()
        self.user_online = QListWidget()  # QComboBox()
        self.socket = socket.socket()
        self.user_list = {}
        self.user_send = 0  # 接收消息的用户的账号
        self.chat_browser = QTextBrowser(self)
        self.cursot = self.chat_browser.textCursor()
        self.main_func()
        self.account = 0
        self.val = 0
        # self.progress_update.connect(lambda: self.bar_setval(self.val))

    def main_func(self):
        print(" ")
        # self.chat_ui({"12345": "uee"}, "12345")
        self.login_func()  # 初始进入登录界面
        # login_state = new_client.join()

    @staticmethod
    def check_account(account):
        for s in account:
            if s < '0' or s > '9':
                return False
        return True

    # 根据对应状态弹出消息提醒盒子
    @staticmethod
    def msg_box(state):
        new_box = QMessageBox()
        if state == 101:
            new_box.setWindowTitle("Empty Account")
            new_box.setText("Input correct account!")
        elif state == 102:  # 账号错误
            new_box.setWindowTitle("Error")
            new_box.setText("Input correct account!")
        elif state == 103:  # 密码为空
            new_box.setWindowTitle("Empty Password")
            new_box.setText("Input correct password!")
        elif state == 104:
            new_box.setWindowTitle("Unknown file")
            new_box.setText("Choose correct file!")
        elif state == 105:
            new_box.setWindowTitle("Success!")
            new_box.setText("File sent successfully!")
        elif state == 106:
            new_box.setWindowTitle("Error")
            new_box.setText("No enough right to save here!")
        elif state == 401:  # 密码错误
            new_box.setWindowTitle("Login Failed!")
            new_box.setText("Wrong password!")
        elif state == 402:  # 账号已被使用
            new_box.setWindowTitle("Account Error")
            new_box.setText("Account has been used!")
        elif state == 403:  # 网络错误
            new_box.setWindowTitle("Connect Error")
            new_box.setText("Connect to server failed!")
        else:
            new_box.setWindowTitle("Error")
            new_box.setText("Unknown Error!")
        new_box.setStandardButtons(QMessageBox.Ok)
        new_box.exec()

    # 处理用户登录请求
    def login_handle(self, account, password):
        # global login_state
        if account == '':
            self.msg_box(101)
        elif not self.check_account(account):
            self.msg_box(102)
        elif password == '':
            self.msg_box(103)
        else:
            new_client = ClientThread(200, account, password, self)  # 创建一个新的客户端线程
            self.client = new_client
            new_client.daemon = True    # 设置客户端线程为守护线程
            new_client.start()
            # login_state = new_client.join()
            # if login_state == 403:
            #     self.msg_box(403)
            # elif login_state == 401:
            #     self.msg_box(401)

    def sign_handle(self, account, password):
        if account == '':
            self.msg_box(101)
        elif not self.check_account(account):
            self.msg_box(102)
        elif password == '':
            self.msg_box(103)
        else:
            new_client = ClientThread(204, account, password, self)  # 创建一个新的客户端线程
            self.client = new_client
            new_client.daemon = True    # 设置客户端线程为守护线程
            new_client.start()
            # sign_state = new_client.join()
            # if sign_state == 403:
            #     self.msg_box(403)
            # elif sign_state == 402:
            #     self.msg_box(402)

    # 登录功能界面
    def login_func(self):
        self.login_win.setFixedSize(400, 300)
        self.login_win.setWindowTitle("Login")
        l_account = QLabel("account")
        l_account.setFont(QFont('宋体', 10))
        e_account = QLineEdit()
        l_pwd = QLabel("password")
        l_pwd.setFont(QFont('宋体', 10))
        e_pwd = QLineEdit()
        e_account.setFont(QFont('宋体', 10))
        e_account.setPlaceholderText("请输入你的账号")
        e_pwd.setFont(QFont('宋体', 10))
        e_pwd.setPlaceholderText("请输入你的密码")

        b_sign = QPushButton("sign up")
        b_sign.clicked.connect(self.sign_func)
        b_sign.clicked.connect(self.login_win.close)
        b_login = QPushButton("Login")
        b_login.clicked.connect(lambda: self.login_handle(e_account.text(), e_pwd.text()))
        self.login_layout.addWidget(l_account, 1, 1)
        self.login_layout.addWidget(e_account, 1, 2)
        self.login_layout.addWidget(l_pwd, 2, 1)
        self.login_layout.addWidget(e_pwd, 2, 2)
        self.login_layout.addWidget(b_sign, 3, 1)
        self.login_layout.addWidget(b_login, 3, 2)
        self.login_win.setLayout(self.login_layout)
        self.login_win.show()

    # 注册功能界面
    def sign_func(self):
        self.sign_win.setFixedSize(400, 300)
        self.sign_win.setWindowTitle("Sign up")
        l_account = QLabel("account")
        e_account = QLineEdit()
        l_pwd = QLabel("password")
        e_pwd = QLineEdit()
        b_login = QPushButton("back to login in")
        b_login.clicked.connect(self.login_func)
        b_login.clicked.connect(self.sign_win.close)
        b_signup = QPushButton("Sign up")
        b_signup.clicked.connect(lambda: self.sign_handle(e_account.text(), e_pwd.text()))
        self.sign_layout.addWidget(l_account, 1, 1)
        self.sign_layout.addWidget(e_account, 1, 2)
        self.sign_layout.addWidget(l_pwd, 2, 1)
        self.sign_layout.addWidget(e_pwd, 2, 2)
        self.sign_layout.addWidget(b_login, 3, 1)
        self.sign_layout.addWidget(b_signup, 3, 2)
        self.sign_win.setLayout(self.sign_layout)
        self.sign_win.show()

    # 修改消息接收方账号
    def change_dst(self, account):
        self.user_send = account
        # print(self.user_send)

    def send_handle(self, content_send):
        self.client.send_thread.send_msg(content_send, self.user_send)  # 调用发送线程接口，加入发送消息队列

    # 发送文件UI 显示进度条
    def send_file(self):
        file_path = QFileDialog.getOpenFileName(self, '选择文件', '')[0]  # 函数返回一个元组 第一个元素为文件绝对路径
        # print(file_path)
        self.bar_win.setWindowTitle('Send Progress')
        self.file_bar.setFixedSize(200, 20)
        self.file_bar.setRange(0, 100)
        self.file_bar.setValue(0)
        self.bar_win_layout.addWidget(self.file_bar, 1, 0)
        file_thread = FileSendThread(self.account, self.user_send, file_path, self)
        file_thread.daemon = True
        file_thread.start()
        self.bar_win.setLayout(self.bar_win_layout)
        self.bar_win.show()

    # 接收文件UI 显示接收进度条与文件保存路径按钮
    def recv_file(self, filesize, filename):
        self.bar_win.setWindowTitle('New File to Receive')
        self.file_bar.setFixedSize(200, 20)
        self.file_bar.setRange(0, 100)
        self.file_bar.setValue(0)

        # 文件开始传输 新建一个接收进程用于接收文件
        def start_trans():
            file_path = QFileDialog.getSaveFileName(self, '选择文件夹', filename, '')[0]  # 函数返回一个元组 第一个元素为文件绝对路径
            file_thread = FileReceiveThread(self.account, file_path, filesize, self)
            file_thread.daemon = True
            file_thread.start()

        start_button = QPushButton()
        start_button.setText("Start")
        start_button.clicked.connect(lambda: start_trans())
        self.bar_win_layout.addWidget(self.file_bar, 0, 0, 1, 2)
        self.bar_win_layout.addWidget(start_button, 1, 0)
        self.bar_win.setLayout(self.bar_win_layout)
        self.bar_win.show()

    def bar_setval(self, val):
        self.file_bar.setValue(val)

    def chat_ui(self, user_list, login_user):  # 在线用户列表 当前登录的用户账号
        self.user_list = {"12345": "yee", "10000": "ha"}  # 测试用; 实际为user_list
        self.main_win.setFixedSize(600, 400)
        self.main_win.setWindowTitle("Sign up")
        self.chat_browser.setFont(QFont('宋体', 10))
        self.chat_browser.setReadOnly(True)
        self.chat_browser.setPlaceholderText('消息展示区域...')
        self.chat_browser.ensureCursorVisible()
        self.account = login_user
        write_browser = QTextEdit(self)
        write_browser.setFont(QFont('宋体', 10))
        self.chat_browser.ensureCursorVisible()

        for p in self.user_list.keys():
            self.user_online.addItem(f"{self.user_list[p]}({p})")
        self.user_online.itemClicked.connect(lambda: self.change_dst(self.user_online.currentItem().text()[-6: -1]))
        b_send = QPushButton("Send")
        # b_send.setFixedSize(100,20)
        b_send.clicked.connect(lambda: self.send_handle(write_browser.toPlainText()))
        b_send_file = QPushButton("Send File")
        b_send_file.clicked.connect(lambda: self.send_file())
        self.main_layout.addWidget(self.chat_browser, 0, 0)
        self.main_layout.addWidget(write_browser, 1, 0, 3, 1)
        self.main_layout.addWidget(b_send, 3, 1)
        self.main_layout.addWidget(self.user_online, 0, 1, 1, 2)
        self.main_layout.addWidget(b_send_file, 2, 1)
        self.main_layout.setColumnStretch(0, 2)
        self.main_layout.setColumnStretch(1, 1)
        self.main_layout.setRowStretch(0, 4)
        self.main_layout.setRowStretch(1, 1)
        self.main_layout.setRowStretch(2, 1)
        self.main_layout.setRowStretch(3, 1)
        self.main_win.setLayout(self.main_layout)
        self.main_win.show()

    def msg_show(self, sender, msg_data):
        # self.chat_browser.append(data[1])
        self.chat_browser.append(sender)  # 在指定的区域显示提示信息
        self.chat_browser.append(msg_data)
        self.chat_browser.moveCursor(self.cursot.End)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = GUI()
    # win.show()
    sys.exit(app.exec_())
