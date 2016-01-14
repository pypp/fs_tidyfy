#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import time
import json
import hashlib
import functools
import subprocess


def sha1_external(filename):
    ''' fast with large files '''
    output = subprocess.Popen(["sha1sum", filename], stdout=subprocess.PIPE).communicate()[0].decode()
    # todo: check plausibility (length, "permission denied", etc)
    return output.split(' ')[0]


def sha1_internal(filename, chunksize=2**15, bufsize=-1):
    ''' fast with small files '''
    # max-limit-of-bytes-in-method-update-of-hashlib-python-module
    # http://stackoverflow.com/questions/4949162
    sha1_hash = hashlib.sha1()
    with open(filename, 'rb', bufsize) as _file:
        for chunk in iter(functools.partial(_file.read, chunksize), b''):
            sha1_hash.update(chunk)
    return sha1_hash.hexdigest()


def fast_sha1(filename, size):
    if size < 50000:
        return sha1_internal(filename)
    else:
        return sha1_external(filename)

        
class indexer:

    class name_component_store:
        def __init__(self):
            self._idx_to_word = {}
            self._word_to_idx = {}
            self._size = 0

        def __len__(self):
            return self._size

        def get_index(self, word):
            assert word != ''
            if word in self._word_to_idx:
                return self._word_to_idx[word]
            _index = self._size
            self._size += 1
            self._word_to_idx[word] = _index
            self._idx_to_word[_index] = word
            return _index

        def __getitem__(self, index):
            return self._idx_to_word[index]

        def save(self, filename):
            json.dump(self._word_to_idx, open(filename, 'w'))

        def load(self, filename):
            _idx2word = {}
            try:
                _word2idx = json.load(open(filename))
            except:
                # file does not exist - just exit
                return
            for word, idx in _word2idx.items():
                _idx2word[idx] = word
            self._idx_to_word, self._word_to_idx, self._size = (
                _idx2word, _word2idx, len(_idx2word))

        def __eq__(self, other):
            return (self._size == other._size and
                    self._idx_to_word == other._idx_to_word and
                    self._word_to_idx == other._word_to_idx)

    def __init__(self):
        # expensive - do it only once
        self._file_dir = os.path.expanduser('~/.fsi/files')
        self._name_file = os.path.expanduser('~/.fsi/name_parts.txt')
        self._name_component_store = indexer.name_component_store()

    def __enter__(self):
        self._name_component_store.load(self._name_file)
        return self

    def __exit__(self, data_type, value, tb):
        # store and load to debug structure for test purposes
        t = time.time()
        self._name_component_store.save(self._name_file)
        logging.debug("save: %.2fs", time.time() - t)
        _test_store = indexer.name_component_store()
        t = time.time()
        _test_store.load(self._name_file)
        logging.debug("load: %.4fs", time.time() - t)
        assert _test_store == self._name_component_store

    def _get_name_components(self, path):
        ''' turn "/home/user/some/directory" into index based string
            e.g. "2/7/4/9"'''
        #todo: assert: '/{}'" not in path
        return '/'.join((str(self._name_component_store.get_index(n))
                             for n in path[1:].split('/')))

    def _restore_name(self, packed_path):
        ''' opposite of _get_name_components(): restores the original path
            on the filesystem '''
        return '/' + '/'.join((self._name_component_store[i]
                         for i in (int(c) for c in packed_path.split('/'))))

    def _store_single_file(self, size_path, name):
        ''' write a file with meta information about a single file '''
        with open(os.path.join(size_path, 'dirinfo'), 'w') as _f:
            _f.write("single ")
            _f.write(name)

    def _get_size_path(self, size):
        ''' returns a tuple with a path representing the file's size and the
            status of the path.
            Creates it if not existent. status is 0 for path did not exist yet,
            1 for path exists with a 'dirinfo' and 1 for path exists with
            several file information.
        '''
        _result = os.path.join(self._file_dir, '/'.join('%d' % size))
        try:
            os.makedirs(_result)
            return (_result, None)
        except OSError as ex:
            if ex.errno != 17: # path exists
                raise
            try:
                _dirinfo = open(os.path.join(_result, 'dirinfo')).readline().split(' ')
                return (_result, _dirinfo)
            except IOError as ex:
                if ex.errno == 2:  # file does not exist
                    return (_result, None)
                raise
                # todo: assert existing hash files

    def _add_file(self, filename):
        try:
            _filesize = os.path.getsize(filename)
            _time = int(os.path.getmtime(filename) * 100)
        except:
            logging.warn('permission denied: "%s"', filename)
            raise

        _size_path, _state = self._get_size_path(_filesize)

        _packed_name = self._get_name_components(filename)
        assert (self._restore_name(_packed_name) == filename)
        # logging.debug("%s => %s", filename, _packed_name)
        # print(_packed_name, _time)

        try:
            _t = time.time()
            if _filesize < 60000:
                _hash = sha1_internal(filename)
            else:
                _hash = sha1_external(filename)
            _t = time.time() - _t
    
            if _filesize >= 10 ** 6:
                logging.debug("#=%s, %s bytes, %.1fms, %.2fMb/ms, /%s/%s",
                              _hash, '{0:,}'.format(_filesize),  _t * 1000,
                              _filesize / (2 << 20) / (_t  * 1000) ,
                              _packed_name, os.path.basename(filename))
        except IOError as ex:
            if ex.errno == 13:
                logging.warn('cannot create checksum (permission denied): "%s"',
                             filename)
            raise

        # === no state changing operations before
        # === red exception safety line ===============================
        # === no exceptions after

        if _state is None:
            # file size not registered
            # create a file with file name and modification date
            self._store_single_file(_size_path, _packed_name)
        else:
            if _state[0] == 'single':
                _path = _state[1]
                if _packed_name != _path:
                    # we found another file with the same file - we have
                    # to turn this entry into a multi-entry
                    print('collision')
                    self._promote_to_multi(_size_path, _filesize, _path, _packed_name)
                else:
                    print('found myself')
                    
            elif _state[0] == 'multi':
                assert False
            else:
                assert False

        return _filesize
    
    def _promote_to_multi(self, size_path, size, other_packed_name, new_packed_name):
        ''' turn a single file entry into a multi file entry
        '''
        # todo raise if any hash cannot be computed
        # todo raise if second file does not exist
        other_file_name = self._restore_name(other_packed_name)
        new_file_name = self._restore_name(new_packed_name)
        
        hash1 = fast_sha1(other_file_name, size)
        hash2 = fast_sha1(new_file_name, size)
        
        assert False
        
    def add(self, path):
        _file_count = 0
        _perf_measure_t = time.time()
        _total_size = 0
        _ignore_pattern = ('.git', '.svn', '__pycache__')

        for (_dir, _dirs, files) in os.walk(path, topdown=True):
            _dirs[:] = [d for d in _dirs if d not in _ignore_pattern]

            _dir = os.path.abspath(_dir)
            for fname in files:
                _fullname = os.path.join(_dir, fname)

                assert _fullname[0] == '/'

                if os.path.islink(_fullname):
                    #logging.debug("skip link %s" % _fullname)
                    continue
                if not os.path.isfile(_fullname):
                    logging.debug("skip special %s" % _fullname)
                    continue
                try:
                    _total_size += self._add_file(_fullname)
                except IOError as ex:
                    if ex.errno == 13:
                        # IOError 13 perm denied
                        continue
                    raise
                except:
                    raise
                _file_count += 1

                if _file_count % 1000 == 0:
                    _t = time.time()
                    logging.debug("performance info: #files:%d, %.2fms/file, #words:%d",
                        _file_count,
                        (_t - _perf_measure_t),
                        len(self._name_component_store) / 2)
                    _perf_measure_t = _t


        logging.info("added %d files with a total of %s bytes",
                     _file_count, '{0:,}'.format(_total_size))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.debug('.'.join((str(e) for e in sys.version_info)))
    with indexer() as p:
        p.add(sys.argv[1])


'''
size_cats:

    0:    2004
    1:   14909 ****
    2:   79085 **************************
    3:  169468 ********************************************************
    4:   61196 ********************
    5:   12829 ****
    6:    7339 **
    7:     890
    8:      47
    9:      16

files:  347783
sizes:   55014
folders: 70877

'''

