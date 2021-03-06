import os
import time
import warnings

import testutil
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from twill.commands import *

from pony_build import coordinator, dbsqlite

DB_TEST_FILE=os.path.join(os.path.dirname(__file__), 'tests.db')

def make_db(filename=DB_TEST_FILE):
    try:
        os.unlink(filename)
    except OSError:
        pass

    db = dbsqlite.open_shelf(filename, 'c')
    db = coordinator.IntDictWrapper(db)
    coord = coordinator.PonyBuildCoordinator(db)

    ## CTB: note, make sure to add items to the database in the correct
    ## order: most recently received ==> last.

    # mangle the receipt time in the database, in order to test expiration
    client_info = dict(success=True,
                       tags=['a_tag'],
                       package='test-expire',
                       duration=0.1,
                       host='testhost',
                       arch='fooarch')
    results = [ dict(status=0, name='abc', errout='', output='',
                    command=['foo', 'bar'],
                    type='test_the_test') ]
    (k, _) = coord.add_results('127.0.0.1', client_info, results)
    receipt, client_info, results_list = db[k]
    receipt['time'] = time.time() - 60*60*24 * 10     # -- 10 days ago
    db[k] = receipt, client_info, results_list

    # mangle the receipt time in the database, in order to test stale flag.
    client_info = dict(success=True,
                       tags=['a_tag'],
                       package='test-stale',
                       duration=0.1,
                       host='testhost',
                       arch='fooarch')
    results = [ dict(status=0, name='abc', errout='', output='',
                    command=['foo', 'bar'],
                    type='test_the_test') ]
    (k, _) = coord.add_results('127.0.0.1', client_info, results)
    receipt, client_info, results_list = db[k]
    receipt['time'] = time.time() - 60*60*24 * 2      # -- 2 days ago
    db[k] = receipt, client_info, results_list

    # also add a fresh result
    client_info = dict(success=True,
                       tags=['a_tag'],
                       package='test-underway',
                       duration=0.1,
                       host='testhost',
                       arch='fooarch')
    results = [ dict(status=0, name='abc', errout='', output='',
                    command=['foo', 'bar'],
                    type='test_the_test') ]
    (k, _) = coord.add_results('127.0.0.1', client_info, results)

    del coord
    db.close()

def setup():
    make_db()
    testutil.run_server(DB_TEST_FILE)

def teardown():
    testutil.kill_server()

def test_index():
    go(testutil._server_url)

    title('pony-build main')
    code(200)

def test_package_index():
    go(testutil._server_url)
    code(200)
    
    go('/p/test-underway/')
    title('Build summary for')
    code(200)
    show()
    notfind("Stale build")
    
    follow('view details')
    code(200)
    show()


def test_package_stale():
    go(testutil._server_url)
    code(200)
    
    go('/p/test-stale/')
    title('Build summary for')
    code(200)
    show()

    find("Stale build")

def test_package_expired():
    go(testutil._server_url)
    code(200)
    
    go('/p/test-expire/')
    title('Build summary for')
    code(200)
    show()

    notfind('view details')
