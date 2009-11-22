"""
The XML-RPC & internal API for pony-build.

You can get the current coordinator object by calling
pony_build.server.get_coordinator().
"""

import time
from datetime import datetime, timedelta
import UserDict
import os, os.path
import urllib

# default duration allocated to a build
DEFAULT_BUILD_DURATION=60*60            # in seconds <== 1 hr

# the maximum request for a build allowance
MAX_BUILD_ALLOWANCE=4*60*60               # in seconds <== 1 hr

### files location

if 'PONY_BUILD_FILES' in os.environ:
    _files_dir = os.path.abspath(os.environ['PONY_BUILD_FILES'])
else:
    _files_dir = os.path.dirname(__file__)
    _files_dir = os.path.join(_files_dir, '..', '.files')
    _files_dir = os.path.abspath(_files_dir)

if not os.path.exists(_files_dir):
    os.mkdir(_files_dir)

print 'putting uploaded files into %s' % _files_dir

###

class UploadedFile(object):
    def __init__(self, subdir, filename, description, visible):
        self.subdir = subdir
        self.filename = filename
        self.description = description
        self.visible = visible

    def make_subdir(self):
        subdir = os.path.join(_files_dir, self.subdir)
        subdir = os.path.abspath(subdir)
        if not os.path.isdir(subdir):
            os.mkdir(subdir)

    def _make_abspath(self):
        safe_path = urllib.quote_plus(self.filename)
        fullpath = os.path.join(_files_dir, self.subdir, safe_path)
        fullpath = os.path.abspath(fullpath)
        if not fullpath.startswith(_files_dir):
            raise Exception("security warning: %s not under %s" % \
                            (self.filename, _files_dir))
        return fullpath

    def exists(self):
        return os.path.isfile(self._make_abspath())

    def open(self, mode='rb'):
        return open(self._make_abspath(), mode)

class IntDictWrapper(object, UserDict.DictMixin):
    def __init__(self, d):
        self.d = d

    def __getitem__(self, k):
        k = str(int(k))
        return self.d[k]

    def __setitem__(self, k, v):
        k = str(int(k))
        self.d[k] = v

    def __delitem__(self, k):
        k = str(int(k))
        self.d.__delitem__(k)

    def keys(self):
        return [ int(x) for x in self.d.keys() ]

    def sync(self):
        if hasattr(self.d, 'sync'):
            self.d.sync()

    def close(self):
        if hasattr(self.d, 'close'):
            self.d.close()

def build_tagset(client_info, no_arch=False, no_host=False):
    arch = client_info['arch']
    host = client_info['host']
    package = client_info['package']

    tags = list(client_info['tags'])

    tags.append('__package=' + package)
    if not no_arch:
        tags.append('__arch=' + arch)
    if not no_host:
        tags.append('__host=' + host)

    tagset = frozenset(tags)
    return tagset

class PonyBuildCoordinator(object):
    def __init__(self, db=None):
        if db is None:
            db = IntDictWrapper({})

        self.db = db

        self._process_results()
        self.request_build = {}
        self.is_building = {}
        self.listeners = []

        self.files = {}

    def add_listener(self, x):
        self.listeners.append(x)

    def notify_build(self, package, client_info, requested_allowance=None):
        tagset = build_tagset(client_info)
        self.is_building[tagset] = (time.time(), requested_allowance)

    def add_results(self, client_ip, client_info, results):
#        print client_ip
#        print client_info
#        print results
#        print '---'
        receipt = dict(time=time.time(), client_ip=client_ip)

        key = self.db_add_result(receipt, client_ip, client_info, results)
        self._process_results()

        for x in self.listeners:
            x.notify_result_added(key)

        # @CTB should return an auth key to allow changes to this record,
        # not just the record #... INSECURE.
        return key

    def set_request_build(self, client_info, value):
        # note: setting value=False is a way to override value=True.
        tagset = build_tagset(client_info)
        self.request_build[tagset] = value

    def check_should_build(self, client_info, keep_request=False):
        """
        Returns tuple: ('should_build_flag, reason')
        """
        package = client_info['package']
        tagset = build_tagset(client_info)
        
        last_build = self.get_unique_tagsets_for_package(package)

        if self.request_build.get(tagset, False):
            if not keep_request:
                self.request_build.pop(tagset)
            return True, 'build requested'
        
        if tagset in self.is_building:
            (last_t, requested) = self.is_building[tagset]
            last_t = datetime.fromtimestamp(last_t)
            
            now = datetime.now()
            diff = now - last_t

            if not requested:
                last_duration = DEFAULT_BUILD_DURATION
                if tagset in last_build:
                    try:
                        last_duration = last_build[tagset][1]['duration']
                    except KeyError:
                        pass
                requested = last_duration
            requested = timedelta(0, requested) # seconds

            if diff < requested:
                return False, 'may be in build now'
                
        if tagset in last_build:
            last_t = last_build[tagset][0]['time']
            last_t = datetime.fromtimestamp(last_t)
            
            now = datetime.now()
            diff = now - last_t
            if diff >= timedelta(1): # 1 day, default
                return True, 'last build was %s ago; do build!' % (diff,)

            # was it successful?
            success = last_build[tagset][1]['success']
            if not success:
                return True, 'last build was unsuccessful; go!'
        else:
            # tagset not in last_build
            return True, 'no build recorded for %s; build!' % (tagset,)

        return False, "build up to date"

    def _process_results(self):
        self._hosts = hosts = {}
        self._archs = archs = {}
        self._packages = packages = {}

        keys = sorted(self.db.keys())

        for k in keys:
            (receipt, client_info, results_list) = self.db[k]

            host = client_info['host']
            arch = client_info['arch']
            pkg = client_info['package']

            l = hosts.get(host, [])
            l.append(k)
            hosts[host] = l

            l = archs.get(arch, [])
            l.append(k)
            archs[arch] = l

            l = packages.get(pkg, [])
            l.append(k)
            packages[pkg] = l

    def db_get_result_info(self, result_id):
        return self.db[result_id]

    def db_add_result(self, receipt, client_ip, client_info, results):
        next_key = 0
        if self.db:
            next_key = max(self.db.keys()) + 1

        receipt['result_key'] = str(next_key)
                
        self.db[next_key] = (receipt, client_info, results)
        self.db.sync()

        return next_key

    def db_add_uploaded_file(self, auth_key, filename, content, description,
                             visible):
        if auth_key not in self.db:
            return False
        
        print 'YY', auth_key
        print 'YY', filename
        print 'YY', len(content)
        print 'YY', description

        auth_key = str(auth_key)

        subdir = auth_key
        fileobj = UploadedFile(subdir, filename, description, visible)
        fileobj.make_subdir()
        fp = fileobj.open('wb')
        fp.write(content)
        fp.close()

        file_list = self.files.get(auth_key, [])
        file_list.append(fileobj)
        self.files[auth_key] = file_list

        return True

    def get_files_for_result(self, key):
        return self.files.get(key, [])

    def get_all_packages(self):
        k = self._packages.keys()
        k.sort()
        return k

    def get_last_result_for_package(self, package):
        x = self._packages.get(package)
        if x:
            return x[-1]
        return None

    def get_all_results_for_package(self, package):
        l = self._packages.get(package, [])
        if l:
            return [ self.db[n] for n in l ]
        return []

    def get_all_archs(self):
        k = self._archs.keys()
        k.sort()
        return k

    def get_last_result_for_arch(self, arch):
        x = self._archs.get(arch)
        if x:
            return x[-1]
        return None
    

    def get_all_hosts(self):
        k = self._hosts.keys()
        k.sort()
        return k

    def get_last_result_for_host(self, host):
        x = self._hosts.get(host)
        if x:
            return x[-1]
        return None

    def get_latest_arch_result_for_package(self, package):
        d = {}
        for arch, l in self._archs.iteritems():
            for n in l:
                receipt, client_info, results = self.db[n]
                if client_info['package'] == package:
                    d[arch] = (receipt, client_info, results)

        return d

    def get_unique_tagsets_for_package(self, package,
                                      no_host=False, no_arch=False):
        """
        Get the 'unique' set of latest results for the given package,
        based on tags, host, and architecture.  'no_host' says to
        collapse multiple hosts, 'no_arch' says to ignore multiple
        archs.

        Returns a dictionary of (receipt, client_info, results_list)
        tuples indexed by the set of keys used for 'uniqueness',
        i.e. an ImmutableSet of the tags + host + arch.  For display
        purposes, anything beginning with a '__' should be filtered
        out of the keys.
        
        """
        result_indices = self._packages.get(package)
        if not result_indices:
            return {}

        d = {}
        for n in result_indices:
            receipt, client_info, results_list = self.db[n]
            key = build_tagset(client_info, no_host=no_host, no_arch=no_arch)
            
            # check if already stored
            if key in d:
                receipt2, _, _ = d[key]
                # store the more recent one...
                if receipt['time'] > receipt2['time']:
                    d[key] = receipt, client_info, results_list
            else:
                d[key] = receipt, client_info, results_list

        return d

    def get_tagsets_for_package(self, package, no_host=False, no_arch=False):
        result_indices = self._packages.get(package)
        if not result_indices:
            return []

        x = set()
        for n in result_indices:
            receipt, client_info, results_list = self.db[n]
            key = build_tagset(client_info, no_host=no_host, no_arch=no_arch)

            x.add(key)

        return list(x)

    def get_last_result_for_tagset(self, package, tagset):
        result_indices = self._packages.get(package)
        if not result_indices:
            return 0

        result_indices.reverse()
        for n in result_indices:
            receipt, client_info, results_list = self.db[n]
            key = build_tagset(client_info)

            if set(tagset) == set(key):
                return (receipt, client_info, results_list)

        return 0
