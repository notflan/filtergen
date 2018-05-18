import os
import json
import socket
import sys
import time
import argparse
from socks.transmission import Command
from cffi import FFI
import binascii

parser = argparse.ArgumentParser(description='filtergen daemon controller')
parser.add_argument('socket', help="Unix socket to write to")
parser.add_argument("--shutdown", action='store_true', help="Tell daemon to shut down")
args = parser.parse_args()

trans = Command()
coms = dict()

if args.shutdown:
	coms["shutdown"] = True

if os.path.exists(args.socket):
	sock = socket.socket( socket.AF_UNIX, socket.SOCK_DGRAM )
	sock.connect(args.socket)
	value = json.dumps(coms)
	print("Writing %s" % value)
	trans.send(sock, value)
	sock.close()
else:
	print("Socket does not exist",file=sys.stderr)
