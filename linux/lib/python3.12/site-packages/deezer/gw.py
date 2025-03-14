import requests
from time import sleep

import json
from deezer.utils import map_artist_album, map_user_track, map_user_artist, map_user_album, map_user_playlist
from deezer.errors import GWAPIError

class PlaylistStatus():
    PUBLIC = 0
    PRIVATE = 1
    COLLABORATIVE = 2

EMPTY_TRACK_OBJ = {
    'SNG_ID': 0,
    'SNG_TITLE': '',
    'DURATION': 0,
    'MD5_ORIGIN': 0,
    'MEDIA_VERSION': 0,
    'FILESIZE': 0,
    'ALB_TITLE': "",
    'ALB_PICTURE': "",
    'ART_ID': 0,
    'ART_NAME': ""
}

class GW:
    def __init__(self, session, headers):
        self.http_headers = headers
        self.session = session
        self.api_token = None

    def api_call(self, method, args=None, params=None):
        if args is None: args = {}
        if params is None: params = {}
        if not self.api_token and method != 'deezer.getUserData': self.api_token = self._get_token()
        p = {'api_version': "1.0",
             'api_token': 'null' if method == 'deezer.getUserData' else self.api_token,
             'input': '3',
             'method': method}
        p.update(params)
        try:
            result_json = self.session.post(
                "http://www.deezer.com/ajax/gw-light.php",
                params=p,
                timeout=30,
                json=args,
                headers=self.http_headers
            ).json()
        except (requests.ConnectionError, requests.Timeout):
            sleep(2)
            return self.api_call(method, args, params)
        if len(result_json['error']):
            if (
                result_json['error'] == {"GATEWAY_ERROR": "invalid api token"} or
                result_json['error'] == {"VALID_TOKEN_REQUIRED": "Invalid CSRF token"}
            ):
                self.api_token = self._get_token()
                return self.api_call(method, args, params)
            if result_json.get('payload', {}) and result_json['payload'].get('FALLBACK', {}):
                for key in result_json['payload']['FALLBACK'].keys():
                    args[key] = result_json['payload']['FALLBACK'][key]
                return self.api_call(method, args, params)
            raise GWAPIError(json.dumps(result_json['error']))
        if not self.api_token and method == 'deezer.getUserData': self.api_token = result_json['results']['checkForm']
        return result_json['results']

    def _get_token(self):
        token_data = self.get_user_data()
        return token_data['checkForm']

    def get_user_data(self):
        return self.api_call('deezer.getUserData')

    def get_user_profile_page(self, user_id, tab, limit=10):
        return self.api_call('deezer.pageProfile', {'USER_ID': user_id, 'tab': tab, 'nb': limit})

    def get_user_favorite_ids(self, checksum = None, limit = 10000, start = 0):
        return self.api_call('song.getFavoriteIds', {'nb': limit, 'start': start, 'checksum': checksum})

    def get_child_accounts(self):
        return self.api_call('deezer.getChildAccounts')

    def get_track(self, sng_id):
        return self.api_call('song.getData', {'SNG_ID': sng_id})

    def get_track_page(self, sng_id):
        return self.api_call('deezer.pageTrack', {'SNG_ID': sng_id})

    def get_track_lyrics(self, sng_id):
        return self.api_call('song.getLyrics', {'SNG_ID': sng_id})

    def get_tracks(self, sng_ids):
        tracks_array = []
        body = self.api_call('song.getListData', {'SNG_IDS': sng_ids})
        errors = 0
        for i in range(len(sng_ids)):
            if sng_ids[i] != 0:
                tracks_array.append(body['data'][i - errors])
            else:
                errors += 1
                tracks_array.append(EMPTY_TRACK_OBJ)
        return tracks_array

    def get_album(self, alb_id):
        return self.api_call('album.getData', {'ALB_ID': alb_id})

    def get_album_page(self, alb_id):
        return self.api_call('deezer.pageAlbum', {
            'ALB_ID': alb_id,
            'lang': 'en',
            'header': True,
            'tab': 0
        })

    def get_album_tracks(self, alb_id):
        tracks_array = []
        body = self.api_call('song.getListByAlbum', {'ALB_ID': alb_id, 'nb': -1})
        for track in body['data']:
            track['POSITION'] = body['data'].index(track)
            tracks_array.append(track)
        return tracks_array

    def get_artist(self, art_id):
        return self.api_call('artist.getData', {'ART_ID': art_id})

    def get_artist_page(self, art_id):
        return self.api_call('deezer.pageArtist', {
            'ART_ID': art_id,
            'lang': 'en',
            'header': True,
            'tab': 0
        })

    def get_artist_top_tracks(self, art_id, limit=100):
        tracks_array = []
        body = self.api_call('artist.getTopTrack', {'ART_ID': art_id, 'nb': limit})
        for track in body['data']:
            track['POSITION'] = body['data'].index(track)
            tracks_array.append(track)
        return tracks_array

    def get_artist_discography(self, art_id, index=0, limit=25):
        return self.api_call('album.getDiscography', {
            'ART_ID': art_id,
            "discography_mode":"all",
            'nb': limit,
            'nb_songs': 0,
            'start': index
        })

    def get_playlist(self, playlist_id):
        return self.get_playlist_page(playlist_id)

    def get_playlist_page(self, playlist_id):
        return self.api_call('deezer.pagePlaylist', {
            'PLAYLIST_ID': playlist_id,
            'lang': 'en',
            'header': True,
            'tab': 0
        })

    def get_playlist_tracks(self, playlist_id):
        tracks_array = []
        body = self.api_call('playlist.getSongs', {'PLAYLIST_ID': playlist_id, 'nb': -1})
        for track in body['data']:
            track['POSITION'] = body['data'].index(track)
            tracks_array.append(track)
        return tracks_array

    def create_playlist(self, title, status=PlaylistStatus.PUBLIC, description=None, songs=[]):
        newSongs = []
        for song in songs:
            newSongs.append([song, 0])
        return self.api_call('playlist.create', {
            'title': title,
            'status': status,
            'description': description,
            'songs': newSongs
        })

    def edit_playlist(self, playlist_id, title, status=None, description=None, songs=[]):
        newSongs = []
        for song in songs:
            newSongs.append([song, 0])
        return self.api_call('playlist.update', {
            'PLAYLIST_ID': playlist_id,
            'title': title,
            'status': status,
            'description': description,
            'songs': newSongs
        })

    def add_songs_to_playlist(self, playlist_id, songs, offset=-1):
        newSongs = []
        for song in songs:
            newSongs.append([song, 0])
        return self.api_call('playlist.addSongs', {
            'PLAYLIST_ID': playlist_id,
            'songs': newSongs,
            'offset': offset
        })

    def add_song_to_playlist(self, playlist_id, sng_id, offset=-1):
        return self.add_songs_to_playlist(playlist_id, [sng_id], offset)

    def remove_songs_from_playlist(self, playlist_id, songs):
        newSongs = []
        for song in songs:
            newSongs.append([song, 0])
        return self.api_call('playlist.deleteSongs', {
            'PLAYLIST_ID': playlist_id,
            'songs': newSongs
        })

    def remove_song_from_playlist(self, playlist_id, sng_id):
        return self.remove_songs_from_playlist(playlist_id, [sng_id])

    def delete_playlist(self, playlist_id):
        return self.api_call('playlist.delete', {'PLAYLIST_ID': playlist_id})

    def add_song_to_favorites(self, sng_id):
        return self.api_call('favorite_song.add', {'SNG_ID': sng_id})

    def remove_song_from_favorites(self, sng_id):
        return self.api_call('favorite_song.remove', {'SNG_ID': sng_id})

    def add_album_to_favorites(self, alb_id):
        return self.api_call('album.addFavorite', {'ALB_ID': alb_id})

    def remove_album_from_favorites(self, alb_id):
        return self.api_call('album.deleteFavorite', {'ALB_ID': alb_id})

    def add_artist_to_favorites(self, art_id):
        return self.api_call('artist.addFavorite', {'ART_ID': art_id})

    def remove_artist_from_favorites(self, art_id):
        return self.api_call('artist.deleteFavorite', {'ART_ID': art_id})

    def add_playlist_to_favorites(self, playlist_id):
        return self.api_call('playlist.addFavorite', {'PARENT_PLAYLIST_ID': playlist_id})

    def remove_playlist_from_favorites(self, playlist_id):
        return self.api_call('playlist.deleteFavorite', {'PLAYLIST_ID': playlist_id})

    def get_page(self, page):
        params = {
            'gateway_input': json.dumps({
                'PAGE': page,
                'VERSION': '2.3',
                'SUPPORT': {
                    'grid': [
                        'channel',
                        'album'
                    ],
                    'horizontal-grid': [
                        'album'
                    ],
                },
                'LANG': 'en'
            })
        }
        return self.api_call('page.get', params=params)

    def search(self, query, index=0, limit=10, suggest=True, artist_suggest=True, top_tracks=True):
        return self.api_call('deezer.pageSearch', {
            "query": query,
            "start": index,
            "nb": limit,
            "suggest": suggest,
            "artist_suggest": artist_suggest,
            "top_tracks": top_tracks
        })

    def search_music(self, query, type, index=0, limit=10):
        return self.api_call('search.music', {
            "query": query,
            "filter": "ALL",
            "output": type,
            "start": index,
            "nb": limit
        })

    # Extra calls

    def get_artist_discography_tabs(self, art_id, limit=100):
        index = 0
        releases = []
        result = {'all': []}
        ids = []

        # Get all releases
        while True:
            response = self.get_artist_discography(art_id, index=index, limit=limit)
            releases += response['data']
            index += limit
            if index > response['total']:
                break

        for release in releases:
            if release['ALB_ID'] not in ids:
                ids.append(release['ALB_ID'])
                obj = map_artist_album(release)
                if (release['ART_ID'] == art_id or release['ART_ID'] != art_id and release['ROLE_ID'] == 0) and release['ARTISTS_ALBUMS_IS_OFFICIAL']:
                    # Handle all base record types
                    if not obj['record_type'] in result:
                        result[obj['record_type']] = []
                    result[obj['record_type']].append(obj)
                    result['all'].append(obj)
                else:
                    # Handle albums where the artist is featured
                    if release['ROLE_ID'] == 5:
                        if not 'featured' in result:
                            result['featured'] = []
                        result['featured'].append(obj)
                    # Handle "more" albums
                    elif release['ROLE_ID'] == 0:
                        if not 'more' in result:
                            result['more'] = []
                        result['more'].append(obj)
                        result['all'].append(obj)
        return result

    def get_track_with_fallback(self, sng_id):
        body = None
        if int(sng_id) > 0:
            try:
                body = self.get_track_page(sng_id)
            except:
                pass
        if body:
            if 'LYRICS' in body:
                body['DATA']['LYRICS'] = body['LYRICS']
            if 'ISRC' in body:
                body['DATA']['ALBUM_FALLBACK'] = body['ISRC']
            body = body['DATA']
        else:
            body = self.get_track(sng_id)
        return body

    def get_user_playlists(self, user_id, limit=25):
        user_profile_page = self.get_user_profile_page(user_id, 'playlists', limit=limit)
        blog_name = user_profile_page['DATA']['USER'].get('BLOG_NAME', "Unknown")
        data = user_profile_page['TAB']['playlists']['data']
        result = []
        for playlist in data:
            result.append(map_user_playlist(playlist, blog_name))
        return result

    def get_user_albums(self, user_id, limit=25):
        data = self.get_user_profile_page(user_id, 'albums', limit=limit)['TAB']['albums']['data']
        result = []
        for album in data:
            result.append(map_user_album(album))
        return result

    def get_user_artists(self, user_id, limit=25):
        data = self.get_user_profile_page(user_id, 'artists', limit=limit)['TAB']['artists']['data']
        result = []
        for artist in data:
            result.append(map_user_artist(artist))
        return result

    def get_user_tracks(self, user_id, limit=25):
        user_data = self.get_user_data()
        if user_data['USER']['USER_ID'] == user_id: return self.get_my_favorite_tracks()
        data = self.get_user_profile_page(user_id, 'loved', limit=limit)['TAB']['loved']['data']
        result = []
        for track in data:
            result.append(map_user_track(track))
        return result

    def get_my_favorite_tracks(self, limit=25):
        ids_raw = self.get_user_favorite_ids(limit=limit)
        ids = [ x['SNG_ID'] for x in ids_raw['data'] ]
        if len(ids) == 0: return []
        data = self.get_tracks(ids)
        result = []
        for (i, track) in enumerate(data):
            track = dict(track, **ids_raw['data'][i])
            result.append(map_user_track(track))
        return result
