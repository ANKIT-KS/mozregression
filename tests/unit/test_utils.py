import unittest
from mock import patch, Mock
import datetime
import tempfile
import shutil
import os
import requests
from mozregression import utils, errors, limitedfilecache


class TestUrlLinks(unittest.TestCase):
    @patch('requests.get')
    def test_url_no_links(self, get):
        get.return_value = Mock(text='')
        self.assertEquals(utils.url_links(''), [])

    @patch('requests.get')
    def test_url_with_links(self, get):
        get.return_value = Mock(text="""
        <body>
        <a href="thing/">thing</a>
        <a href="thing2/">thing2</a>
        </body>
        """)
        self.assertEquals(utils.url_links(''),
                          ['thing/', 'thing2/'])

    @patch('requests.get')
    def test_url_with_links_regex(self, get):
        get.return_value = Mock(text="""
        <body>
        <a href="thing/">thing</a>
        <a href="thing2/">thing2</a>
        </body>
        """)
        self.assertEquals(
            utils.url_links('', regex="thing2.*"),
            ['thing2/'])


class TestParseDate(unittest.TestCase):
    def test_valid_date(self):
        date = utils.parse_date("2014-07-05")
        self.assertEquals(date, datetime.date(2014, 7, 5))

    def test_invalid_date(self):
        self.assertRaises(errors.DateFormatError, utils.parse_date,
                          "invalid_format")


class TestParseBits(unittest.TestCase):
    @patch('mozregression.utils.mozinfo')
    def test_parse_32(self, mozinfo):
        mozinfo.bits = 32
        self.assertEqual(utils.parse_bits('32'), 32)
        self.assertEqual(utils.parse_bits('64'), 32)

    @patch('mozregression.utils.mozinfo')
    def test_parse_64(self, mozinfo):
        mozinfo.bits = 64
        self.assertEqual(utils.parse_bits('32'), 32)
        self.assertEqual(utils.parse_bits('64'), 64)


class TestDownloadUrl(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

    @patch('requests.get')
    def test_download(self, get):
        self.data = """
        hello,
        this is a response.
        """ * (1024 * 16)

        def iter_content(chunk_size=1):
            rest = self.data
            while rest:
                chunk = rest[:chunk_size]
                rest = rest[chunk_size:]
                yield chunk

        response = Mock(headers={'Content-length': str(len(self.data))},
                        iter_content=iter_content)
        get.return_value = response

        fname = os.path.join(self.tempdir, 'some.content')
        utils.download_url('http://toto', fname)

        self.assertEquals(self.data, open(fname).read())

    @patch('requests.get')
    @patch('mozfile.remove')
    def test_download_with_exception_remove_tempfile(self, remove, get):
        response = Mock(headers={'Content-length': '10'},
                        iter_content=Mock(side_effect=Exception))
        get.return_value = response

        fname = os.path.join(self.tempdir, 'some.content')
        self.assertRaises(Exception, utils.download_url, 'http://toto', fname)
        remove.assert_called_once_with(fname + '.part')


class TestGetBuildUrl(unittest.TestCase):
    def test_for_linux(self):
        self.assertEqual(utils.get_build_regex('test', 'linux', 32),
                         r'test.*linux-i686\.tar.bz2')

        self.assertEqual(utils.get_build_regex('test', 'linux', 64),
                         r'test.*linux-x86_64\.tar.bz2')

        self.assertEqual(utils.get_build_regex('test', 'linux', 64,
                                               with_ext=False),
                         r'test.*linux-x86_64')

    def test_for_win(self):
        self.assertEqual(utils.get_build_regex('test', 'win', 32),
                         r'test.*win32\.zip')
        self.assertEqual(utils.get_build_regex('test', 'win', 64),
                         r'test.*win64(-x86_64)?\.zip')
        self.assertEqual(utils.get_build_regex('test', 'win', 64,
                                               with_ext=False),
                         r'test.*win64(-x86_64)?')

    def test_for_mac(self):
        self.assertEqual(utils.get_build_regex('test', 'mac', 32),
                         r'test.*mac.*\.dmg')
        self.assertEqual(utils.get_build_regex('test', 'mac', 64),
                         r'test.*mac.*\.dmg')
        self.assertEqual(utils.get_build_regex('test', 'mac', 64,
                                               with_ext=False),
                         r'test.*mac.*')


class TestRelease(unittest.TestCase):
    def test_valid_release_to_date(self):
        date = utils.date_of_release(8)
        self.assertEquals(date, "2011-08-16")
        date = utils.date_of_release(15)
        self.assertEquals(date, "2012-06-05")
        date = utils.date_of_release(34)
        self.assertEquals(date, "2014-09-02")

    def test_valid_formatted_release_dates(self):
        formatted_output = utils.formatted_valid_release_dates()
        firefox_releases = utils.releases()

        for line in formatted_output.splitlines():
            if "Valid releases: " in line:
                continue

            fields = line.translate(None, " ").split(":")
            version = int(fields[0])
            date = fields[1]

            self.assertTrue(version in firefox_releases)
            self.assertEquals(date, firefox_releases[version])

    def test_invalid_release_to_date(self):
        with self.assertRaises(errors.UnavailableRelease):
            utils.date_of_release(4)
        with self.assertRaises(errors.UnavailableRelease):
            utils.date_of_release(441)


class TestHTTPCache(unittest.TestCase):
    def setUp(self):
        self.addCleanup(utils.set_http_cache_session, None)

    def make_cache(self):
        return limitedfilecache.get_cache(
            '/fakedir', limitedfilecache.ONE_GIGABYTE, logger=None)

    def test_basic(self):
        self.assertEquals(utils.get_http_session(), requests)

    def test_none_returns_requests(self):
        utils.set_http_cache_session(self.make_cache())
        utils.set_http_cache_session(None)
        self.assertEquals(utils.get_http_session(), requests)

    def test_get_http_session(self):
        utils.set_http_cache_session(self.make_cache())
        a_session = utils.get_http_session()

        # verify session exists
        self.assertTrue(isinstance(a_session, requests.Session))

        # turns out CacheControl is just a function not a class
        # so it makes verifying that we're actually using it
        # a little messy
        for k, v in a_session.adapters.items():
            self.assertTrue(isinstance(v.cache,
                            limitedfilecache.LimitedFileCache))

    def test_set_http_session_with_get_defaults(self):
        original_get = Mock()
        session = Mock(get=original_get)
        utils.set_http_cache_session(session, get_defaults={"timeout": 10.0})
        # default is applied
        utils.get_http_session().get('url')
        original_get.assert_called_with('url', timeout=10.0)
        # this is just a default, it can be overriden
        utils.get_http_session().get('url', timeout=5.0)
        original_get.assert_called_with('url', timeout=5.0)
        # you can still pass a None session
        with patch('requests.Session') as Session:
            Session.return_value = session
            utils.set_http_cache_session(None, get_defaults={'timeout': 1.0})
            # a new session has been returned
            self.assertEquals(session, utils.get_http_session())
            # with defaults patch too
            utils.get_http_session().get('url')
            original_get.assert_called_with('url', timeout=1.0)

if __name__ == '__main__':
    unittest.main()
