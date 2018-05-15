import sys
import os
import os.path
import traceback
import json
import time
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

def get_url(request_url):
	opener = urllib.request.build_opener()
	response = opener.open(request_url)
	return response.read()
	
def imageurl(board, post):
	return "https://i.4cdn.org/%s/%s%s" % (board, post['tim'], post['ext'])
	
def callbackend(filename):
	p = Popen(['python', 'gis-scrape.py', filename], stdin=PIPE, stdout=PIPE, stderr=PIPE)
	output, err = p.communicate()
	rc = p.returncode
	return output

def addmd5(fp, md5, image, word):
	strin = "/%s/ #%s (matched %s)" % (md5, image, word)
	if fp == None:
		print (strin)
	else:
		print(strin, file=fp)
def noaddmd5(fp, md5):
	strin = "#!%s" % (md5)
	if fp == None:
		print (strin)
	else:
		print(strin, file=fp)

parser = argparse.ArgumentParser(description='4chan X reverse image md5 filter generator (uses GISS by Erik Rodner)')
parser.add_argument('board', help='4chan board to spider')
parser.add_argument('strings', help='Google image suggestion strings to filter')
parser.add_argument('--verbose', action='store_true', help='Show all messages')
parser.add_argument('--fatal', action='store_true', help='Stop parsing images on error')
parser.add_argument('--nokeep', action='store_true', help='Do not cache hashes that did not hit the filter')
parser.add_argument('--force', action='store_true', help='Ignore whitelisted hashes already in output file')
parser.add_argument('--sleep', help='How long to wait between Google requests (default 10 seconds). If you set this too low Google will start blocking you.', default=10, type=int)
parser.add_argument('--api', help='Set URL of 4chan JSON API (you should probably not change this)', default='https://api.4chan.org/%s/catalog.json')
parser.add_argument('--output', help='Output file or \"stdout\" to write to stdout. If an MD5 entry is already in the output file, it will not be parsed again', default='stdout')

#parser.add_argument('--full', action='store_true', help='Parse whole board, instead of just thread OPs') #TODO
args = parser.parse_args()

if args.verbose:
	print("Generating MD5 filters for images matching \"%s\" on /%s/" % (args.strings, args.board)) 

md5s = list()
ignore=list()
words = args.strings.split()

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
				

r = requests.get(args.api % args.board)

if args.verbose:
	print("Downloaded JSON from 4chan API")
try:
	pages = r.json()
	image_urls = list()
	post_md5s = dict()
	fp = None
	if args.verbose:
		print("Parsed json successfully")
	for page in pages:
		for thread in page['threads']: 
			if("ext" in thread): #ignore no file posts
				if (thread['md5'] not in md5s) and (thread['md5'] not in ignore):
					rurl = imageurl(args.board, thread)
					image_urls.append(rurl)
					post_md5s[rurl] = thread['md5']
					
				elif args.verbose:
					print("Ignoring post no %d: Already cached" % thread['no'])
			elif args.verbose:
				print("Ignoring post no. %d: No image" % thread['no'])
			
	#subprocess.call(['python', "gis-scrape.py"] + image_urls)
	if not args.output == "stdout":
		if os.path.isfile(args.output):
			fp = open(args.output, "a")
		else:
			fp = open(args.output, "w")
			print("#filtergen filter entries", file=fp)
		
	for url in image_urls: 
		try: 
			if args.verbose:
				print("Working on image %s" % url)
			raw = callbackend(url)
			print("got %s from backend" % raw)
			js = json.loads(raw)
			bestguess = js[url]['bestguess']
			if args.verbose:
				print("\tgot bestguess \"%s\"" % bestguess)
			hit = False
			
			for word in words:
				if word in bestguess:
					md5s.append(post_md5s[url])
					if args.verbose:
						print("\tmatch, adding to list")
					addmd5(fp, post_md5s[url], url, word)
					hit = True
					break
			if (not args.nokeep) and not hit:
				noaddmd5(fp, post_md5s[url])
		except (KeyboardInterrupt):
			if args.verbose:
				print("Interrupt detected")
				break
		except:
			print("#error looking up image %s" % url)
			if args.verbose:
				traceback.print_exc()
			if args.fatal:
				break
		time.sleep(args.sleep)
	if not fp == None:
		fp.close()		
	
except:
	print("#Error parsing JSON")
	if args.verbose:
		traceback.print_exc()
	pass
