from datetime import datetime, timedelta
import functools
import hashlib
import os
import pickle
import re
import shutil
import sys
import time
from urllib.parse import urlencode

import requests
from requests.exceptions import HTTPError
from simpleplugin import Plugin
import xbmc
import xbmcgui
import xbmcaddon


plugin = Plugin()
_ = plugin.initialize_gettext()

ADDON = xbmcaddon.Addon()

SHOWS_CACHE = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), 'shows')
if not os.path.exists(SHOWS_CACHE):
    os.mkdir(SHOWS_CACHE)

INFO_CACHE =  os.path.join(xbmcvfs.translatePath(ADDON.getAddonInfo('profile')), 'info')
if not xbmcvfs.exists(INFO_CACHE):
    xbmcvfs.mkdirs(INFO_CACHE)

BASE_URL = 'https://www.byte.fm'

ARCHIVE_BASE_URL = 'http://archiv.byte.fm'

LETTERS = '0ABCDEFGHIJKLMNOPQRSTUVWXYZ'

PLUGIN_NAME = 'plugin.audio.bytefm'

CHUNK_SIZE = 1024 * 1024 # 1MB

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    AUTH = (
        ADDON.getSettingString("byte.login.username"),
        ADDON.getSettingString("byte.login.password")
    )
except Exception:
    xbmc.log("[ByteFM] Credentials not set. Using None.", xbmc.LOGERROR)
    AUTH = None


CUE_TEMPLATE = '''PERFORMER "{moderators}"
TITLE "{broadcast_title}"
'''
CUE_ENTRY_TEMPLATE = '''FILE "{filename}" MP3
  TRACK {tracknumber} AUDIO
    TITLE "{title}"
    PERFORMER "{artist}"
    INDEX 01 {timestamp}
'''


def cached(duration=10):
    """
    Cached decorator

    Used to cache function return data

    Usage::

        @plugin.cached(30)
        def my_func(*args, **kwargs):
            # Do some stuff
            return value

    :param duration: caching duration in min (positive values only)
    :type duration: int
    :raises ValueError: if duration is zero or negative
    """
    def outer_wrapper(func):
        @functools.wraps(func)
        def inner_wrapper(*args, **kwargs):
            current_time = datetime.now()
            key = hashlib.md5((func.__name__ + str(args) + str(kwargs)).encode("utf-8")).hexdigest()
            fname = os.path.join(INFO_CACHE, key+".pcl")
            try:
                if not xbmcvfs.exists(fname):
                    raise KeyError
                xbmc.log(f'[ByteFM] Exists: {fname}', xbmc.LOGDEBUG)
                timestamp = datetime.fromtimestamp(xbmcvfs.Stat(fname).st_mtime())
                xbmc.log(f'[ByteFM] Timestamp: {timestamp}', xbmc.LOGDEBUG)
                if current_time - timestamp > timedelta(minutes=duration):
                    raise KeyError
                xbmc.log(f'[ByteFM] Read: {fname}', xbmc.LOGDEBUG)
                with open(fname, "rb") as fp:
                    data = pickle.load(fp)
                xbmc.log(f'[ByteFM] Cache hit: {key}', xbmc.LOGDEBUG)
            except (KeyError, pickle.UnpicklingError):
                xbmc.log(f'[ByteFM] Cache miss: {key}', xbmc.LOGDEBUG)
                data = func(*args, **kwargs)
                with open(fname, "wb") as fp:
                    pickle.dump(data, fp)
            return data
        return inner_wrapper
    return outer_wrapper


def plugin_url(**kwargs):
    """Build plugin:// url with args."""
    if kwargs:
        return sys.argv[0] + '?' + urlencode(kwargs, doseq=True)
    else:
        return sys.argv[0]


def _http_get(url, **kwargs):
    """Log and perform a HTTP GET"""
    xbmc.log(f"[ByteFM] HTTP GET: {url}", xbmc.LOGINFO)
    kwargs['auth'] = AUTH
    resp = requests.get(url, **kwargs)
    try:
        resp.raise_for_status()
    except HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            xbmcgui.Dialog().ok(
                'ByteFM', _("Authentication Failed!"),
                _("Please check your username and password."), '')
            ADDON.openSettings()
            sys.exit(-1)
        else:
            raise
    return resp

def _strip_html(text):
    if not text:
        return ''
    # Remove all tags
    return re.sub(r'<[^>]+>', '', text)

@cached(duration=60*24*7)
def _get_genres():
    return _http_get(f'{BASE_URL}/api/v1/genres/').json()

@cached()
def _get_shows():
    return _http_get(f'{BASE_URL}/api/v1/broadcasts/').json()

@cached()
def _get_broadcasts(slug):
    return _http_get(f'{BASE_URL}/api/v1/broadcasts/{slug}/').json()

@cached(duration=60*24*7)
def _get_broadcast_recording_playlist(show_slug, broadcast_slug, broadcast_date):
    if not broadcast_slug:
        broadcast_slug = ''
    url = f'{BASE_URL}/api/v1/broadcasts/{show_slug}/{broadcast_date}/{broadcast_slug}'
    return _http_get(url).json()

@cached(duration=60*24*30) # TODO: RESET THIS CACHE WHEN USER CHANGES CREDENTIALS
def _get_streams():
    return _http_get(f'{BASE_URL}/api/v1/streams/').json()

@cached(duration=60*24*7)
def _get_moderators():
    moderators = _http_get(f'{BASE_URL}/api/v1/moderators/').json()
    return sorted(moderators, key=lambda k: k['name'])

def _get_img_url(api_resp):
    if api_resp['image']:
        return BASE_URL + api_resp['image']
    return None

def _get_subtitle(broadcast):
    if broadcast.get('subtitle'):
        return '{} ({})'.format(_strip_html(broadcast['subtitle']), broadcast['date'])
    else:
        return _('Broadcast from {}').format(broadcast['date'])

def _save_cuefile(playlist, cue_path, mp3_path, moderators, broadcast_title):
    xbmc.log(f"[ByteFM] Creating CUE file at {cue_path}", xbmc.LOGINFO)
    with open(cue_path, 'w', encoding='utf-8') as f:
        f.write(CUE_TEMPLATE.format(
            moderators=moderators, broadcast_title=broadcast_title))
        for idx, entry in enumerate(playlist):
            minutes, seconds = (0, 0) if idx == 0 else divmod(entry['time'], 60)
            timestamp = f"{minutes:02d}:{seconds:02d}:00"
            f.write(CUE_ENTRY_TEMPLATE.format(
                filename=mp3_path, tracknumber=f'{int(idx+1):02d}', title=entry['title'],
                artist=entry['artist'], timestamp=timestamp))

def _save_thumbnail(image_url, show_path):
    dest_path = os.path.join(show_path, 'folder.jpg')
    if not os.path.exists(dest_path):
        try:
            resp = _http_get(image_url, stream=True)
        except Exception:
            msg = f"[ByteFM] Failed to download show thumbnail {image_url} - ignoring."
            xbmc.log(msg, xbmc.LOGERROR)
            dest_path = None
        else:
            with open(dest_path, 'wb') as f:
                resp.raw.decode_content = True
                shutil.copyfileobj(resp.raw, f)
    return dest_path

def _download_show(title, moderators, show_slug, broadcast_slug, broadcast_date, image_url, show_path):
    xbmc.log(f"[ByteFM] Downloading show {show_slug} to {show_path}", xbmc.LOGINFO)
    broadcast_data = _get_broadcast_recording_playlist(show_slug, broadcast_slug, broadcast_date)
    recordings = broadcast_data['recordings']
    list_items = []
    if not os.path.exists(show_path):
        os.makedirs(show_path)
    thumbnail_path = _save_thumbnail(image_url, show_path)
    for rec_idx, url in enumerate(recordings):
        mp3_filename = url.replace('/', '_').replace(' ', '_').lower()
        label = f'Part {rec_idx+1}'
        show_part_path = os.path.join(show_path, label)
        list_items.append({'url': show_part_path, 'label': label})
        if not os.path.exists(show_part_path):
            os.makedirs(show_part_path)
        if thumbnail_path:
            shutil.copy(thumbnail_path, show_part_path)
        mp3_path = os.path.join(show_part_path, mp3_filename)
        cue_path = mp3_path + '.cue'
        _save_cuefile(broadcast_data['playlist'][url], cue_path, mp3_path, moderators, title)
        if not os.path.isfile(mp3_path):
            xbmc.log(f'[ByteFM] {mp3_path} does not exist, downloading...', xbmc.LOGINFO)
            resp = _http_get(ARCHIVE_BASE_URL + url, stream=True)
            progress_bar = xbmcgui.DialogProgress()
            progress_bar.create(_('Please wait'))
            i = 0.0
            file_size = int(resp.headers['Content-Length'])
            extra_info = _('File {} of {}').format(rec_idx + 1, len(recordings))
            with open(mp3_path, 'wb') as f:
                for block in resp.iter_content(CHUNK_SIZE):
                    f.write(block)
                    i += 1
                    percent_done = int(((CHUNK_SIZE * i) / file_size) * 100)
                    progress_bar.update(percent_done, _('Downloading...'), extra_info)

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
            'url': plugin_url(action='letters'),
        },
        {
            'label': _('Browse shows by genre'),
            'url': plugin_url(action='list_genres'),
        },
        {
            'label': _('Browse shows by moderator'),
            'url': plugin_url(action='list_moderators'),
        }
    ]
    return items


@plugin.action()
def letters(params):
    return [{'label': letter, 'url': plugin_url(action='list_shows', letter=letter)} for letter in LETTERS]


@plugin.action()
def list_genres(params):
    return [
        {
            'label': genre,
            'url': plugin_url(action='list_shows', genre=genre)
        } for genre in _get_genres()
    ]


@plugin.action()
def list_moderators(params):
    return [
        {
            'label': _strip_html(moderator['name']),
            'icon': BASE_URL + moderator['image'] if moderator['image'] else '',
            'info': {'video': {'plot': _strip_html(moderator['description'])}},
            'url': plugin_url(action='list_shows', moderator_slug=moderator['slug'])
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
            'url': plugin_url(
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
            raise Exception(f"Invalid moderator {params['moderator_slug']} - not found!")
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
            'url': plugin_url(
                action='play', show_slug=params['slug'], broadcast_date=broadcast['date'],
                moderators=params['moderators'], title=_get_subtitle(broadcast),
                broadcast_slug=broadcast['slug'],
                image=_get_img_url(broadcast) or params['show_img']),
            'icon': _get_img_url(broadcast) or params['show_img'],
            'thumbnail': _get_img_url(broadcast) or params['show_img'],
            'info': {'video': {'plot': broadcast['description']}},
        } for broadcast in _get_broadcasts(params['slug'])
    ]


@plugin.action()
def play(params):
    # TODO: TEST CUESHEETS WITH MULTIPLE PARTS
    concat_str = params['show_slug'] + params['broadcast_date'] + params['title']
    show_dir = hashlib.md5(concat_str.encode('utf-8')).hexdigest()
    show_path = os.path.join(SHOWS_CACHE, show_dir)
    list_items = _download_show(
        params['title'], params['moderators'], params['show_slug'],
        params.get('broadcast_slug'), params['broadcast_date'], params['image'],
        show_path)
    return list_items


if __name__ == '__main__':
    plugin.run()
