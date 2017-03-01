import requests

from simpleplugin import Plugin


plugin = Plugin()

BASE_URL = 'http://localhost:8000'

LIVE_BASE_URL = 'https://byte.fm'

LETTERS = '0ABCDEFGHIJKLMNOPQRSTUVWXYZ'


@plugin.cached(duration=60*24*7)
def _get_genres():
    return requests.get(BASE_URL + '/api/v1/genres/').json()

@plugin.cached()
def _get_shows():
    return requests.get(BASE_URL + '/api/v1/broadcasts/').json()

@plugin.cached()
def _get_broadcasts(slug):
    return requests.get(BASE_URL + '/api/v1/broadcasts/{}/'.format(slug)).json()

def _get_img_url(api_resp):
    if api_resp['image']:
        return LIVE_BASE_URL + api_resp['image']
    return None

def _get_subtitle(broadcast):
    if broadcast.get('subtitle'):
        return u'{} ({})'.format(broadcast['subtitle'], broadcast['date'])
    else:
        return u'Broadcast from {}'.format(broadcast['date'])


@plugin.action()
def root(params):
    items = [
        {
            'label': 'Listen live',
            'url': 'http://byte.fm/livestream.mp3',
            'is_playable': True
        },
        {
            'label': 'Browse by title',
            'url': plugin.get_url(action='letters'),
        },
        {
            'label': 'Browse by genre',
            'url': plugin.get_url(action='list_genres'),
        }
    ]
    return items


@plugin.action()
def letters(params):
    return [{'label': letter, 'url': plugin.get_url(action='list_shows', letter=letter)} for letter in LETTERS]


@plugin.action()
def list_genres(params):
    return [
        {
            'label': genre,
            'url': plugin.get_url(action='list_shows', genre=genre)
        } for genre in _get_genres()
    ]


@plugin.action()
def list_shows(params):
    items = []
    if params.get('letter'):
        for show in _get_shows():
            if show['title'].lower().startswith(params['letter'].lower()):
                items.append({
                    'label': show['title'],
                    'url': plugin.get_url(action='list_broadcasts', slug=show['slug']),
                    'thumbnail': _get_img_url(show),
                    'icon': _get_img_url(show)
                })
    elif params.get('genre'):
        for show in _get_shows():
            if params['genre'] in show['genres']:
                items.append({
                    'label': show['title'],
                    'url': plugin.get_url(action='list_broadcasts', slug=show['slug']),
                    'thumbnail': _get_img_url(show),
                    'icon': _get_img_url(show)
                })
    else:
        raise Exception("Need to specify at least a letter or genre!")
    return items


@plugin.action()
def list_broadcasts(params):
    # TODO: url: play or display info?
    # TODO: remove html from api resp
    return [
        {
            'label': _get_subtitle(broadcast),
            'url': plugin.get_url(action='root'),
            'icon': _get_img_url(broadcast),
            'thumbnail': _get_img_url(broadcast),
        } for broadcast in _get_broadcasts(params['slug'])
    ]


if __name__ == '__main__':
    plugin.run()
