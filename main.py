import hashlib
import os
import shutil

from BeautifulSoup import BeautifulSoup
import requests
from simpleplugin import Plugin
import xbmc
import xbmcgui


plugin = Plugin()
_ = plugin.initialize_gettext()

SHOWS_CACHE = os.path.join(plugin.config_dir, 'shows')
if not os.path.exists(SHOWS_CACHE):
    os.mkdir(SHOWS_CACHE)

BASE_URL = 'https://www.byte.fm'

ARCHIVE_BASE_URL = 'http://archiv.byte.fm'

LETTERS = '0ABCDEFGHIJKLMNOPQRSTUVWXYZ'

PLUGIN_NAME = 'plugin.audio.bytefm'

CHUNK_SIZE = 1024 * 1024 # 1MB

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    AUTH = (plugin.addon.getSetting("byte.login.username"),
            plugin.addon.getSetting("byte.login.password"))
    assert all(AUTH)
except AssertionError:
    plugin.addon.openSettings()


CUE_TEMPLATE = u'''PERFORMER "{moderators}"
TITLE "{broadcast_title}"
'''
CUE_ENTRY_TEMPLATE = u'''FILE "{filename}" MP3
  TRACK {tracknumber} AUDIO
    TITLE "{title}"
    PERFORMER "{artist}"
    INDEX 01 {timestamp}
'''


def _http_get(url, **kwargs):
    """Log and perform a HTTP GET"""
    plugin.log_notice("HTTP GET: {}".format(url))
    kwargs['auth'] = AUTH
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp

def _strip_html(text):
    text = text or ''
    return BeautifulSoup(text).getText()

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
def _get_broadcast_recording_playlist(show_slug, broadcast_date):
    url = BASE_URL + '/api/v1/broadcasts/{}/{}/'.format(show_slug, broadcast_date)
    return _http_get(url).json()

@plugin.cached(duration=60*24*30) # TODO: RESET THIS CACHE WHEN USER CHANGES CREDENTIALS
def _get_streams():
    url = BASE_URL + '/api/v1/streams/'
    return _http_get(url).json()

@plugin.cached(duration=60*24*7)
def _get_moderators():
    url = BASE_URL + '/api/v1/moderators/'
    moderators = _http_get(url).json()
    return sorted(moderators, key=lambda k: k['name'])

def _get_img_url(api_resp):
    if api_resp['image']:
        return BASE_URL + api_resp['image']
    return None

def _get_subtitle(broadcast):
    if broadcast.get('subtitle'):
        return u'{} ({})'.format(_strip_html(broadcast['subtitle']), broadcast['date'])
    else:
        return _(u'Broadcast from {}').format(broadcast['date'])

def _save_cuefile(playlist, cue_path, mp3_path, moderators, broadcast_title):
    plugin.log_notice("Creating CUE file at {}".format(cue_path))
    with open(cue_path, 'w') as f:
        f.write(CUE_TEMPLATE.format(
            moderators=moderators, broadcast_title=broadcast_title).encode('utf-8'))
        for idx, entry in enumerate(playlist):
            minutes, seconds = (0, 0) if idx == 0 else divmod(entry['time'], 60)
            timestamp = "%02d:%02d:00" % (minutes, seconds)
            f.write(CUE_ENTRY_TEMPLATE.format(
                filename=mp3_path, tracknumber='%02d' % int(idx+1), title=entry['title'],
                artist=entry['artist'], timestamp=timestamp).encode('utf-8'))

def _save_thumbnail(image_url, show_path):
    dest_path = os.path.join(show_path, 'folder.jpg')
    if not os.path.exists(dest_path):
        try:
            resp = _http_get(image_url, stream=True)
        except:
            msg = "Failed to download show thumbnail {} - ignoring.".format(image_url)
            plugin.log_error(msg)
        else:
            with open(dest_path, 'wb') as f:
                resp.raw.decode_content = True
                shutil.copyfileobj(resp.raw, f)
    return dest_path

def _download_show(title, moderators, show_slug, broadcast_date, image_url, show_path):
    plugin.log_notice("Downloading show {} to {}".format(show_slug, show_path))
    broadcast_data = _get_broadcast_recording_playlist(show_slug, broadcast_date)
    recordings = broadcast_data['recordings']
    list_items = []
    if not os.path.exists(show_path):
        os.makedirs(show_path)
    thumbnail_path = _save_thumbnail(image_url, show_path)
    for rec_idx, url in enumerate(recordings):
        mp3_filename = url.replace('/', '_').replace(' ', '_').lower()
        label = 'Part {}'.format(rec_idx+1)
        show_part_path = os.path.join(show_path, label)
        list_items.append({'url': show_part_path, 'label': label})
        if not os.path.exists(show_part_path):
            os.makedirs(show_part_path)
        shutil.copy(thumbnail_path, show_part_path)
        mp3_path = os.path.join(show_part_path, mp3_filename)
        cue_path = mp3_path + '.cue'
        _save_cuefile(broadcast_data['playlist'][url], cue_path, mp3_path, moderators, title)
        if not os.path.isfile(mp3_path):
            plugin.log_notice('{} does not exist, downloading...'.format(mp3_path))
            resp = _http_get(ARCHIVE_BASE_URL + url, stream=True)
            progress_bar = xbmcgui.DialogProgress()
            progress_bar.create(_('Downloading...'))
            i = 0.0
            file_size = int(resp.headers['Content-Length'])
            extra_info = _('File {} of {}').format(rec_idx + 1, len(recordings))
            with open(mp3_path, 'wb') as f:
                for block in resp.iter_content(CHUNK_SIZE):
                    f.write(block)
                    i += 1
                    percent_done = int(((CHUNK_SIZE * i) / file_size) * 100)
                    progress_bar.update(percent_done, _('Please wait'), extra_info)

    return list_items


@plugin.action()
def root(params):
    streams = _get_streams()
    stream_url = streams.get('hq', streams['sq'])
    items = [
        {
            'label': _('Livestream'),
            'url': stream_url,
            'icon': os.path.join(THIS_DIR, 'icon.png'),
            'is_playable': True
        },
        {
            'label': _('Browse shows by title'),
            'url': plugin.get_url(action='letters'),
        },
        {
            'label': _('Browse shows by genre'),
            'url': plugin.get_url(action='list_genres'),
        },
        {
            'label': _('Browse shows by moderator'),
            'url': plugin.get_url(action='list_moderators'),
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
def list_moderators(params):
    return [
        {
            'label': _strip_html(moderator['name']),
            'icon': BASE_URL + moderator['image'] if moderator['image'] else '',
            'info': {'video': {'plot': _strip_html(moderator['description'])}},
            'url': plugin.get_url(action='list_shows', moderator_slug=moderator['slug'])
        } for moderator in _get_moderators()
    ]


@plugin.action()
def list_shows(params):
    items = []
    shows = _get_shows()

    def _create_show_listitem(show):
        show_img = _get_img_url(show)
        return {
            'label': _strip_html(show['title']),
            'url': plugin.get_url(
                action='list_broadcasts', slug=show['slug'], show_img=show_img,
                moderators=show['moderators'] or 'Unknown', show_title=show['title']),
            'thumbnail': _get_img_url(show),
            'icon': _get_img_url(show),
            'info': {'video': {'plot': _strip_html(show['description'])}}
        }

    if params.get('letter'):
        letter = params['letter'].lower()
        if letter == '0':
            letter = '0123456789'
        for show in shows:
            if show['title'].lower()[0] in letter:
                items.append(_create_show_listitem(show))
    elif params.get('genre'):
        for show in shows:
            if params['genre'] in show['genres']:
                items.append(_create_show_listitem(show))
    elif params.get('moderator_slug'):
        try:
            moderator = [m for m in _get_moderators() if m['slug'] == params['moderator_slug']][0]
        except IndexError:
            raise Exception("Invalid moderator {} - not found!".format(params['moderator_slug']))
        for show in shows:
            if show['slug'] in moderator['broadcasts']:
                items.append(_create_show_listitem(show))
    else:
        raise Exception("Need to specify at least a letter, genre or moderator slug!")
    return items


@plugin.action()
def list_broadcasts(params):
    # TODO: url: play or display info?
    return [
        {
            'label': _get_subtitle(broadcast),
            'url': plugin.get_url(
                action='play', show_slug=params['slug'], broadcast_date=broadcast['date'],
                moderators=params['moderators'], title=_get_subtitle(broadcast),
                image=_get_img_url(broadcast) or params['show_img']),
            'icon': _get_img_url(broadcast) or params['show_img'],
            'thumbnail': _get_img_url(broadcast) or params['show_img'],
            'info': {'video': {'plot': broadcast['description']}},
        } for broadcast in _get_broadcasts(params['slug'])
    ]


@plugin.action()
def play(params):
    # TODO: TEST CUESHEETS WITH MULTIPLE PARTS
    show_dir = hashlib.md5(params['show_slug'] + params['broadcast_date'] + params['title']).hexdigest()
    show_path = os.path.join(SHOWS_CACHE, show_dir)
    list_items = _download_show(
        params['title'], params['moderators'], params['show_slug'],
        params['broadcast_date'], params['image'], show_path)
    return list_items


if __name__ == '__main__':
    plugin.run()
