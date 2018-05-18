import os
import tempfile
import json
import socket
import sys
import time
import argparse
from socks.transmission import Command
from socks.transmission import SplitBuffer
from cffi import FFI
import binascii

def parse_resp(resp):
	print("Read resp %s" % resp)

parser = argparse.ArgumentParser(description='filtergen daemon controller')
parser.add_argument('socket', help="Unix socket to write to")
parser.add_argument("--shutdown", action='store_true', help="Tell daemon to shut down")
parser.add_argument("--get", action='store_true', help="Get filter data")
args = parser.parse_args()

trans = Command()
large=  SplitBuffer()
coms = dict()

cli_sock =  tempfile._get_default_tempdir()+"/"+next(tempfile._get_candidate_names())

if args.shutdown:
	coms["shutdown"] = True

if args.get:
	coms["back"] = cli_sock
	coms["get"] = True

if os.path.exists(args.socket):
	sock = socket.socket( socket.AF_UNIX, socket.SOCK_DGRAM )
	readsock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
	readsock.bind(cli_sock)

	sock.connect(args.socket)
	value = json.dumps(coms)
	#print("Writing %s" % value)
	trans.send(sock, value)

	if "back" in coms:
		resp=large.recv(readsock)
		parse_resp(resp.decode("utf-8"))

	readsock.close()
	sock.close()
else:
	print("Socket does not exist",file=sys.stderr)

if os.path.exists(cli_sock):
	os.remove(cli_sock)
