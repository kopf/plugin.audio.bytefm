from bs4 import BeautifulSoup
import requests

from lib import log


class Scraper(object):
    base_url = 'https://www.byte.fm'

    def list_shows(self, route):
        retval = []
        soup = self._make_soup(route)
        for show_list in soup.find_all('div', {'class': 'broadcast-list'}):
            for show in show_list.find_all('a'):
                retval.append((unicode(show.text.strip()).encode('utf-8'), show['href']))
        return retval

    def list_broadcasts(self, route):
        retval = []
        # Get the first page:
        soup = self._make_soup(route)
        retval.append(self.extract_broadcast_data(route, soup=soup))
        # Get single subsection of page where broadcasts are displayed,
        # since they're repeated for responsive layout:
        soup = soup.find('div', {'class': 'broadcast-more'})
        # Iterate over all linked pages apart from the one we already have:
        for broadcast in soup.find_all('div', {'class': 'shows-info'})[1:]:
            retval.append(self.extract_broadcast_data(broadcast.find('a')['href']))
        return retval

    def extract_broadcast_data(self, route, soup=None):
        if soup is None:
            soup = self._make_soup(route)
        log(route)
        description = soup.find('div', {'class': 'broadcast-description'}).text.strip()
        img = '{}{}'.format(self.base_url, soup.find('img', {'class': 'broadcast-image'})['src'])
        div = soup.find('div', {'class': 'g-highlight'})
        link = div.find('a')
        subtitle = link.text.strip()
        date = div.find('div', {'class': 'shows-block-date'}).text.strip()
        return {'title': subtitle, 'date': date, 'route': link['href'], 'description': description, 'img': img}

    def _make_soup(self, route):
        return BeautifulSoup(requests.get(self.base_url + route).text, 'html.parser')
