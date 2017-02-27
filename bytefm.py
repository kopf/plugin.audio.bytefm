from bs4 import BeautifulSoup
import requests


class Scraper(object):
    base_url = 'https://www.byte.fm'

    def list_shows(self, route):
        retval = []
        soup = self._make_soup(route)
        for broadcast_list in soup.find_all('div', {'class': 'broadcast-list'}):
            for show in broadcast_list.find_all('a'):
                retval.append((unicode(show.text.strip()).encode('utf-8'), show['href']))
        return retval

    def _make_soup(self, route):
        return BeautifulSoup(requests.get(self.base_url + route).text, 'html.parser')
