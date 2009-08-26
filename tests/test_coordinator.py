from pony_build import coordinator

class Test_Coordinator_API(object):
    def setup(self):
        self.coord = coordinator.PonyBuildCoordinator()

    def load_results(self):
        client_info = dict(success=True,
                           tags=['tag1'],
                           package='package1',
                           duration=0.1,
                           host='test-machine',
                           arch='foo')
        
        self.coord.add_results('127.0.0.1', client_info, [])
        self.tagset = coordinator.build_tagset(client_info)

    def test_get_no_arch(self):
        keys = self.coord.get_all_archs()
        assert len(keys) == 0

    def test_get_arch(self):
        self.load_results()
        keys = self.coord.get_all_archs()
        assert len(keys) == 1
        assert keys[0] == 'foo'

    def test_get_no_packages(self):
        keys = self.coord.get_all_packages()
        assert len(keys) == 0

    def test_get_all_packages(self):
        self.load_results()
        keys = self.coord.get_all_packages()
        assert len(keys) == 1
        assert keys[0] == 'package1'

    def test_get_no_host(self):
        keys = self.coord.get_all_hosts()
        assert len(keys) == 0

    def test_get_host(self):
        self.load_results()
        keys = self.coord.get_all_hosts()
        assert len(keys) == 1
        assert keys[0] == 'test-machine'

    def test_get_unique_tagsets(self):
        """
        We should only have a single tagset for our results.
        """
        
        self.load_results()

        x = self.coord.get_unique_tagsets_for_package('package1')
        x = x.keys()
        
        assert [ self.tagset ] == x

    def test_get_unique_tagsets_is_single(self):
        """
        We should only have a single tagset for our results, even if we
        load twice.
        """
        
        self.load_results()
        self.load_results()

        x = self.coord.get_unique_tagsets_for_package('package1')
        x = x.keys()
        
        assert [ self.tagset ] == x