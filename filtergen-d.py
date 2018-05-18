import os
import json
import socket
import time
import argparse

parser = argparse.ArgumentParser(description='filtergen daemon controller')
parser.add_argument('socket', help="Unix socket to write to")
parser.add_argument("--shutdown", action='store_true', help="Tell daemon to shut down")
args = parser.parse_args()

def send(socket, string):
	socket.send(string.encode("ascii"))
def recv(socket):
	#buf=''
	#while len(buf)<1 or buf[-1] != "\0":
	#	buf+=socket.recv(1)
		
	#num = int(buf[:-1])
	#if(num>0):
	#	return socket.recv(num)
	#else:
	#	return None
	return socket.recv(1024).decode("ascii")

coms = dict()

if args.shutdown:
	coms["shutdown"] = True

if os.path.exists(args.socket):
	sock = socket.socket( socket.AF_UNIX, socket.SOCK_DGRAM )
	sock.connect(args.socket)
	value = json.dumps(coms)
	print("Writing %s" % value)
	send(sock, value)
	sock.close()
else:
	print("Socket does not exist",file=stderr)
