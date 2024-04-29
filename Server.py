import socket
import threading

Server_Host = socket.gethostname()
Server_Port = 8000

user_password = {}
curr_user = set()


class ClientThread(threading.Thread):
    def __init__(self, client_socket):
        threading.Thread.__init__(self)
        self.sock = client_socket

    def run(self):
        a = self.sock.recv(1024).decode()
        print(f"{a} add into the chatroom!\n")
        self.sock.send("welcome!\n".encode())
        while True:
            try:
                name = self.sock.recv(1024).decode()
                print(name)
            except:
                print("error\n")

    def sign_up(self, account, password):  # 注册
        if user_password.get(account, -1) == -1:
            user_password[account] = password
            self.sock.send("success".encode())
        else:
            self.sock.send("fail")

    def log_in(self, account, password):  # 登录
        if user_password.get(account, -1) == -1:
            self.sock.send("not".encode())
        elif user_password[account] != password:
            self.sock.send("fail".encode())
        else:
            if account in curr_user:
                self.sock.send("logged".encode())
            else:
                curr_user.add(account)
                self.sock.send("success".encode())

    def log_out(self, account):  # 登出
        curr_user.remove(account)
        self.sock.send("success".encode())


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((Server_Host, Server_Port))
    server_socket.listen(5)
    print(f"{Server_Host}: Listening from port {Server_Port}...\n")
    client_list = []
    while True:
        client_socket, client_addr = server_socket.accept()
        client_list.append(client_socket)
        try:
            new_thread = ClientThread(client_socket)
            new_thread.start()
        except:
            print("Error: unable to start thread!")


if __name__ == '__main__':
    main()
