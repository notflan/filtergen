import sys
import os
import os.path
import traceback
import json
import socket
import time
import datetime
import re
import threading
import binascii
from cffi import FFI
from socks.transmission import Command
from socks.transmission import SplitBuffer
import select
from subprocess import Popen, PIPE
# command line parsing
import argparse
# check for ssl availability in general
try:
    import ssl
except ImportError:
    print ("error: no ssl support")
# library for performing HTTP(S) requests
#import urllib.request
#import urllib.error
import requests

DEBUG=False

def get_url(request_url):
	opener = urllib.request.build_opener()
	
	response = opener.open(request_url)
	return response.read()
	
def callbackend(filename, args):
	p = Popen(['python', 'gis-scrape.py', filename]+args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
	output, err = p.communicate()
	rc = p.returncode
	return output


def only_okay(only, js):
	if not any(only):
		return True
	for k,v in only.items():
		if (k in js.keys()) and re.match(v, js[k]):
			return True
	return False
def daemon_exit(code):
	sys.stdout.flush()
	sys.stderr.flush()
	os._exit(code)
def parse_daemon_config(fp, en):
	for line in fp:
		line = line.strip()
		if "=" in line and not line[0]=="#":
			k,v = line.split("=", 2)
			en[k.strip()]=v.strip()
	#required field(s)
	if not "socket" in en:
		return False
	
	#default fields
	if not "log" in en:
		en["log"] = "/dev/null"
	if not "errorlog" in en:
		en["errorlog"] = "/dev/null"
	if not "timeout" in en:
		en["timeout"] = "5"
	
	return True
def _fork():
	if DEBUG:
		return 0
	else:
		return os.fork()
def ssleep(sec,check):
	if(sec<5):
		time.sleep(5)
	else:
		x=0
		while x<sec:
			time.sleep(sec/5)
			if(check()):
				return True
			x+=(sec/5)
	return False
def daemon_log(string,error=False):
	print("%s: %s" %(time.strftime("%Y/%m/%d %H:%M:%S"), string), file=(sys.stderr if error else sys.stdout))
def parse_only_config(ty, regex):
	if not ty == None:
		if ty[0]=="file":
			with open(ty[1], "r") as f:
				for line in f:
					if "=" in line:
						k,v = line.split("=", 2)
						parse_only_config(k,v)
		else:
			regex[ty[0]] = ty[1]

class Daemon(threading.Thread):
	def __init__(self, socket, opt):
		self.socket = socket
		self.opt = opt
		self.tstart=time.time()
		self.running= True
		self.accept=False
		self.on=None
		self.trans = Command()
		self.large = SplitBuffer()
		threading.Thread.__init__(self)
	def send(self, string):
		self.trans.send(self.socket,string)
	def recv(self):
		return self.trans.recv(self.socket)
	def info(self):
		ifo=dict()
		ifo["uptime"] = time.time()-self.tstart
		ifo["message"] = "Filtergen daemon version 0.5"
		
		return ifo
	def parse(self, data):
		fv = json.loads(data)
		if not fv:
			daemon_log("Invalid data formatting")
		else:
			if "back" in fv:
				#we need to send data back
				back = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
				back.connect(fv["back"])
				bdata = dict()
				bdata["info"] = self.info();
				if "get" in fv:
					daemon_log("Request for data")
					if self.on!=None:
						bdata["get"] = self.on("get")
				self.large.send(back, json.dumps(bdata).encode("utf-8"))
				back.close()

			if "shutdown" in fv:
				daemon_log("Shutdown recieved")
				self.running=False
				return True	
			return True
	def run(self):
		while self.running:
			if not self.accept:
				time.sleep(1)
				continue
			ready = select.select([self.socket], [], [], int(self.opt["timeout"]))
			if ready[0]:
				data = self.recv()
				if not data:
					daemon_log("Invalid data recieved")
					continue
				else:
					daemon_log("Parsing %s" % data)
					self.parse(data)
					

parser = argparse.ArgumentParser(description='4chan X reverse image md5 filter generator (uses GISS by Erik Rodner)')
parser.add_argument('board', help='4chan board to spider')
parser.add_argument('strings', help='Google image suggestion strings to filter')
parser.add_argument('--verbose', action='store_true', help='Show all messages')
parser.add_argument('--daemon', metavar='CONFIG FILE', help='Start process as daemon', default=None)
parser.add_argument('--debug', action='store_true', help="Set debug flag to true")
parser.add_argument('--fatal', action='store_true', help='Stop parsing images on error')
parser.add_argument('--nokeep', action='store_true', help='Do not cache hashes that did not hit the filter')
parser.add_argument('--force', action='store_true', help='Ignore whitelisted hashes already in output file')
parser.add_argument('--abuse', metavar='COOKIE', help='Google abuse exception cookie', default=None)
parser.add_argument('--only', help='Only run on posts that match regex conditions. Type can be any entry for posts in the 4chan JSON API, if the field does not exist, it is ignored. Or type can be "file" to load config from file. Format for config file: <field>=<regex>', nargs=2, metavar=('TYPE', 'REGEX'), default=None)
parser.add_argument('--always', action='store_true', help='Always add hash to filter (useful with --only), disable image checking')
parser.add_argument('--sleep', help='How long to wait between Google requests (default 10 seconds). If you set this too low Google will start blocking you', default=10, type=int)
parser.add_argument('--baseurl', default="https://i.4cdn.org/%s/", help="Base URL of image (default \'https://i.4cdn.org/%%s/\')")
parser.add_argument('--api', help='Set URL of 4chan JSON API (you should probably not change this)', default='https://api.4chan.org/%s/catalog.json')
parser.add_argument('--output', help='Output file or \"stdout\" to write to stdout. If an MD5 entry is already in the output file, it will not be parsed again', default='stdout')

#parser.add_argument('--full', action='store_true', help='Parse whole board, instead of just thread OPs') #TODO
args = parser.parse_args()

DEBUG = args.debug

daemon = dict()
daemon_sock=None
daemon_server = None

def imageurl(board, post):
	return (args.baseurl+"%s%s") % (board, post['tim'], post['ext'])

def printl(string, error=False):
	if(daemon_server==None):
		print(string, file=(sys.stderr if error else sys.stdout))
	else:
		daemon_log("[L] "+string,error)

def can_break():
	return daemon_server.running == False

if not args.daemon == None:
	okay=False
	error="(unbound)"
	if os.path.isfile(args.daemon):
		with open(args.daemon,"r") as fp:
			okay=parse_daemon_config(fp, daemon)
		if(okay):
			pass
		else:
			if args.verbose:
				error = "Error: config file is not valid"
			else:
				error = "#error starting daemon: config file is in invalid format"
	else:
		if args.verbose:
			error = "Error: config file does not exist"
		else:
			error = "#error starting daemon: config file does not exist"
	if okay:
		pid = _fork()
		if not pid == 0:
			print("Process forked to background: PID %d" % pid)
			sys.exit(0)
		else:
			#daemon stuff
			if not DEBUG:
				sys.stdout = open(daemon["log"], "w")
				sys.stderr = open(daemon["errorlog"], "w")
			
			if os.path.exists(daemon["socket"]):
				os.remove(daemon["socket"])
				if os.path.exists(daemon["socket"]):
					daemon_log("Error removing socket",True)
					daemon_exit(1)
			daemon_sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
			daemon_sock.bind(daemon["socket"])

			daemon_log("Bound to \"%s\"" % daemon["socket"])
			
			daemon_sock.setblocking(0)
			
			
			daemon_server=Daemon(daemon_sock,daemon)
			daemon_server.start()
	else:
		print(error)
		sys.exit(1)

md5s = list()
ignore=list()
regex=dict()
words = args.strings.split()


def addmd5(fp, md5, image, word):
	strin = "#%s (matched %s)\n/%s/" % (image, word, md5)
	md5s.append(md5)
	if fp == None:
		print (strin)
	else:
		print(strin, file=fp)
def noaddmd5(fp, md5):
	strin = "#!%s" % (md5)
	ignore.append(md5)
	if fp == None:
		print (strin)
	else:
		print(strin, file=fp)

if not args.output == "stdout":
	if os.path.isfile(args.output):
		with open(args.output, "r") as f:
			for line in f:
				line = line.strip()
				if line[0] =='#':
					if len(line)>2 and not args.force:
						if line[1]=='!':
							va = line[2:26]
							ignore.append(va)
				elif len(line)<23:
					pass
				else:
					md5s.append(line[1:25])
				


parse_only_config(args.only,regex)

if args.verbose:
	printl("Generating MD5 filters for images matching %s%s" % (("\"%s\" on /%s/" % (args.strings, args.board)) if not args.always else "(all images)", (" and regex %s"%str(regex)) if any(regex) else ""  )) 

def run_round():
	r = requests.get(args.api % args.board)

	if args.verbose:
		printl("Downloaded JSON from 4chan API")
	try:
		pages = r.json()
		image_urls = list()
		backend_args= list()
		post_md5s = dict()
		fp = None
		
		if not args.abuse == None:
			backend_args = ["--abuse", args.abuse]
		
		if args.verbose:
			printl("Parsed json successfully")
		for page in pages:
			for thread in page['threads']: 
				if("ext" in thread): #ignore no file posts
					if (thread['md5'] not in md5s) and (thread['md5'] not in ignore):
						if only_okay(regex, thread):
							rurl = imageurl(args.board, thread)
							image_urls.append(rurl)
							post_md5s[rurl] = thread['md5']
						elif args.verbose:
							printl("Ignoring post %d: Doesn't satisfy conditions" % thread['no']) #TOO verbose?
						
					elif args.verbose:
						printl("Ignoring post no %d: Already cached" % thread['no'])
				elif args.verbose:
					printl("Ignoring post no. %d: No image" % thread['no'])
				
		#subprocess.call(['python', "gis-scrape.py"] + image_urls)
		if not args.output == "stdout":
			if os.path.isfile(args.output):
				fp = open(args.output, "a")
			else:
				fp = open(args.output, "w")
				print("#filtergen filter entries", file=fp)
		try: 
			for url in image_urls: 
				try: 
					if args.verbose:
						printl("Working on image %s" % url)
					if args.always:
						if args.verbose:
							printl("Force adding %s" % url)
						addmd5(fp, post_md5s[url], url, str(regex))
					else:
						raw = callbackend(url, backend_args)
						
						js = json.loads(raw)
						bestguess = js[url]['bestguess']
						if args.verbose:
							printl("\tgot bestguess \"%s\"" % bestguess)
						
						hit=False
						for word in words:
							if word in bestguess:
								if args.verbose:
									printl("\tmatch, adding to list")
								addmd5(fp, post_md5s[url], url, word)
								hit = True
								break
						if (not args.nokeep) and not hit:
							noaddmd5(fp, post_md5s[url])
				except (KeyboardInterrupt):
					if args.verbose:
						printl("Interrupt detected")
						break
				except:
					printl("#error looking up image %s" % url)
					if args.verbose:
						traceback.print_exc()
					if args.fatal:
						return False
				if not daemon_server:
					time.sleep(args.sleep)					
				else:
					ssleep(args.sleep, can_break)
					if daemon_server.running==False:
						break;
				
		except (KeyboardInterrupt):
			if args.verbose:
				print("Interrupt detected")
		except:
			print("#error calling backend")
			if args.verbose:
				traceback.print_exc()
			if daemon_server!=None:
				ssleep(args.sleep, can_break)
		
		if not fp == None:
			fp.close()		
		
	except:
		print("#Error parsing JSON")
		if args.verbose:
			traceback.print_exc()
		pass
	return True

def _on_get():
	gd = dict()
	gd["matched"] = md5s
	gd["ignored"] = ignore
	return gd

def d_on(string):
	if string == "get":
		return _on_get()

if(daemon_server==None):
	run_round()
else:
	daemon_server.on = d_on 
	daemon_server.accept=True
	
	while(daemon_server.running):
		if not run_round():
			daemon_server.running=False
		#time.sleep(10)
		#daemon_server.running=False
	daemon_server.join()
	daemon_log("Closing socket end exiting")
	daemon_sock.close()
	os.remove(daemon["socket"])
	daemon_exit(0)
