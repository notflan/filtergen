import os
#import json
import socket
import sys
import time
from cffi import FFI
import binascii

class SplitBuffer(object):
	def __init__(self):
		self.ffi = FFI()
		self.buffersize = 4096
		self.ffi.cdef("""
			typedef struct {
				unsigned char data[%d];
			} buffer_t;
			typedef struct {
				unsigned int crc32;
				int size;
			} bufsize_t;
		""" % self.buffersize)
	def _sendsize(self, socket, size, crc):
		i = self.ffi.new("bufsize_t*")
		i.size = size
		i.crc32 = crc
		socket.send(self.ffi.buffer(i))
	def _recvsize(self, socket):
		data = socket.recv(self.ffi.sizeof("bufsize_t"))
		if not data or len(data)!=self.ffi.sizeof("bufsize_t"):
			print("Could not read data size", file=sys.stderr)
			return None
		else:
			buf = self.ffi.from_buffer(data)
			if self.ffi.sizeof(buf) != self.ffi.sizeof("bufsize_t"):
				print("Could not deserialise data size", file=sys.stderr)
				return None
			else:
				i = self.ffi.cast("bufsize_t*", buf)
				return (i.size,i.crc32)

	def send(self, socket, data):
		datasize = len(data)		
		self._sendsize(socket, datasize, binascii.crc32(data))

		bi = self.ffi.new("buffer_t*")
		i =0
		while i<datasize:
			buf = data[i:min(datasize, i+self.buffersize)]
			i+=len(buf)

			tb = self.ffi.from_buffer(buf)
			self.ffi.memmove(bi.data, tb, self.ffi.sizeof(tb))
			socket.send(self.ffi.buffer(bi))
	def recv(self, socket):
		datasize,checksum = self._recvsize(socket)
		data = bytearray()		

		bi = self.ffi.new("buffer_t*")
		i=0
		while i<datasize:
			raw = socket.recv(self.ffi.sizeof("buffer_t"))
			if not raw or len(raw)!=self.ffi.sizeof("buffer_t"):
				print("Could not read data chunk (at %d)"%i, file=sys.stderr)
				return None
			else:
				i+=len(raw)
				ch = self.ffi.from_buffer(raw)
				bt = self.ffi.cast("buffer_t*", ch)
				ful = self.ffi.buffer(bt.data)
				data.extend(ful)
				print("%s" % self.ffi.string(bt.data))
		realdata= data[:datasize]
		if(checksum==binascii.crc32(realdata)):
			return realdata
		else:
			print("Checksum mismatch (expected %x, got %x)" %(checksum, binascii.crc32(realdata)))
			return None
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
