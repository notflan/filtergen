import os
#import json
import socket
import sys
import time
from cffi import FFI
import binascii

class Command(object):
	def __init__(self):
		self.ffi = FFI()
		self.buffersize = 2048
		self.ffi.cdef("""
			typedef struct {
				int size;
				unsigned int crc32;
				char string[%d];
			} commandstr_t;
		""" % self.buffersize)
	def send(self, socket, string):
		strb = string.encode("ascii")
		cmdstr = self.ffi.new("commandstr_t*")
		cmdstr.size = len(strb)
		cmdstr.crc32 = binascii.crc32(strb)
		tb = self.ffi.from_buffer(strb)
		self.ffi.memmove(cmdstr.string, tb, min(self.ffi.sizeof(tb), self.buffersize))
		socket.send(self.ffi.buffer(cmdstr))
	def recv(self, socket):
		sz = self.ffi.sizeof("commandstr_t")
		data = socket.recv(sz)
		if not data or len(data) != sz:
			print("Recieved wrong number of bytes (expected %d, got %d)" %(sz, len(data)), file=sys.stderr)
			return None
		else:
			buf = self.ffi.from_buffer(data)
			if(self.ffi.sizeof(buf)!=sz):
				print("Deserialised buffer is of incorrect size (expected %d, got %d)" %(sz,self.ffi.sizeof(buf)), file=sys.stderr)
				return None
			else:
				cmdstr = self.ffi.cast("commandstr_t*", buf)
				readstr = self.ffi.string(cmdstr.string)
				crcc = binascii.crc32(readstr)
				if crcc == cmdstr.crc32:
					return readstr
				else:
					print("Checksum mismatch", file=sys.stderr)
					return None
