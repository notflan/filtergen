import os
import tempfile
import json
import socket
import sys
import datetime
import time
import argparse
from socks.transmission import Command
from socks.transmission import SplitBuffer
from cffi import FFI
import binascii


parser = argparse.ArgumentParser(description='filtergen daemon controller')
parser.add_argument('socket', help="Unix socket to write to")
parser.add_argument('--raw', action='store_true', help= "Print raw output only")
parser.add_argument("--shutdown", action='store_true', help="Tell daemon to shut down")
parser.add_argument("--quiet", action='store_true', help="Do not display daemon information")
parser.add_argument("--get", metavar="FILENAME", help="Get filter data, if FILENAME is \"stdout\" write to stdout", default=None)
args = parser.parse_args()

trans = Command()
large=  SplitBuffer()
coms = dict()
getfn = None

def write_get_str(ar, fl):
	for line in ar["matched"]:
		print(line, file=fl)
	for line in ar["ignored"]:
		print("#!"+line, file=fl)

def parse_resp(js):
	if args.raw:
		print(js)
	else:
		resp = json.loads(js)
		if not args.quiet and "info" in resp:
			ifo = resp["info"]
			print("%s\r\n\tUptime: %s" % (ifo["message"], str(datetime.timedelta(seconds=ifo["uptime"]))))
		if "get" in resp:
			vl = resp["get"]
			if getfn!=None:
				with open(getfn, "w") as f:
					write_get_str(resp["get"], f)
			else:
				write_get_str(resp["get"], sys.stdout)

cli_sock =  tempfile._get_default_tempdir()+"/"+next(tempfile._get_candidate_names())

if args.shutdown:
	coms["shutdown"] = True

if args.get!=None:
	coms["back"] = cli_sock
	if args.get!="stdout":
		getfn = args.get
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
