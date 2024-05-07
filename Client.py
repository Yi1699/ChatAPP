import json
import socket
import threading
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import struct
from queue import Queue
import datetime

Server_host = '47.109.66.188'
Server_port = 8000
Buffer_size = 1024


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

    # 接收消息并放入缓冲区
    def read(self, data_recv):
        self.msg_recv += data_recv
        self.read_head()
        self.change_msg()

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
    message_show = pyqtSignal() # 添加新消息信号

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
        self.chat_ui_signal.connect(lambda: self.win_ui.chat_ui(self.user_list))    # 连接聊天界面
        self.message_show.connect(lambda: self.win_ui.msg_show(self.msg_sender, self.msg_data))     # 连接添加新消息函数
        self.send_thread = SendThread(self.sock, self.account)
        self.send_thread.start()

    # 用于线程非正常退出时返回状态码
    def join(self, timeout=None):
        super().join()
        return self.return_state

    # 线程运行函数重载
    def run(self):
        try:    # 尝试连接服务器端，并发送登录信息
            self.sock.connect((Server_host, Server_port))
            self.send_thread.login(self.account, self.password)
        except:     # 无法连接则抛出异常 终止线程
            self.return_state = 403
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
                elif state == 401:  # 密码错误
                    return state
                elif state == 203:  # 接收到服务端消息
                    data = json.loads(msg)
                    self.new_msg_show(data["rsc"], data["content"])     # 聊天框加入新消息
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
            self.sock.send(new_msg)

    # 阻塞等待消息队列加入消息 当有新消息则进行处理
    def wait_send(self):
        while True:
            if not self.msg_list.empty():
                return self.msg_list.get()

    # 外部调用接口，封装数据包加入消息队列
    def add_msg(self, data, state):
        data_send = Massage()
        data_send.pack(data, state)
        self.msg_list.put(data_send)

    # 发送登录信息
    def login(self, account, password):
        msg_login = {"account": account, "password": password}
        msg_json = json.dumps(msg_login)
        self.add_msg(msg_json, 200)  # 登录状态

    # 发送聊天消息
    def send_msg(self, data, account):
        msg_send = {"dst": account, "rsc": self.account, "content": data}
        msg_json = json.dumps(msg_send)
        self.add_msg(msg_json, 202)  # 发送状态


# GUI类
class GUI(QWidget):
    def __init__(self):  # 登录窗口，布局，注册窗口，布局，主聊天窗口和布局
        super().__init__()
        self.login_win = QWidget()
        self.login_layout = QGridLayout()
        self.sign_win = QWidget()
        self.sign_layout = QGridLayout()
        self.main_win = QWidget()
        self.main_layout = QGridLayout()
        self.main_func()
        self.socket = socket.socket()
        self.user_list = {}
        self.user_send = 0  # 接收消息的用户的账号
        self.chat_browser = QTextBrowser(self)
        self.cursot = self.chat_browser.textCursor()

    def main_func(self):
        print(" ")
        self.login_func()  # 初始进入登录界面

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
        elif state == 401:  # 密码错误
            new_box.setWindowTitle("Login Failed!")
            new_box.setText("Wrong password!")
        elif state == 402:
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
        if account == '':
            self.msg_box(101)
        elif not self.check_account(account):
            self.msg_box(102)
        elif password == '':
            self.msg_box(103)
        else:
            new_client = ClientThread(200, account, password, self)  # 创建一个新的客户端线程
            self.client = new_client
            new_client.start()
            login_state = new_client.join()
            if login_state == 403:
                self.msg_box(403)
            elif login_state == 401:
                self.msg_box(401)

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
            new_client.start()
            sign_state = new_client.join()
            if sign_state == 403:
                self.msg_box(403)
            elif sign_state == 402:
                self.msg_box(402)

    # 登录功能界面
    def login_func(self):
        self.login_win.setFixedSize(800,400)
        self.login_win.setWindowTitle("Login")
        l_account = QLabel("account")
        e_account = QLineEdit()
        l_pwd = QLabel("password")
        e_pwd = QLineEdit()
        e_account.setFont(QFont('宋体', 8))
        e_account.setPlaceholderText("请输入你的账号")
        e_pwd.setFont(QFont('宋体', 8))
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
        self.sign_win.setFixedSize(800, 400)
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

    def change_dst(self, account):
        self.user_send = account

    def send_handle(self, content_send):
        self.client.send_thread.send_msg(content_send, self.user_send)  # 调用发送线程接口，加入发送消息队列

    def chat_ui(self, user_list):
        self.user_list = user_list
        self.main_win.setFixedSize(800, 400)
        self.main_win.setWindowTitle("Sign up")
        self.chat_browser.setFont(QFont('宋体', 10))
        self.chat_browser.setReadOnly(True)
        self.chat_browser.setPlaceholderText('消息展示区域...')
        self.chat_browser.ensureCursorVisible()

        write_browser = QTextEdit(self)
        write_browser.setFont(QFont('宋体', 8))
        self.chat_browser.ensureCursorVisible()

        user_online = QListWidget()  # QComboBox()
        user_online.resize(200,300)
        for p in self.user_list:
            user_online.addItem(f"{user_list[p]}({p})")
        user_online.clicked.connect(lambda: self.change_dst(user_online.currentItem().text()[-6: -1]))
        b_send = QPushButton("Send")
        b_send.clicked.connect(lambda: self.send_handle(write_browser.toPlainText()))
        self.main_layout.addWidget(self.chat_browser, 0, 0)
        self.main_layout.addWidget(write_browser, 1, 0)
        self.main_layout.addWidget(b_send, 2, 1)

        self.main_win.setLayout(self.main_layout)
        self.main_win.show()

    def msg_show(self, sender, msg_data):
        # self.chat_browser.append(data[1])
        self.chat_browser.append(sender)  # 在指定的区域显示提示信息
        self.chat_browser.append(msg_data)
        self.chat_browser.moveCursor(self.cursot.End)
        # a = data
        # cursor = self.chat_browser.textCursor()
        # cursor.movePosition(QTextCursor.End)  # 将光标移动到文本末尾
        # cursor.insertText("\nThis is a new line.")  # 在光标位置插入新文本
        # self.chat_browser.setTextCursor(cursor)  # 设置QTextBrowser的光标
        # self.chat_browser.centerCursor()  # 将光标滚动到视图中


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = GUI()
    # win.show()
    sys.exit(app.exec_())
