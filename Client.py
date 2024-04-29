import socket
import threading
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import struct
from queue import Queue

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
        return msg, self.state.get()

    def msg_empty(self):
        if len(self.msg) == 0:
            return True
        else:
            return False


class ClientThread(threading.Thread):
    def __init__(self, server_socket, account):
        threading.Thread.__init__(self)
        self.sock = server_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.account = account

    def run(self):
        self.sock.connect((Server_host, Server_port))

        print("")


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

    # def initUI(self):
    #     self.setGeometry(300, 300, 300, 220)
    #     self.setWindowTitle('Icon')
    #     self.setWindowIcon(QIcon('web.png'))
    #     self.show()
    #

    def main_func(self):
        print(" ")
        self.login_func()  # 初始进入登录界面

    def check_account(self, account):
        for s in account:
            if s < '0' or s > '9':
                return False
        return True


    def login_handle(self, account, password):
        if account == '':
            print("eror")
        elif password == '':
            print("!")
        elif not self.check_account(account):
            error_account = QMessageBox.warning(self, "错误", "系统错误")
            error_account.exec_()
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
        # b_login.clicked.connect(self.login_win.close)
        self.login_layout.addWidget(l_account, 1, 1)
        self.login_layout.addWidget(e_account, 1, 2)
        self.login_layout.addWidget(l_pwd, 2, 1)
        self.login_layout.addWidget(e_pwd, 2, 2)
        self.login_layout.addWidget(b_sign, 3, 1)
        self.login_layout.addWidget(b_login, 3, 2)
        self.login_win.setLayout(self.login_layout)
        self.login_win.show()

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
        self.sign_layout.addWidget(l_account, 1, 1)
        self.sign_layout.addWidget(e_account, 1, 2)
        self.sign_layout.addWidget(l_pwd, 2, 1)
        self.sign_layout.addWidget(e_pwd, 2, 2)
        self.sign_win.setLayout(self.sign_layout)
        self.sign_win.show()

    def chat_ui(self):
        self.main_win.setFixedSize(800, 400)
        self.main_win.setWindowTitle("Sign up")
        chat_browser = QTextBrowser(self)
        chat_browser.setFont(QFont('宋体', 8))
        chat_browser.setReadOnly(True)
        chat_browser.setPlaceholderText('消息展示区域...')
        chat_browser.ensureCursorVisible()

        write_browser = QTextEdit(self)
        write_browser.setFont(QFont('宋体', 8))
        chat_browser.ensureCursorVisible()

        # l_account = QLabel("account")
        # e_account = QLineEdit()
        # l_pwd = QLabel("password")
        # e_pwd = QLineEdit()
        b_send = QPushButton("Send")
        self.main_layout.addWidget(chat_browser, 0, 0)
        self.main_layout.addWidget(write_browser, 1, 0)
        self.main_layout.addWidget(b_send, 2, 1)

        # b_send.clicked.connect(self.login_func)
        # self.main_layout.addWidget(l_account, 1, 1)
        # self.main_layout.addWidget(e_account, 1, 2)
        # self.main_layout.addWidget(l_pwd, 2, 1)
        # self.main_layout.addWidget(e_pwd, 2, 2)
        self.main_win.setLayout(self.main_layout)
        self.main_win.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = GUI()
    # win.show()
    sys.exit(app.exec_())

# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import *
# from PyQt5.QtGui import *
# import sys
#
# from QCandyUi import CandyWindow
#
# # 导入socket 通信模块
# import socket
# class ClientUI(QWidget):
#     def __init__(self):
#         super(ClientUI, self).__init__()
#         self.init_ui()
#
#     def init_ui(self):
#         self.setWindowTitle('socket 客户端  公众号：[Python 集中营]')
#         self.setWindowIcon(QIcon('hi.ico'))
#         self.setFixedSize(500, 300)
#
#         hbox = QHBoxLayout()
#
#         hbox_v1 = QVBoxLayout()
#         self.brower = QTextBrowser()
#         self.brower.setFont(QFont('宋体', 8))
#         self.brower.setReadOnly(True)
#         self.brower.setPlaceholderText('消息展示区域...')
#         self.brower.ensureCursorVisible()
#         hbox_v1.addWidget(self.brower)
#
#         hbox_v2 = QVBoxLayout()
#
#         hbox_v2_g1 = QGridLayout()
#         self.ip_label = QLabel()
#         self.ip_label.setText('ip地址 ')
#         self.ip_txt = QLineEdit()
#         self.ip_txt.setPlaceholderText('0.0.0.0')
#
#         self.port_label = QLabel()
#         self.port_label.setText('端口 ')
#         self.port_txt = QLineEdit()
#         self.port_txt.setPlaceholderText('4444')
#
#         self.message = QTextEdit()
#         self.message.setPlaceholderText('发送消息内容...')
#
#         hbox_v2_g1.addWidget(self.ip_label, 0, 0, 1, 1)
#         hbox_v2_g1.addWidget(self.ip_txt, 0, 1, 1, 1)
#
#         hbox_v2_g1.addWidget(self.port_label, 1, 0, 1, 1)
#         hbox_v2_g1.addWidget(self.port_txt, 1, 1, 1, 1)
#
#         hbox_v2_g1.addWidget(self.message, 2, 0, 1, 2)
#
#         self.start_btn = QPushButton()
#         self.start_btn.setText('发送消息')
#         self.start_btn.clicked.connect(self.start_btn_clk)
#
#         hbox_v2.addLayout(hbox_v2_g1)
#         hbox_v2.addWidget(self.start_btn)
#
#         hbox.addLayout(hbox_v1)
#         hbox.addLayout(hbox_v2)
#
#         self.thread_ = ClientThread(self)
#         self.thread_.message.connect(self.show_message)
#
#         self.setLayout(hbox)
#
#     def show_message(self, text):
#         '''
#         槽函数：向文本浏览器中写入内容
#         :param text:
#         :return:
#         '''
#         cursor = self.brower.textCursor()
#         cursor.movePosition(QTextCursor.End)
#         self.brower.append(text)
#         self.brower.setTextCursor(cursor)
#         self.brower.ensureCursorVisible()
#
#     def start_btn_clk(self):
#         self.thread_.start()
#
#
# class ClientThread(QThread):
#     message = pyqtSignal(str)
#
#     def __init__(self, parent=None):
#         super(ClientThread, self).__init__(parent)
#         self.parent = parent
#         self.working = True
#         self.is_connect = False
#
#     def __del__(self):
#         self.working = False
#         self.wait()
#
#     def run(self):
#         try:
#             if self.is_connect is False:
#                 self.connect_serv()
#             # 将控制台输入消息进行 utf-8 编码后发送
#             self.socket_client.send(self.parent.message.toPlainText().strip().encode('utf-8'))
#             self.message.emit(self.socket_client.recv(1024).decode('utf-8'))
#         except Exception as e:
#             self.message.emit("发送消息异常：" + str(e))
#
#     def connect_serv(self):
#         try:
#             self.message.emit("正在创建客户端socket...")
#             # 创建客户端 socket
#             self.socket_client = socket.socket()
#             # 连接服务端
#             address = (self.parent.ip_txt.text().strip(), int(self.parent.port_txt.text().strip()))
#             self.socket_client.conne