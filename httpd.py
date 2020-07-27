# coding='UTF-8'

import socket
import logging
import select
import multiprocessing
import datetime
import os
from optparse import OptionParser

# Respond to GET with status code in {200,403,404}
# Respond to HEAD with status code in {200,404}
# Respond to all other request methods with status code 405
# Directory index file name index.html
# Respond to requests for /<file>.html with the contents of DOCUMENT_ROOT/<file>.html
# Requests for /<directory>/ should be interpreted as requests for DOCUMENT_ROOT/<directory>/index.html
# Respond with the following header fields for all requests:
# Server
# Date
# Connection
# Respond with the following additional header fields for all 200 responses to GET and HEAD requests:
# Content-Length
# Content-Type
# Respond with correct Content-Type for .html, .css, js, jpg, .jpeg, .png, .gif, .swf
# Respond to percent-encoding URLs
# No security vulnerabilities!


HOST,PORT = '127.0.0.1',8094 # host -> socket.gethostname() use to set machine IP  
METHODS = ['GET', 'HEAD']
CODES = [200, 403, 404, 405]
DOCUMENT_ROOT = '/'
CONTENT_TYPES = {'html':'text/html','css':'text/css','js':'application/javascript','jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','gif':'image/gif','swf':'	application/x-shockwave-flash'}
CODES_MESSGAGE = {200:'OK', 403:'Forbidden',404:'Not Found',405:'Method Not Allowed'}
URL_SPEC_CHAR = {':':'%3A', '/':'%2F', '?':'%3F', '#':'%23', '[':'%5B',']':'%5D','@':'%40','!':'%21','$':'%24',	'&':'%26',"'":'%27','(':'%28',')':'%29','*':'%2A','+':'%2B',',':'%2C',';':'%3B','=':'%3D','%':'%25',' ':'%20'}
VERSION = 'HTTP/1.1'
CONNECTIONS_LIMIT = 100
EOL1 = b'\n\n'
EOL2 = b'\n\r\n'

def generate_full_path(path, document_root):
    if(path == '/'):
        path = 'index.html'
    else:
        path = path[1:]
    full_path = os.curdir + document_root + path
    print("full path is: {}".format(full_path))
    return full_path

def generate_headers(file_type, code, content_lenght):
    # version _ code _ message
    first_line = '{} {} {}\r\n'.format(VERSION, code, CODES_MESSGAGE[code])
    headers = first_line.encode('UTF-8')
    # Server:
    headers += 'Server: python httpd server 0.1'.encode('UTF-8')
    # Date: 
    time_now = datetime.datetime.now()
    date = 'Date: {}\r\n'.format(time_now.strftime('%a, %d %b %Y %H:%M:%S %Z'))
    headers += date.encode('UTF-8')
    # Connection:
    if code == 200: 
        # Content-Type:
        content_type = 'Content-Type: {}\r\n'.format(CONTENT_TYPES[file_type]) 
        headers += content_type.encode('UTF-8')
        # Content-Length:
        _content_lenght = 'Content-Length: {}\r\n'.format(content_lenght)
        headers += _content_lenght.encode('UTF-8')
    # end line
    headers += b'\r\n'
    return headers

def generate_content(path):
    try:
        file = open(path,'rb') # open file , r => read , b => byte format
        content = file.read()
        # print(content)
        file.close()
        file_name = path.split('/')[-1]
        file_type = file_name.split('.')[1]
    except:
        logging.info("Error while reading file: {}".format(path))
        content = 'Error whie reading file'.encode('UTF-8')
    return file_type, content

def generate_response(*args):
    if len(args) == 1:
        response = generate_headers('html', args[0], 0)
        print(response)
    else:
        content_type, content_data = generate_content(args[1])
        response = generate_headers(content_type, 200, len(content_data))
        print(response)
        response += content_data
    return response

def processing(request):
    # парсинг
    _request = request.split('\r\n')
    first_line = _request[0].split(' ')
    method = first_line[0]
    path = first_line[1].split('?')[0]
    # protocol = first_line[2]

    if method not in METHODS:
        return generate_response(405)
    
    full_path = generate_full_path(path, DOCUMENT_ROOT)
    if not os.path.isfile(full_path):
        return generate_response(404)

    # file_ext, ecoded_content = generate_content()

    if not full_path.split('.')[-1] in [k for k in CONTENT_TYPES.keys()]:
        return generate_response(403)
  
    return generate_response(200, full_path)

def start_server(address, port, document_root, workers_number):

    my_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    my_socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    my_socket.bind((address,port))
    my_socket.listen(workers_number)
    my_socket.setblocking(0)

    epoll = select.epoll()
    epoll.register(my_socket.fileno(), select.EPOLLIN)

    try:
        connections = {}; requests = {}; responses = {}
        while True:
            events = epoll.poll(CONNECTIONS_LIMIT)
            for fileno, event in events:
                if fileno==my_socket.fileno():
                    connection, address = my_socket.accept()
                    connection.setblocking(0)
                    epoll.register(connection.fileno(), select.EPOLLIN)
                    connections[connection.fileno()] = connection
                    requests[connection.fileno()]=b''
                    responses[connection.fileno()] = b''
                elif event & select.EPOLLIN:
                    requests[fileno] +=connections[fileno].recv(1024)
                    if EOL1 in requests[fileno] or EOL2 in requests[fileno]:
                        epoll.modify(fileno, select.EPOLLOUT)
                        # print('-'*40 + '\n' + requests[fileno].decode()[:-2])
                elif event & select.EPOLLOUT:
                    request = requests[fileno]
                    responses[fileno] = processing(request.decode('UTF-8'))
                    # print("--------------> {}".format(request))
                    # responses[fileno]=response
                    byteswritten = connections[fileno].send(responses[fileno])
                    # byteswritten = connections[fileno].send(response)
                    responses[fileno] = responses[fileno][byteswritten:]
                    if len(responses[fileno]) ==  0:
                        epoll.modify(fileno,  0)
                        connections[fileno].shutdown(socket.SHUT_RDWR)
                elif event & select.EPOLLHUP:
                    epoll.unregister(fileno)
                    connections[fileno].close()
                    del connections[fileno]
    finally:
        epoll.unregister(my_socket.fileno())
        epoll.close()
        my_socket.close()

if __name__ == "__main__":
    op = OptionParser()
    op.add_option("-w", "--workers_number", action="store", type=int, default=100)
    op.add_option("-l", "--log", action="store", default=None)
    op.add_option("-r", "--document_root", action="store", type=str, default=DOCUMENT_ROOT)
    op.add_option("-p", "--port", action="store", type=int, default=PORT)
    op.add_option("-a", "--address", action="store", type=str, default=HOST)
    (opts, args) = op.parse_args()
    logging.basicConfig(filename=opts.log
    ,
                        level=logging.INFO,
                        format='[%(asctime)s] %(levelname).1s %(message)s',
                        datefmt='%Y.%m.%d %H:%M:%S')                  
    logging.info("Starting server at %s" % opts.port)
    try:
        start_server(opts.address, opts.port, opts.document_root, opts.workers_number)
    except KeyboardInterrupt:
        pass
    # server_close()
