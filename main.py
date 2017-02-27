import sys
import urllib
import urlparse

from bs4 import BeautifulSoup
import requests
import xbmcaddon
import xbmcgui
import xbmcplugin

from bytefm import Scraper


class ByteFMPlugin(object):
    def __init__(self, base_url, addon_handle, args):
        self.base_url = base_url
        self.plugin_name = 'plugin.audio.bytefm'
        self.addon = xbmcaddon.Addon(self.plugin_name)
        self.cache_path = self.addon.getAddonInfo('path').decode('utf-8')
        self.addon_handle = addon_handle
        self.scraper = Scraper()
        self.cmd = args.get('cmd')
        self.selected = args.get('selected')
        self.route = args.get('route')

    def execute(self):
        if not self.cmd:
            self.display_screen([
                {'cmd': 'play', 'url': 'http://byte.fm/livestream.mp3', 'label': 'Livestream'},
                {'cmd': 'list_shows', 'label': 'Programmes', 'is_folder': True},
            ])
        elif self.cmd == 'list_shows':
            self.list_shows()
        else:
            raise NotImplementedError()

    def list_shows(self):
        if not self.selected:
            entries = []
            for l in '0ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                entries.append({'cmd': 'list_shows', 'label': l, 'selected': l, 'is_folder': True})
            self.display_screen(entries)
        else:
            shows = self.scraper.list_shows('/sendungen/{}/'.format(self.selected.lower()))
            entries = [
                {'cmd': 'list_broadcasts', 'label': name, 'selected': name, 'route': route, 'is_folder': True} for name, route in shows
            ]
            self.display_screen(entries)

    def list_broadcasts(self):
        raise NotImplementedError()

    def display_screen(self, entries):
        xbmc_entries = []
        for entry in entries:
            label = entry.pop('label')
            is_folder = entry.pop('is_folder', False)
            url = self._build_url(entry)
            xbmc_entries.append((url, xbmcgui.ListItem(label=label), is_folder))
        xbmcplugin.addDirectoryItems(self.addon_handle, xbmc_entries, len(xbmc_entries))
        xbmcplugin.setContent(self.addon_handle, 'songs')
        xbmcplugin.endOfDirectory(self.addon_handle)

    def _build_url(self, query):
        return u'{}?{}'.format(self.base_url, urllib.urlencode(query))

    def _make_soup(self, url):
        return BeautifulSoup(requests.get(url).text, 'html.parser')


if __name__ == '__main__':
    plugin = ByteFMPlugin(
        base_url=sys.argv[0], addon_handle=int(sys.argv[1]),
        args={k: v[0] for k, v in urlparse.parse_qs(sys.argv[2][1:]).iteritems()})
    plugin.execute()
