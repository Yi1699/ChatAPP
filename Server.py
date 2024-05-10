import socket
import threading
import struct
import json
from queue import Queue

Server_Host = socket.gethostname()
Server_Port = 8000
BUFFER_SIZE = 1024

# 存储用户密码和当前在线用户
user_password = {}
curr_user = {}

# 存储客户端对应的线程
client_threads = {}

# 初始化一个空列表，用于存储已连接的客户端套接字
client_list = []

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


class ClientThread(threading.Thread):
    def __init__(self, client_socket, client_address):
        threading.Thread.__init__(self)
        self.sock = client_socket
        self.address = client_address
        self.msg_recv = Massage()

    def run(self):
        print(f"Connection from {self.address}")
        # self.sock.send("Welcome to the chatroom!".encode())
        # self.register()  # 默认先注册
        while True:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                # if not data:
                #     break
                self.handle_data(data)
            except Exception as e:
                print(f"Error: {e}")
                break

        self.logout(self.address)
        self.sock.close()
        print(f"Connection {self.address} closed")

    def handle_data(self, data):
        # 循环接收消息 每次从消息队列取出一个消息进行处理
        self.msg_recv.read(data)
        while not self.msg_recv.msg_empty():
            msg, state = self.msg_recv.get_msg()
            # 每次读取一条消息,根据状态码作出相应动作
            self.process_message(state, msg)  # 注意不同类别的msg格式不同 根据state区分

    def process_message(self, state, data):
        if state == 200:  # 登录
            self.login(data)
        elif state == 204:  # 注册
            self.sign_up(data)
        elif state == 202:  # 发送消息
            self.broadcast_message(data)
        elif state == 208:  # 文件接收准备
            self.prepare_file_receiving(data)

    def login(self, data):
        account, password = self.parse_data(data)
        # print(account, password)
        if account in user_password and user_password[account] == password:
            if account in curr_user:
                self.sock.sendall(struct.pack('!2s2i', b'##', 0, 406))  # 重复登录
            else:
                curr_user['account'] = account
                client_threads[account] = self
                send_data = Massage()
                send_data = send_data.pack(json.dumps(curr_user), 201)
                self.sock.sendall(send_data)  # 登录成功是201
        else:
            self.sock.sendall(struct.pack('!2s2i', b'##', 0, 401))

    def sign_up(self, data):
        account, password = self.parse_data(data)
        print(account, password)
        if account not in user_password:
            user_password[account] = password
            self.sock.sendall(struct.pack('!2s2i', b'##', 0, 205))  # 注册成功是205
        else:
            self.sock.sendall(struct.pack('!2s2i', b'##', 0, 402))

    def broadcast_message(self, message):
        for thread in client_threads.values():
            if thread != self:
                thread.sock.sendall(message)

    def prepare_file_receiving(self, data):
        # 文件接收准备逻辑，待实现
        pass

    def parse_data(self, data):
        # account, password = data.split(":")
        # return account, password
        new_data = json.loads(data)
        account = new_data['account']
        password = new_data['password']
        return account, password
    # 可以直接用json.loads()解析json.dumps()转化成str,后面通用

    def logout(self, account):
        if account in curr_user:
            curr_user.remove(account)
            client_threads.pop(account)
            self.sock.sendall(struct.pack('!2s2i', b'##', 0, 205))
        else:
            self.sock.sendall(struct.pack('!2s2i', b'##', 0, 402))


def main():
    # 创建一个socket对象，用于服务器监听和接受客户端连接
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # 绑定服务器监听的地址和端口
    server_socket.bind((Server_Host, Server_Port))

    # 开始监听传入连接，最多可以有5个客户端连接同时等待接入
    server_socket.listen(5)

    # 打印服务器监听的主机名和端口号
    print(f"{Server_Host}: Listening from port {Server_Port}...\n")


    # 无限循环，等待客户端的连接请求
    while True:
        # 接受一个新的客户端连接
        # server_socket.accept()会返回一个客户端套接字和一个客户端地址元组
        client_socket, client_addr = server_socket.accept()

        # 将新的客户端套接字添加到client_list列表中
        client_list.append(client_socket)

        try:
            # 创建一个新的线程实例，传入客户端套接字
            new_thread = ClientThread(client_socket, client_addr)

            # 启动新线程，开始处理来自客户端的通信
            new_thread.start()
        except:
            # 如果线程启动失败，打印错误信息
            print("Error: unable to start thread!")


if __name__ == '__main__':
    main()