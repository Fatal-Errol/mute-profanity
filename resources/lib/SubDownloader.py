#!/usr/bin/env python

import struct
import os
import sys
import traceback
import io
from threading import Thread
import time
import xbmcgui

from zipfile import *
from xmlrpc.client import ServerProxy
from urllib.request import Request, urlopen

text_characters = "".join(list(map(chr, list(range(32, 127)))) + list("\n\r\t\b"))
_null_trans = str.maketrans("", "")

server = ServerProxy("http://api.opensubtitles.org/xml-rpc")
token = ""

class ThreadWithReturnValue(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None
    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args,
                                                **self._kwargs)
    def join(self, timeout=None):
        Thread.join(self, timeout)
        return self._return


def FindSubtitles(videoname, lang):
    dialog = xbmcgui.Dialog()

    print("Contacting www.opensubtitles.org (" + videoname + ")", file=sys.stderr)
    filename = os.path.join(os.path.dirname(videoname), os.path.splitext(os.path.basename(videoname))[0] + ".srt")
    print(filename)

    langs = lang.split(",")

    data = GetSubtitles(videoname);
    if data:
        for l in langs:
            for item in data:
                if item['SubLanguageID'] == l:
                    print("Found", item['LanguageName'], "subtitle ...", file=sys.stderr)
                    fullFile = os.path.join(os.path.dirname(videoname), item['SubFileName'])
                    zipname = Download(item['ZipDownloadLink'], fullFile)
                    print("Extracting subtitle ", filename, file=sys.stderr)

                    Unzip(zipname, filename, item['SubFileName'].replace('&', '.'))
                    os.remove(zipname)
                    return filename
    print("No Subtitles found", file=sys.stderr)
    return None

def GetSubtitles(moviepath):
    #print >> sys.stderr, server.LogIn("","","","SubIt")['status']
    try:
        session = server.LogIn("", "", "", "SubIt")
    except Exception:
        # Retry once, it could be a momentary overloaded server?
        time.sleep(3)
        try:
            # Connection to opensubtitles.org server
            session = server.LogIn("", "", "", "SubIt")
        except Exception:
            # Failed connection attempts?
            dialog.ok("Connection error!", "Unable to reach opensubtitles.org servers!\n\nPlease check:\n- Your Internet connection status\n- www.opensubtitles.org availability\n- Your downloads limit (200 subtitles per 24h)\nThe subtitles search and download service is powered by opensubtitles.org. Be sure to donate if you appreciate the service provided!")
            sys.exit(1)

    # Connection refused?
    if session['status'] != '200 OK':
        dialog.ok("Connection error!", "Opensubtitles.org servers refused the connection: " + session['status'] + ".\n\nPlease check:\n- Your Internet connection status\n- www.opensubtitles.org availability\n- Your 200 downloads per 24h limit")
        sys.exit(1)

    token = session['token']

    moviebytesize = os.path.getsize(moviepath)
    hash = Compute(moviepath)
    movieInfo = {'sublanguageid': 'eng', 'moviehash': hash, 'moviebytesize': str(moviebytesize)}
    movies = [movieInfo]
    data = server.SearchSubtitles(token, movies)['data']

    # if the hash fails, try searching by title of movie (assuming file is named after its title)
    if not data:
        basename = os.path.basename(moviepath)
        name = os.path.splitext(basename)[0]
        print("Could not find by hash ...", file=sys.stderr)
        print("Searching by name: \"" + name + "\"", file=sys.stderr)
        movieInfo = {'sublanguageid': 'eng', 'query': name}
        movies = [movieInfo]
        data = server.SearchSubtitles(token, movies)['data']

    server.LogOut()
    return data


def Compute(name):
    try:
        longlongformat = 'q'  # long long
        bytesize = struct.calcsize(longlongformat)
        f = open(name, "rb")
        filesize = os.path.getsize(name)
        hash = filesize

        if filesize < 65536 * 2:
            return "SizeError"

        for x in range(65536 // bytesize):
            buffer = f.read(bytesize)
            (l_value,) = struct.unpack(longlongformat, buffer)
            hash += l_value
            hash = hash & 0xFFFFFFFFFFFFFFFF #to remain as 64bit number

        f.seek(max(0, filesize - 65536), 0)
        for x in range(65536 // bytesize):
            buffer = f.read(bytesize)
            (l_value,) = struct.unpack(longlongformat, buffer)
            hash += l_value
            hash = hash & 0xFFFFFFFFFFFFFFFF

        f.close()
        returnedhash = "%016x" % hash
        return returnedhash

    except IOError:
        return "IOError"


def Unzip(zipname, unzipname, subname=None):
    z = ZipFile(zipname)
    if not subname:
        for filename in z.namelist():
            if os.path.splitext(os.path.basename(filename))[1] == ".srt":
                outfile = open(unzipname, "wb")
                outfile.write(z.read(filename))
                outfile.close()
                break
    else:
        #Subtitle file specified, just use that one
        outfile = open(unzipname, "wb")
        outfile.write(z.read(subname))
        outfile.close()


def istext(s):
    if "\0" in s:
        return 0

    if not s:  # Empty files are considered text
        return 1

    # Get the non-text characters (maps a character to itself then
    # use the 'remove' option to get rid of the text characters.)
    t = s.translate(_null_trans, text_characters)

    # If more than 30% non-text characters, then
    # this is considered a binary file
    return float(len(t)) / len(s) <= 0.30


def Download(url, filename):
    req = Request(url)
    f = urlopen(req)
    print("downloading " + url, file=sys.stderr)
    print("save to " + filename + ".zip", file=sys.stderr)
    # Open our local file for writing
    local_file = open(filename + ".zip", "w" + "b")
    #Write to our local file
    local_file.write(f.read())
    local_file.close()
    print("file " + filename + ".zip created", file=sys.stderr)
    return filename + ".zip"


def StartThreaded(videoname, lang):
    t = ThreadWithReturnValue(target=FindSubtitles, args=(videoname, lang))
    t.setDaemon(True)
    t.start()
    return t

def main():
    args = sys.argv
    if len(args) < 3:
        print("Usage: file language")
        sys.exit(1)

    srtFile = None
    try:
        srtFile = FindSubtitles(args[1], args[2])
    except:
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(3)

    if not srtFile:
        sys.exit(2)

    print(srtFile)
    sys.exit(0)


if __name__ == '__main__':
    main()
