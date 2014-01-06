"""
Media Renamer v0.1
by Matt Donahoe


This script helps you rename your images by showing you them one by one
(Kinda like Google Image labeler, except you are the only one doing it...)

How it works:
It recursively scans the given directory for unnamed images/movies.
(IMG_2345.jpg DSC13435.JPG, SANY0102.MP4 etc)
Then it starts a local server on port 50000 which you interact
with through a web browser

How to use it:
Run the script inside a directory that contain a bunch of photos or movies
	python picnamer.py
Then go to http://localhost:50000/ and start entering tags for images

The file will be renamed according to the tags.
Duplicate names will have numbers attached
"""



import string,cgi
from os import sep, path, rename
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from urlparse import urlparse
import sys
import re
from random import shuffle,random


valid_chars = string.lowercase+string.uppercase+string.digits+'-'+'_'
def cleanfilename(name):
	n=''
	name = name.replace('%20','-').replace(' ','-')
	for c in name:
		if c in valid_chars: n+=c
	return n

def prepnextfile():
	if files[0].endswith('MP4'): return '<EMBED WIDTH=500 HEIGHT=350 SCALE="TOFIT" SRC="movie%s.mp4" AUTOPLAY="true" CONTROLLER="false" PLUGINSPAGE="http://www.apple.com/quicktime/download/"></EMBED>'%(str(random()))
	return '<img src="image.jpg" width=500></img>'

def buildfile():
	return """<html><body onload="document.forms[0].n.focus();"><h3>%s</h3>%s<br><form method="POST"><input type="text" name="n" autocomplete="off" size="45"></input><input type="submit"></input></form>"""%(files[0],media)

class MyHandler(BaseHTTPRequestHandler):

	def do_GET(self):
		try:

			parsed = urlparse(self.path)
			name = parsed[2][1:] #get the relative url, drop the first /
			print name
			if name=="": 
				thedata = buildfile()
				content_type = "text/html"
			
			elif name.endswith('jpg'):
				thedata = file(files[0]).read()
				content_type = 'image/jpeg'
			
			elif name.endswith('mp4'):
				thedata = file(files[0]).read()
				content_type = 'application/mp4'
			else: raise IOError
			
			self.send_response(200)
			self.send_header('Content-type', content_type)
			self.send_header('Cache-Control', "public,max-age:0")
			self.end_headers()
			self.wfile.write(thedata)
			
		
		except IOError:
			self.send_error(404,'File Not Found: %s' % self.path)
	
	def do_POST(self):
		global media
		try:
			form = cgi.FieldStorage(
				fp=self.rfile,
				headers=self.headers,
				environ={
					'REQUEST_METHOD':'POST',
					'CONTENT_TYPE':self.headers['Content-Type'],
				}
			)
			
			#rename the file uniquely
			n = cleanfilename(form['n'].value)
			if n=='': self.do_GET()
			m = 0
			start = path.split(files[0])[0] + sep + n
			ext = path.splitext(files[0])[1].lower()
			newname = start + ext
			
			while path.exists(newname):
				m+=1
				newname = start+str(m)+ext
			
			rename(files[0], newname)
			
			
			#remove the newly renamed image from our list
			files.pop(0)
			if len(files)==0:
				print "no more images"
				raise KeyboardInterrupt #need a better way to quit
			media = prepnextfile()
			#reload the page
			self.do_GET()

		except:
			print sys.exc_info()


##grab the directory as an argument, if availble
try:
	directory = sys.argv[1]
except IndexError:
	directory = "."

##find unnamed images
pattern = re.compile('(IMG|DSC|SANY).*\.(JPG|jpg|MP4)$')
files = []
def media_finder(r,d,fs):
	files.extend([d+sep+f for f in fs if r.match(f)])
path.walk(directory,media_finder, pattern)


##randomly shuffle the images (makes labeling more fun)
shuffle(files)
if len(files):
	try:
		server = HTTPServer(('', 50000), MyHandler)
		print 'started httpserver...'
		media = prepnextfile()
		server.serve_forever()
	except KeyboardInterrupt:
		print '^C received, shutting down server'
		server.socket.close()
		print "%i media files remain"%(len(files))
		
else: print "no files"
			

