#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""add docstring"""

import os
import logging
import hashlib
from functools import partial

def sha1_chunked(filename, chunksize=2**15, bufsize=-1):
    """add docstring"""
    # http://stackoverflow.com/questions/4949162/max-limit-of-bytes-in-method-update-of-hashlib-python-module
    sha1_hash = hashlib.sha1()
    with open(filename, 'rb', bufsize) as _file:
        for chunk in iter(partial(_file.read, chunksize), ''):
            sha1_hash.update(chunk)
    return sha1_hash

class FileInfo:
    """add docstring"""
    def __init__(self, name, path):
        self.name = name
        self.path = path
        
    def get_hash(self):
        """add docstring"""
        try:
            _fullname = os.path.join(self.path, self.name)
            _hash1 = sha1_chunked(_fullname).hexdigest()
            
        except MemoryError, ex:
            logging.error( "error, trying to get hash for file '%s' (%d Mb)",
                           _fullname, 
                           os.path.getsize(_fullname) / 2 **20 )
            logging.error( "error was '%s'", str(ex))
            raise
        return _hash1
        
class FileY:
    """add docstring"""

    def __init__(self, file_info, initial_state=0):
        self.state = initial_state
        self.file_info = file_info
        self.files = None
        
    def add(self, new_file_info):
        """add docstring"""
        if self.state == 0:
            # if this is the first collision then first promote this FileY
            # to a 'folder' for equally sized files
            self.state = 1
            self.files = {self.file_info.get_hash(): FileY(self.file_info, 2)}
            self.file_info = None
            return self.add(new_file_info)
        
        elif self.state == 1:
            _new_hash = new_file_info.get_hash()
            if not _new_hash in self.files:
                self.files[_new_hash] = FileY(new_file_info, 2)
                return 2
            else:
                self.files[_new_hash].add(new_file_info)
                return 2
            
        elif self.state == 2:
            self.state = 3
            self.files = [self.file_info, new_file_info]
            self.file_info = None
            return 3
        
        elif self.state == 3:
            self.files.append(new_file_info)
            return 3
            

class FsDb:
    """add docstring"""

    def __init__(self, import_export_file = None):
        self._ie_file = import_export_file
        self._files = {}

    def register(self, path):
        """add docstring"""
        _totalsize = 0
        for (path, _, files) in os.walk(os.path.abspath(path)):
            for fname in files:
                _fullname = os.path.join(path, fname)
                if os.path.islink(_fullname):
                    continue
                
                _file_info = FileInfo(fname, path)
                
                _filesize = os.path.getsize(_fullname)

                logging.debug( "%s", _fullname )
                
                if not _filesize in self._files:
                    # simple case: file size does not exist yet, so just
                    #              fill the size => file container
                    self._files[_filesize] = FileY(_file_info)
                else:
                    # collision: size is taken, so we have to treat this
                    #            entry as a 'folder' for equally sized files
                    _collision_type = self._files[_filesize].add(_file_info)
                    logging.info("collision (%d): %s", 
                                 _collision_type, _fullname)
                    
                
                #logging.debug("%s", _hash1)
                _totalsize += _filesize
        return _totalsize

def test():
    """add docstring"""
    fsdb = FsDb("fstdb.txt")
    fsdb.register("./example_fs")

if __name__ == "__main__":
    test()
    