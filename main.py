import os

import requests
from simpleplugin import Plugin


plugin = Plugin()

BASE_URL = 'http://localhost:8000'

LIVE_BASE_URL = 'https://byte.fm'

LETTERS = '0ABCDEFGHIJKLMNOPQRSTUVWXYZ'

PLUGIN_NAME = 'plugin.audio.bytefm'

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

AUTH = ('lol', 'lol')

CUE_TEMPLATE = u'''PERFORMER "{moderators}"
TITLE "{broadcast_title}"
'''
CUE_ENTRY_TEMPLATE = u'''FILE "{filename}" MP3
  TRACK {tracknumber} AUDIO
    TITLE "{title}"
    PERFORMER "{artist}"
    INDEX 01 {timestamp}
'''


def _http_get(url, auth=None):
    """Log and perform a HTTP GET"""
    plugin.log_notice("HTTP GET: {}".format(url))
    return requests.get(url, auth=auth)

@plugin.cached(duration=60*24*7)
def _get_genres():
    return _http_get(BASE_URL + '/api/v1/genres/').json()

@plugin.cached()
def _get_shows():
    return _http_get(BASE_URL + '/api/v1/broadcasts/').json()

@plugin.cached()
def _get_broadcasts(slug):
    return _http_get(BASE_URL + '/api/v1/broadcasts/{}/'.format(slug)).json()

@plugin.cached(duration=60*24*7)
def _get_broadcast_url_playlist(show_slug, broadcast_date):
    url = BASE_URL + '/api/v1/broadcasts/{}/{}/'.format(show_slug, broadcast_date)
    return _http_get(url, auth=AUTH).json()

def _get_img_url(api_resp):
    if api_resp['image']:
        return LIVE_BASE_URL + api_resp['image']
    return None

def _get_subtitle(broadcast):
    if broadcast.get('subtitle'):
        return u'{} ({})'.format(broadcast['subtitle'], broadcast['date'])
    else:
        return u'Broadcast from {}'.format(broadcast['date'])

def _save_cuefile(playlist, cue_path, mp3_path, moderators, broadcast_title):
    with open(cue_path, 'w') as f:
        f.write(CUE_TEMPLATE.format(
            moderators=moderators, broadcast_title=broadcast_title).encode('utf-8'))
        for idx, entry in enumerate(playlist):
            minutes, seconds = divmod(entry['time'], 60)
            timestamp = "%02d:%02d:00" % (minutes, seconds)
            f.write(CUE_ENTRY_TEMPLATE.format(
                filename=mp3_path, tracknumber='%02d' % idx, title=entry['title'],
                artist=entry['artist'], timestamp=timestamp).encode('utf-8'))


@plugin.action()
def root(params):
    items = [
        {
            'label': 'Listen live',
            'url': 'http://byte.fm/livestream.mp3',
            'icon': os.path.join(THIS_DIR, 'icon.png'),
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
                show_img = _get_img_url(show)
                items.append({
                    'label': show['title'],
                    'url': plugin.get_url(
                        action='list_broadcasts', slug=show['slug'], show_img=show_img,
                        moderators=show['moderators'], show_title=show['title']),
                    'thumbnail': _get_img_url(show),
                    'icon': _get_img_url(show)
                })
    elif params.get('genre'):
        for show in _get_shows():
            if params['genre'] in show['genres']:
                show_img = _get_img_url(show)
                items.append({
                    'label': show['title'],
                    'url': plugin.get_url(
                        action='list_broadcasts', slug=show['slug'], show_img=show_img,
                        moderators=show['moderators'], show_title=show['title']),
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
            'url': plugin.get_url(
                action='play', show_slug=params['slug'], broadcast_date=broadcast['date'],
                moderators=params['moderators'], title=_get_subtitle(broadcast)),
            'icon': _get_img_url(broadcast) or params['show_img'],
            'thumbnail': _get_img_url(broadcast) or params['show_img'],
            #'info': {'video': {'plot': broadcast['description']}},
            'is_playable': True
        } for broadcast in _get_broadcasts(params['slug'])
    ]


@plugin.action()
def play(params):
    broadcast_data = _get_broadcast_url_playlist(params['show_slug'], params['broadcast_date'])
    url = broadcast_data['url']
    playlist = reversed(broadcast_data['playlist'])
    mp3_filename = url.replace('/', '_').replace(' ', '_')
    mp3_path = os.path.join(plugin.config_dir, mp3_filename)
    cue_path = mp3_path + '.cue'
    resp = requests.get('http://archiv.byte.fm' + url, stream=True, auth=AUTH)
    # TODO: Assert http 200
    if not os.path.isfile(mp3_path):
        plugin.log_error('{} does not exist'.format(mp3_path))
        with open(mp3_path, 'wb') as f:
            for block in resp.iter_content(4096):
                f.write(block)
    if not os.path.isfile(cue_path):
        _save_cuefile(playlist, cue_path, mp3_path, params['moderators'], params['title'])
    return 'special://profile/addon_data/{}/{}'.format(PLUGIN_NAME, mp3_filename + '.cue')



if __name__ == '__main__':
    plugin.run()
